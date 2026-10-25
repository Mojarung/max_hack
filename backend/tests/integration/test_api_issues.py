"""Заявки через REST API: фото, классификация, дубли, голосование до порога, статусы и права."""

import httpx
import pytest
from fakes import FakeBroker, FakeMinio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.modules.issues.models import Issue, IssueUpdate
from domovoy.modules.misc_models import UserAchievement
from domovoy.modules.users.models import User
from integration.helpers import Home, make_home, png_bytes

pytestmark = pytest.mark.integration


async def create_issue(api: httpx.AsyncClient, home: Home, text: str, **form: str) -> dict:
    resp = await api.post("/api/v1/issues", headers=home.h(home.residents[0]), data={"description": text, **form})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAuth:
    async def test_without_login_is_401(self, api: httpx.AsyncClient) -> None:
        resp = await api.get("/api/v1/issues")
        assert resp.status_code == 401

    async def test_unknown_demo_user_is_401(self, api: httpx.AsyncClient) -> None:
        resp = await api.get("/api/v1/issues", headers={"X-Dev-User": "999999999"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Демо-пользователь не найден"

    async def test_foreign_house_is_403(self, api: httpx.AsyncClient, home: Home) -> None:
        resp = await api.get("/api/v1/issues", headers=home.h(home.outsider))
        assert resp.status_code == 403

    async def test_missing_house_is_403(self, api: httpx.AsyncClient, home: Home) -> None:
        headers = {**home.h(), "X-House-Id": "987654"}
        assert (await api.get("/api/v1/issues", headers=headers)).status_code == 403

    async def test_without_house_header_uses_active_house(self, api: httpx.AsyncClient, home: Home) -> None:
        # первый вход с X-House-Id делает дом активным, дальше он подставляется сам
        await api.get("/api/v1/me", headers=home.h())
        resp = await api.get("/api/v1/me", headers={"X-Dev-User": str(home.admin.max_user_id)})
        assert resp.json()["house"]["id"] == home.house.id
        assert resp.json()["role"] == "admin"


class TestCreate:
    async def test_issue_with_photo_is_classified_and_posted_to_chat(
        self, api: httpx.AsyncClient, home: Home, broker: FakeBroker, minio: FakeMinio
    ) -> None:
        resp = await api.post(
            "/api/v1/issues",
            headers=home.h(home.residents[0]),
            data={"description": "Течёт крыша над 9 этажом, после дождя лужа", "location_hint": "подъезд 2"},
            files=[("photos", ("roof.png", png_bytes(), "image/png"))],
        )
        assert resp.status_code == 201, resp.text
        issue = resp.json()
        assert issue["category"] == "roof"
        assert issue["status"] == "voting"
        assert (issue["votes_count"], issue["votes_needed"]) == (1, 3)
        assert issue["voted_by_me"] is True
        assert issue["responsible_org"]["name"] == home.uk.name
        assert issue["location_hint"] == "подъезд 2"
        assert [t["status"] for t in issue["timeline"]] == ["voting"]
        # фото пересжато в JPEG и лежит в хранилище
        (url,) = issue["photos"]
        key = url.removeprefix("/api/v1/media/")
        assert minio.objects[key][:3] == b"\xff\xd8\xff"
        # сообщение в чат дома с кнопкой голоса и фото
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert f"Заявка №{issue['id']}" in msg["text"]
        assert msg["buttons"][0][0]["payload"] == f"vote:{issue['id']}"
        assert msg["photos"] == [key]
        assert msg["ref"] == {"issue_id": issue["id"]}
        assert broker.events("issue.created", home.house.id)[0]["id"] == issue["id"]
        # первая заявка дала ачивку «Зоркий глаз»
        assert [e["code"] for e in broker.events("achievement.awarded", home.house.id)] == ["first_issue"]

    async def test_media_endpoint_serves_saved_photo(self, api: httpx.AsyncClient, home: Home) -> None:
        resp = await api.post(
            "/api/v1/issues",
            headers=home.h(),
            data={"description": "Сломаны качели во дворе"},
            files=[("photos", ("a.png", png_bytes("blue"), "image/png"))],
        )
        url = resp.json()["photos"][0]
        media = await api.get(url)
        assert media.status_code == 200
        assert media.headers["content-type"] == "image/jpeg"
        assert (await api.get("/api/v1/media/issues/" + "0" * 32 + ".jpg")).status_code == 404
        assert (await api.get("/api/v1/media/documents/secret.pdf")).status_code == 404

    @pytest.mark.parametrize(
        ("files", "detail"),
        [
            ([("photos", ("a.gif", b"GIF89a", "image/gif"))], "Поддерживаются только фото"),
            ([("photos", ("a.png", b"not an image", "image/png"))], "Не удалось прочитать изображение"),
            ([("photos", (f"{i}.png", b"x", "image/png")) for i in range(6)], "не больше 5 фото"),
        ],
    )
    async def test_bad_photos_are_rejected(self, api: httpx.AsyncClient, home: Home, files: list, detail: str) -> None:
        resp = await api.post("/api/v1/issues", headers=home.h(), data={"description": "Течёт кран"}, files=files)
        assert resp.status_code == 422
        assert detail in resp.json()["detail"]

    async def test_blank_description_is_rejected(self, api: httpx.AsyncClient, home: Home) -> None:
        resp = await api.post("/api/v1/issues", headers=home.h(), data={"description": "     "})
        assert resp.status_code == 422

    async def test_gas_goes_out_without_voting(self, api: httpx.AsyncClient, home: Home, broker: FakeBroker) -> None:
        issue = await create_issue(api, home, "В подъезде сильно пахнет газом")
        assert issue["category"] == "gas"
        assert issue["status"] == "sent"
        assert issue["deadline_at"] is not None
        assert "Экстренная категория" in issue["timeline"][-1]["note"]
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert "104" in msg["text"] and "112" in msg["text"]
        assert broker.payloads("issue.dispatch") == [{"issue_id": issue["id"]}]

    async def test_title_from_form_wins(self, api: httpx.AsyncClient, home: Home) -> None:
        issue = await create_issue(api, home, "Во дворе яма у въезда", title="Яма на дороге")
        assert issue["title"] == "Яма на дороге"


class TestReadAndSearch:
    async def test_classify_names_responsible_org(self, api: httpx.AsyncClient, home: Home) -> None:
        resp = await api.post("/api/v1/issues/classify", headers=home.h(), json={"text": "Лифт застрял между этажами"})
        body = resp.json()
        assert body["category"] == "elevator"
        assert body["org_name"] == home.uk.name
        assert body["source"] == "rules"
        assert body["deadline_hours"] > 0

    async def test_classify_garbage_goes_to_regional_operator(self, api: httpx.AsyncClient, home: Home) -> None:
        resp = await api.post(
            "/api/v1/issues/classify", headers=home.h(), json={"text": "Контейнеры переполнены, мусор не вывозят"}
        )
        assert resp.json()["org_kind"] == "regop"
        assert "ТКО" in resp.json()["org_name"]

    async def test_similar_finds_duplicate_of_open_issue(self, api: httpx.AsyncClient, home: Home) -> None:
        issue = await create_issue(api, home, "Течёт крыша над 9 этажом во втором подъезде")
        resp = await api.post(
            "/api/v1/issues/similar", headers=home.h(home.residents[1]), json={"text": "течёт крыша над 9 этажом"}
        )
        found = resp.json()
        assert found and found[0]["id"] == issue["id"]
        assert found[0]["voted_by_me"] is False
        assert found[0]["score"] >= 0.35

    async def test_list_filters_and_search(self, api: httpx.AsyncClient, home: Home, session: AsyncSession) -> None:
        roof = await create_issue(api, home, "Течёт крыша над 9 этажом")
        lamp = await create_issue(api, home, "Не горит свет на лестнице")
        await session.execute(update(Issue).where(Issue.id == lamp["id"]).values(status="resolved"))
        await session.commit()

        all_ids = [i["id"] for i in (await api.get("/api/v1/issues", headers=home.h())).json()]
        assert all_ids == [lamp["id"], roof["id"]]
        open_ids = [i["id"] for i in (await api.get("/api/v1/issues?status=open", headers=home.h())).json()]
        assert open_ids == [roof["id"]]
        resolved = (await api.get("/api/v1/issues?status=resolved", headers=home.h())).json()
        assert [i["id"] for i in resolved] == [lamp["id"]]
        found = (await api.get("/api/v1/issues", params={"q": "крыша"}, headers=home.h())).json()
        assert found[0]["id"] == roof["id"] and found[0]["score"] is not None

    async def test_issue_of_other_house_is_404(self, api: httpx.AsyncClient, home: Home) -> None:
        issue = await create_issue(api, home, "Сломаны качели на площадке")
        other = await create_issue_elsewhere(api)
        assert (await api.get(f"/api/v1/issues/{other}", headers=home.h())).status_code == 404
        assert (await api.get(f"/api/v1/issues/{issue['id']}", headers=home.h())).status_code == 200


async def create_issue_elsewhere(api: httpx.AsyncClient) -> int:
    other = await make_home()
    return (await create_issue(api, other, "Не работает домофон в первом подъезде"))["id"]


class TestVoting:
    async def test_votes_reach_threshold_and_dispatch(
        self, api: httpx.AsyncClient, home: Home, broker: FakeBroker, session: AsyncSession
    ) -> None:
        issue = await create_issue(api, home, "Сломаны качели на детской площадке")
        url = f"/api/v1/issues/{issue['id']}/vote"
        # сообщение заявки уже в чате: голос из приложения должен обновить его счётчик
        await session.execute(update(Issue).where(Issue.id == issue["id"]).values(chat_message_id="mid-1"))
        await session.commit()
        broker.published.clear()

        second = (await api.post(url, headers=home.h(home.residents[1]))).json()
        assert (second["votes_count"], second["status"], second["voted_by_me"]) == (2, "voting", True)
        assert broker.payloads("bot.issue_refresh") == [{"issue_id": issue["id"]}]
        assert broker.payloads("issue.dispatch") == []

        third = (await api.post(url, headers=home.h(home.residents[2]))).json()
        assert (third["votes_count"], third["status"]) == (3, "sent")
        assert third["deadline_at"] is not None
        assert "Порог набран: 3 из 3" in third["timeline"][-1]["note"]
        assert broker.payloads("issue.dispatch") == [{"issue_id": issue["id"]}]
        # автор получил ачивку за набранный порог
        author_id = home.residents[0].id
        codes = set(await session.scalars(select(UserAchievement.code).where(UserAchievement.user_id == author_id)))
        assert {"first_issue", "issue_sent"} <= codes

        late = await api.post(url, headers=home.h(home.admin))
        assert late.status_code == 409
        assert late.json()["detail"] == "Голосование по этой заявке уже закрыто"

    async def test_double_vote_is_409(self, api: httpx.AsyncClient, home: Home) -> None:
        issue = await create_issue(api, home, "Течёт кран в подвале")
        url = f"/api/v1/issues/{issue['id']}/vote"
        assert (await api.post(url, headers=home.h(home.residents[1]))).status_code == 200
        again = await api.post(url, headers=home.h(home.residents[1]))
        assert again.status_code == 409
        assert again.json()["detail"] == "Вы уже поддержали эту заявку"
        own = await api.post(url, headers=home.h(home.residents[0]))
        assert own.status_code == 409

    async def test_unvote_rules(self, api: httpx.AsyncClient, home: Home, session: AsyncSession) -> None:
        issue = await create_issue(api, home, "Грязно в подъезде, давно не мыли")
        url = f"/api/v1/issues/{issue['id']}/vote"
        voter = home.residents[1]
        await api.post(url, headers=home.h(voter))
        points_after_vote = (await session.get(User, voter.id)).points

        back = await api.delete(url, headers=home.h(voter))
        assert back.status_code == 200
        assert (back.json()["votes_count"], back.json()["voted_by_me"]) == (1, False)
        session.expire_all()
        assert (await session.get(User, voter.id)).points == points_after_vote - 2

        assert (await api.delete(url, headers=home.h(voter))).json()["detail"] == "Вы ещё не голосовали за эту заявку"
        author = await api.delete(url, headers=home.h(home.residents[0]))
        assert author.status_code == 409
        assert author.json()["detail"] == "Автор заявки не может отозвать свой голос"

    async def test_unvote_after_sent_is_409(self, api: httpx.AsyncClient, home: Home) -> None:
        issue = await create_issue(api, home, "Пахнет газом у лифта")
        resp = await api.delete(f"/api/v1/issues/{issue['id']}/vote", headers=home.h(home.residents[1]))
        assert resp.status_code == 409


class TestStatus:
    async def test_author_admin_and_neighbour(
        self, api: httpx.AsyncClient, home: Home, broker: FakeBroker, session: AsyncSession
    ) -> None:
        issue = await create_issue(api, home, "Не горит свет на лестнице первого подъезда")
        url = f"/api/v1/issues/{issue['id']}/status"

        foreign = await api.post(url, headers=home.h(home.residents[1]), json={"status": "resolved"})
        assert foreign.status_code == 403

        work = await api.post(url, headers=home.h(home.residents[0]), json={"status": "in_progress"})
        assert work.json()["status"] == "in_progress"
        assert work.json()["timeline"][-1]["note"].startswith("В работе")

        broker.published.clear()
        done = await api.post(url, headers=home.h(home.admin), json={"status": "resolved", "note": "Заменили лампы"})
        body = done.json()
        assert body["status"] == "resolved"
        assert body["timeline"][-1]["note"] == "Заменили лампы"
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert msg["text"].startswith("🎉 Решено")
        codes = set(
            await session.scalars(select(UserAchievement.code).where(UserAchievement.user_id == home.residents[0].id))
        )
        assert "issue_resolved" in codes

        closed = await api.post(url, headers=home.h(home.admin), json={"status": "rejected"})
        assert closed.status_code == 409

    async def test_unknown_status_is_422(self, api: httpx.AsyncClient, home: Home) -> None:
        issue = await create_issue(api, home, "Сломан домофон")
        resp = await api.post(f"/api/v1/issues/{issue['id']}/status", headers=home.h(), json={"status": "voting"})
        assert resp.status_code == 422

    async def test_timeline_keeps_order(self, api: httpx.AsyncClient, home: Home, session: AsyncSession) -> None:
        issue = await create_issue(api, home, "Не работает лифт в 3 подъезде")
        await api.post(f"/api/v1/issues/{issue['id']}/status", headers=home.h(), json={"status": "rejected"})
        notes = list(
            await session.scalars(
                select(IssueUpdate.status).where(IssueUpdate.issue_id == issue["id"]).order_by(IssueUpdate.id)
            )
        )
        assert notes == ["voting", "rejected"]
