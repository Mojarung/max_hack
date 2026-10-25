"""Профиль, настройки дома, соседи, ачивки, пульс, поиск и служебные эндпоинты."""

import json

import httpx
import pytest
from fakes import FakeBroker, FakeInternet, FakeMinio
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.api import system
from domovoy.core.config import get_settings
from domovoy.core.realtime import hub
from domovoy.modules.users.models import House, Membership, Organization, User
from integration.helpers import Home, make_home, png_bytes

pytestmark = pytest.mark.integration


class TestMe:
    async def test_me_and_onboarding(self, api: httpx.AsyncClient, home: Home) -> None:
        me = (await api.get("/api/v1/me", headers=home.h(home.residents[0]))).json()
        assert me["role"] == "resident" and me["mock"] is True
        assert me["user"]["first_name"] == "Олег" and me["user"]["level_title"] == "Новосёл"
        assert me["user"]["onboarded"] is False
        assert me["house"]["uk_name"] == home.uk.name and me["house"]["has_chat"] is True

        done = (await api.post("/api/v1/me/onboarded", headers=home.h(home.residents[0]))).json()
        assert done["user"]["onboarded"] is True

    async def test_preset_avatar_and_back_to_max_photo(self, api: httpx.AsyncClient, home: Home) -> None:
        h = home.h(home.residents[0])
        preset = (await api.put("/api/v1/me/avatar", headers=h, json={"preset": 3})).json()
        assert preset["user"]["avatar"] == "preset:3"
        assert preset["user"]["photo_url"] == "/avatars/3.webp"
        assert (await api.put("/api/v1/me/avatar", headers=h, json={"preset": 99})).status_code == 422
        reset = (await api.put("/api/v1/me/avatar", headers=h, json={"preset": None})).json()
        assert reset["user"]["avatar"] is None and reset["user"]["photo_url"] is None

    async def test_uploaded_avatar_is_removed_when_replaced(
        self, api: httpx.AsyncClient, home: Home, minio: FakeMinio
    ) -> None:
        h = home.h(home.residents[1])
        files = {"photo": ("me.png", png_bytes("green"), "image/png")}
        uploaded = (await api.post("/api/v1/me/avatar/photo", headers=h, files=files)).json()
        assert uploaded["user"]["avatar"] == "upload"
        key = uploaded["user"]["photo_url"].removeprefix("/api/v1/media/")
        assert key.startswith(f"avatars/{home.residents[1].id}/") and key in minio.objects
        # другое фото или картинка: прежнее своё фото удаляется из хранилища
        await api.put("/api/v1/me/avatar", headers=h, json={"preset": 1})
        assert key not in minio.objects
        empty = await api.post("/api/v1/me/avatar/photo", headers=h, files={"photo": ("", b"", "image/png")})
        assert empty.status_code == 422


class TestHouses:
    async def test_houses_lists_memberships(self, api: httpx.AsyncClient, home: Home, session: AsyncSession) -> None:
        second = House(max_chat_id=None, title="Дача", address="СНТ Ромашка")
        session.add(second)
        await session.flush()
        session.add(Membership(user_id=home.admin.id, house_id=second.id, role="resident"))
        await session.commit()

        rows = (await api.get("/api/v1/houses?refresh=true", headers=home.h())).json()
        assert [(r["id"], r["role"], r["is_current"]) for r in rows] == [
            (home.house.id, "admin", True),
            (second.id, "resident", False),
        ]

    async def test_pulse_counts_votes_waiting_for_me(self, api: httpx.AsyncClient, home: Home) -> None:
        await api.post("/api/v1/issues", headers=home.h(home.residents[0]), data={"description": "Сломаны качели"})
        admin = (await api.get("/api/v1/house/pulse", headers=home.h())).json()
        author = (await api.get("/api/v1/house/pulse", headers=home.h(home.residents[0]))).json()
        assert admin["stats"]["open_issues"] == 1
        assert admin["stats"]["awaiting_my_vote"] == 1
        assert author["stats"]["awaiting_my_vote"] == 0
        assert admin["mood"] in ("happy", "ok") and admin["phrase"]
        # опыт дома - сумма очков жителей: 10 за заявку и 20 за ачивку «Зоркий глаз»
        assert (admin["xp"], admin["level"], admin["xp_next"]) == (30, 1, 400)


class TestHouseSettings:
    async def test_resident_can_change_only_own_apartment(self, api: httpx.AsyncClient, home: Home) -> None:
        h = home.h(home.residents[0])
        assert (await api.patch("/api/v1/house", headers=h, json={"title": "Мой дом"})).status_code == 403
        me = (await api.patch("/api/v1/house", headers=h, json={"apartment": " 42 "})).json()
        assert me["user"]["apartment"] == "42"

    async def test_admin_edits_house_and_gets_own_uk(
        self, api: httpx.AsyncClient, home: Home, session: AsyncSession
    ) -> None:
        body = {
            "title": "  Дом 7  ",
            "address": "г. Ульяновск, ул. Новая, 7",
            "info": "Диспетчерская: 8-800",
            "vote_threshold_pct": 30,
            "uk_name": "УК «Своя»",
            "uk_email": "own@example.org",
            "uk_phone": " +7 111 ",
            "region": "ru-sam",
            "setup_done": True,
        }
        me = (await api.patch("/api/v1/house", headers=home.h(), json=body)).json()
        house = me["house"]
        assert house["title"] == "Дом 7" and house["vote_threshold_pct"] == 30
        assert (house["uk_name"], house["uk_email"], house["uk_phone"]) == ("УК «Своя»", "own@example.org", "+7 111")
        assert (house["region"], house["region_name"]) == ("RU-SAM", "Самарская область")
        # УК была общей с соседним домом: для дома заведена своя запись, общая не тронута
        shared = await session.get(Organization, home.uk.id)
        assert shared is not None and shared.name == home.uk.name
        own = await session.get(House, home.house.id)
        assert own is not None and own.uk_org_id != home.uk.id
        own_uk = own.uk_org_id

        # вторая правка: своя УК уже есть, меняется она же
        again = (await api.patch("/api/v1/house", headers=home.h(), json={"uk_email": None, "uk_phone": ""})).json()
        assert again["house"]["uk_email"] is None and again["house"]["uk_phone"] is None
        session.expire_all()
        assert (await session.get(House, home.house.id)).uk_org_id == own_uk  # type: ignore[union-attr]

    async def test_region_by_coordinates(self, api: httpx.AsyncClient, home: Home, internet: FakeInternet) -> None:
        def nominatim(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/reverse"
            return httpx.Response(200, json={"address": {"ISO3166-2-lvl4": "RU-TA"}})

        internet.handler = nominatim
        me = (await api.patch("/api/v1/house", headers=home.h(), json={"lat": 55.79, "lon": 49.12})).json()
        assert me["house"]["region"] == "RU-TA" and me["house"]["region_name"] == "Республика Татарстан"

    async def test_region_kept_when_geocoder_is_down(self, api: httpx.AsyncClient, internet: FakeInternet) -> None:
        home = await make_home(region="RU-ULY")
        me = (await api.patch("/api/v1/house", headers=home.h(), json={"lat": 54.0, "lon": 48.0})).json()
        assert me["house"]["region"] == "RU-ULY" and me["house"]["lat"] == 54.0
        assert internet.requests  # спрашивали Nominatim, но он недоступен

    async def test_invalid_values_are_422(self, api: httpx.AsyncClient, home: Home) -> None:
        for body in ({"vote_threshold_pct": 1}, {"region": "Ульяновск"}, {"lat": 120}, {"uk_email": "not-mail"}):
            assert (await api.patch("/api/v1/house", headers=home.h(), json=body)).status_code == 422

    async def test_sync_is_admin_only(self, api: httpx.AsyncClient, home: Home) -> None:
        assert (await api.post("/api/v1/house/sync", headers=home.h(home.residents[0]))).status_code == 403
        # без токена MAX сверять не с чем: дом остаётся как есть
        assert (await api.post("/api/v1/house/sync", headers=home.h())).json() == {"members": 0, "bot_is_admin": None}

    async def test_geocode(self, api: httpx.AsyncClient, home: Home, internet: FakeInternet) -> None:
        url = "/api/v1/house/geocode"
        assert (await api.get(url, params={"q": "ул. Ленина"}, headers=home.h(home.residents[0]))).status_code == 403
        assert (await api.get(url, params={"q": "ул."}, headers=home.h())).json() == []
        down = await api.get(url, params={"q": "Ульяновск, Ленина 1"}, headers=home.h())
        assert down.status_code == 502

        internet.handler = lambda request: httpx.Response(
            200,
            json=[
                {
                    "display_name": "Ленина, 1, Ульяновск",
                    "lat": "54.31",
                    "lon": "48.40",
                    "address": {"ISO3166-2-lvl4": "RU-ULY"},
                },
                {"display_name": "Ленина, 1, где-то", "lat": "50", "lon": "40"},
            ],
        )
        found = (await api.get(url, params={"q": "Ульяновск, Ленина 1"}, headers=home.h())).json()
        assert found[0] == {"title": "Ленина, 1, Ульяновск", "lat": 54.31, "lon": 48.4, "region": "RU-ULY"}
        assert found[1]["region"] is None
        assert internet.requests[-1].url.params["countrycodes"] == "ru"


class TestNeighbours:
    async def test_people_and_profile(self, api: httpx.AsyncClient, home: Home) -> None:
        olga = home.residents[0]
        people = (await api.get("/api/v1/people", headers=home.h())).json()
        assert {p["id"] for p in people} == {u.id for u in home.users}
        assert people[0]["role"] == "admin"

        issue = (
            await api.post("/api/v1/issues", headers=home.h(home.residents[1]), data={"description": "Сломан домофон"})
        ).json()
        await api.post(f"/api/v1/issues/{issue['id']}/vote", headers=home.h(olga))
        await api.post("/api/v1/issues", headers=home.h(olga), data={"description": "Течёт кран в подвале"})
        await api.post("/api/v1/listings", headers=home.h(olga), data={"title": "Шкаф-купе", "price": "100"})

        profile = (await api.get(f"/api/v1/people/{olga.id}", headers=home.h())).json()
        assert profile["is_me"] is False
        assert profile["stats"] == {
            "issues_created": 1,
            "issues_open": 1,
            "votes": 1,
            "events_joined": 0,
            "listings_active": 1,
        }
        assert {a["code"] for a in profile["achievements"]} >= {"first_issue", "first_vote"}
        assert (await api.get(f"/api/v1/people/{home.outsider.id}", headers=home.h())).status_code == 404

    async def test_thanks_once_a_day(
        self, api: httpx.AsyncClient, home: Home, broker: FakeBroker, session: AsyncSession
    ) -> None:
        target = home.residents[2]
        url = f"/api/v1/people/{target.id}/thanks"
        profile = (await api.post(url, headers=home.h())).json()
        assert profile["thanks_count"] == 1 and profile["thanked_by_me"] is True
        assert profile["user"]["points"] == 5
        (msg,) = broker.sent(user_id=target.max_user_id)
        assert msg["text"].startswith("🙏 Админ Тестов, кв. 1 говорит вам спасибо")

        again = await api.post(url, headers=home.h())
        assert again.status_code == 409
        self_thanks = await api.post(f"/api/v1/people/{home.admin.id}/thanks", headers=home.h())
        assert self_thanks.status_code == 409
        other = (await api.post(url, headers=home.h(home.residents[0]))).json()
        assert other["thanks_count"] == 2
        assert (await session.get(User, target.id)).points == 10  # type: ignore[union-attr]

    async def test_message_through_kuzya(self, api: httpx.AsyncClient, home: Home, broker: FakeBroker) -> None:
        target = home.residents[1]
        url = f"/api/v1/people/{target.id}/message"
        assert (await api.post(url, headers=home.h(), json={"text": "  Здравствуйте!  "})).json() == {"ok": True}
        (msg,) = broker.sent(user_id=target.max_user_id)
        assert "пишет вам через Кузю" in msg["text"] and "Здравствуйте!" in msg["text"]
        assert (await api.post(url, headers=home.h(), json={"text": "Ещё раз"})).status_code == 429
        assert (await api.post(url, headers=home.h(home.residents[0]), json={"text": "   "})).status_code == 422
        own = await api.post(f"/api/v1/people/{home.admin.id}/message", headers=home.h(), json={"text": "Я"})
        assert own.status_code == 409
        foreign = await api.post(f"/api/v1/people/{home.outsider.id}/message", headers=home.h(), json={"text": "Хай"})
        assert foreign.status_code == 404


class TestAchievementsAndSearch:
    async def test_achievements_and_leaderboard(self, api: httpx.AsyncClient, home: Home) -> None:
        await api.post("/api/v1/issues", headers=home.h(home.residents[0]), data={"description": "Сломаны качели"})
        data = (await api.get("/api/v1/achievements", headers=home.h(home.residents[0]))).json()
        earned = [a["code"] for a in data["items"] if a["earned"]]
        assert earned == ["first_issue"]
        top = data["leaderboard"][0]
        assert (top["rank"], top["user"]["id"], top["is_me"], top["points"]) == (1, home.residents[0].id, True, 30)

    async def test_search_across_sections(self, api: httpx.AsyncClient, home: Home) -> None:
        await api.post("/api/v1/issues", headers=home.h(), data={"description": "Течёт крыша над 9 этажом"})
        await api.post("/api/v1/listings", headers=home.h(), data={"title": "Крыша для детской беседки"})
        found = (await api.get("/api/v1/search", params={"q": "крыша"}, headers=home.h())).json()
        assert found["issues"] and found["issues"][0]["title"].startswith("Течёт крыша")
        assert found["listings"] and found["events"] == []
        assert (await api.get("/api/v1/search", params={"q": "к"}, headers=home.h())).status_code == 422


class TestService:
    async def test_meta_health_and_dev_users(self, api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
        assert (await api.get("/api/v1/health")).json() == {"status": "ok"}
        assert (await api.get("/api/v1/meta")).json()["mock"] is True
        users = (await api.get("/api/v1/dev/users")).json()
        anna = next(u for u in users if u["max_user_id"] == 1001)
        assert anna["role"] == "admin" and anna["first_name"] == "Анна"
        monkeypatch.setattr(get_settings(), "mock_max", False)
        assert (await api.get("/api/v1/dev/users")).status_code == 404

    async def test_login_without_mock_requires_max(
        self, api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "mock_max", False)
        resp = await api.get("/api/v1/me", headers={"X-Dev-User": "1001"})
        assert resp.status_code == 401 and resp.json()["detail"] == "Откройте приложение из MAX"

    async def test_realtime_stream_sends_house_events(self, home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
        class Client:
            checks = 0

            async def is_disconnected(self) -> bool:
                self.checks += 1
                return self.checks > 2

        monkeypatch.setattr(system, "PING_SECONDS", 0.01)
        resp = await system.stream(Client(), init_data=None, dev_user=home.admin.max_user_id, house_id=home.house.id)  # type: ignore[arg-type]
        events = resp.body_iterator.__aiter__()  # type: ignore[union-attr]
        ready = await events.__anext__()
        assert (ready.event, json.loads(ready.data)) == ("ready", {"house_id": home.house.id})
        ping = await events.__anext__()
        assert ping.event == "ping"
        hub.dispatch({"house_id": home.house.id, "event": "issue.created", "data": {"id": 1, "title": "Крыша"}})
        hub.dispatch({"house_id": home.house.id + 1, "event": "issue.created", "data": {"id": 2}})
        created = await events.__anext__()
        assert (created.event, json.loads(created.data)) == ("issue.created", {"id": 1, "title": "Крыша"})
        with pytest.raises(StopAsyncIteration):
            await events.__anext__()
