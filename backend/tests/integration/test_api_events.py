"""События двора, вещи соседей и объявления дома через REST API."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fakes import FakeBroker, FakeMinio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.modules.misc_models import ModerationLog, UserAchievement
from integration.helpers import Home, png_bytes

pytestmark = pytest.mark.integration

RUDE = "Ты дурак, блин"


def future(days: int = 3) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


async def new_event(api: httpx.AsyncClient, home: Home, **extra: object) -> dict:
    body = {"title": "Осенний субботник", "kind": "subbotnik", "starts_at": future(), "place": "Двор", **extra}
    resp = await api.post("/api/v1/events", headers=home.h(), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestEvents:
    async def test_create_announces_with_join_button(
        self, api: httpx.AsyncClient, home: Home, broker: FakeBroker
    ) -> None:
        ev = await new_event(api, home, description="Грабли дадим")
        assert ev["participants_count"] == 1
        assert ev["joined_by_me"] is True
        assert ev["kind_title"] == "Субботник"
        assert [p["id"] for p in ev["participants"]] == [home.admin.id]
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert msg["text"].startswith("📣 **Осенний субботник**")
        assert "Грабли дадим" in msg["text"]
        assert msg["buttons"][0][0]["payload"] == f"join:{ev['id']}"
        assert msg["pin"] is False

    async def test_past_date_and_rude_text_are_rejected(self, api: httpx.AsyncClient, home: Home) -> None:
        past = {"title": "Вчерашний праздник", "starts_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}
        resp = await api.post("/api/v1/events", headers=home.h(), json=past)
        assert resp.status_code == 422 and "уже прошла" in resp.json()["detail"]
        rude = {"title": "Собрание", "description": RUDE, "starts_at": future()}
        resp = await api.post("/api/v1/events", headers=home.h(), json=rude)
        assert resp.status_code == 422 and "не пропустил событие" in resp.json()["detail"]

    async def test_join_leave_and_limits(self, api: httpx.AsyncClient, home: Home, session: AsyncSession) -> None:
        ev = await new_event(api, home, max_participants=2)
        url = f"/api/v1/events/{ev['id']}/join"
        olga, maria, ildar = home.residents

        joined = (await api.post(url, headers=home.h(olga))).json()
        assert joined["participants_count"] == 2 and joined["joined_by_me"] is True
        # субботник даёт ачивку «Чистый двор»
        codes = set(await session.scalars(select(UserAchievement.code).where(UserAchievement.user_id == olga.id)))
        assert "subbotnik" in codes

        again = await api.post(url, headers=home.h(olga))
        assert again.status_code == 409 and again.json()["detail"] == "Вы уже записаны"
        full = await api.post(url, headers=home.h(maria))
        assert full.status_code == 409 and full.json()["detail"] == "Мест больше нет"

        left = (await api.delete(url, headers=home.h(olga))).json()
        assert left["participants_count"] == 1 and left["joined_by_me"] is False
        twice = await api.delete(url, headers=home.h(olga))
        assert twice.status_code == 409
        assert (await api.post(url, headers=home.h(ildar))).status_code == 200

    async def test_list_upcoming_and_past(self, api: httpx.AsyncClient, home: Home) -> None:
        later = await new_event(api, home, starts_at=future(10), title="Собрание жителей", kind="meeting")
        soon = await new_event(api, home, starts_at=future(1))
        upcoming = (await api.get("/api/v1/events", headers=home.h(home.residents[0]))).json()
        assert [e["id"] for e in upcoming] == [soon["id"], later["id"]]
        assert upcoming[0]["joined_by_me"] is False
        assert (await api.get("/api/v1/events?scope=past", headers=home.h())).json() == []
        detail = (await api.get(f"/api/v1/events/{soon['id']}", headers=home.h())).json()
        assert detail["author"]["id"] == home.admin.id

    async def test_event_of_other_house_is_404(self, api: httpx.AsyncClient, home: Home) -> None:
        ev = await new_event(api, home)
        assert (await api.get(f"/api/v1/events/{ev['id']}", headers=home.h(home.outsider))).status_code == 403
        assert (await api.get("/api/v1/events/999999", headers=home.h())).status_code == 404

    async def test_description_edit_rights(self, api: httpx.AsyncClient, home: Home, broker: FakeBroker) -> None:
        ev = await new_event(api, home)
        url = f"/api/v1/events/{ev['id']}"
        foreign = await api.patch(url, headers=home.h(home.residents[0]), json={"description": "Моё описание"})
        assert foreign.status_code == 403
        rude = await api.patch(url, headers=home.h(), json={"description": RUDE})
        assert rude.status_code == 422
        broker.published.clear()
        ok = await api.patch(url, headers=home.h(), json={"description": "  Возьмите перчатки  "})
        assert ok.json()["description"] == "Возьмите перчатки"
        assert broker.events("event.updated", home.house.id)[0]["id"] == ev["id"]

    async def test_photos_add_and_remove(self, api: httpx.AsyncClient, home: Home, minio: FakeMinio) -> None:
        ev = await new_event(api, home)
        url = f"/api/v1/events/{ev['id']}/photos"
        files = [("photos", (f"{i}.png", png_bytes(), "image/png")) for i in range(2)]
        added = (await api.post(url, headers=home.h(), files=files)).json()
        assert len(added["photos"]) == 2
        first_key = added["photos"][0].removeprefix("/api/v1/media/")
        assert first_key in minio.objects

        removed = (await api.delete(f"{url}/0", headers=home.h())).json()
        assert len(removed["photos"]) == 1
        assert first_key not in minio.objects
        assert (await api.delete(f"{url}/5", headers=home.h())).status_code == 404
        foreign = await api.post(url, headers=home.h(home.residents[0]), files=files)
        assert foreign.status_code == 403

        many = [("photos", (f"{i}.png", png_bytes(), "image/png")) for i in range(5)]
        full = (await api.post(url, headers=home.h(), files=many)).json()
        assert len(full["photos"]) == 5
        over = await api.post(url, headers=home.h(), files=files)
        assert over.status_code == 422 and "уже 5 фото" in over.json()["detail"]

    async def test_comments_and_moderation(
        self, api: httpx.AsyncClient, home: Home, broker: FakeBroker, session: AsyncSession
    ) -> None:
        ev = await new_event(api, home)
        url = f"/api/v1/events/{ev['id']}/comments"
        ok = await api.post(url, headers=home.h(home.residents[0]), json={"text": "  Возьму грабли  "})
        assert ok.status_code == 201 and ok.json()["text"] == "Возьму грабли"
        assert broker.events("comment.created", home.house.id)[0]["event_id"] == ev["id"]

        rude = await api.post(url, headers=home.h(home.residents[1]), json={"text": RUDE})
        assert rude.status_code == 422
        assert "Кузя не пропустил комментарий" in rude.json()["detail"]
        logged = await session.scalar(
            select(func.count())
            .select_from(ModerationLog)
            .where(ModerationLog.user_max_id == home.residents[1].max_user_id, ModerationLog.source == "app")
        )
        assert logged == 1

        listed = (await api.get(url, headers=home.h())).json()
        assert [c["text"] for c in listed] == ["Возьму грабли"]
        detail = (await api.get(f"/api/v1/events/{ev['id']}", headers=home.h())).json()
        assert detail["comments_count"] == 1


async def new_listing(api: httpx.AsyncClient, home: Home, user_index: int = 0, **form: str) -> dict:
    data = {"title": "Детская коляска", "description": "Прогулочная", "price": "0", "category": "kids", **form}
    resp = await api.post("/api/v1/listings", headers=home.h(home.residents[user_index]), data=data)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestListings:
    async def test_categories(self, api: httpx.AsyncClient) -> None:
        codes = [c["code"] for c in (await api.get("/api/v1/listings/categories")).json()]
        assert "furniture" in codes and "other" in codes

    async def test_free_listing_with_photo_gives_gift_achievement(
        self, api: httpx.AsyncClient, home: Home, session: AsyncSession
    ) -> None:
        resp = await api.post(
            "/api/v1/listings",
            headers=home.h(home.residents[0]),
            data={"title": "Книги для школьников", "category": "kids"},
            files=[("photos", ("b.png", png_bytes(), "image/png"))],
        )
        item = resp.json()
        assert item["is_free"] is True and item["is_mine"] is True
        assert item["category_title"] == "Детское" and len(item["photos"]) == 1
        codes = set(
            await session.scalars(select(UserAchievement.code).where(UserAchievement.user_id == home.residents[0].id))
        )
        assert "gift" in codes

    async def test_validation(self, api: httpx.AsyncClient, home: Home) -> None:
        bad_cat = await api.post("/api/v1/listings", headers=home.h(), data={"title": "Шкаф", "category": "cars"})
        assert bad_cat.status_code == 422 and bad_cat.json()["detail"] == "Неизвестная категория"
        rude = await api.post("/api/v1/listings", headers=home.h(), data={"title": "Шкаф", "description": RUDE})
        assert rude.status_code == 422
        negative = await api.post("/api/v1/listings", headers=home.h(), data={"title": "Шкаф", "price": "-5"})
        assert negative.status_code == 422

    async def test_filters_and_scopes(self, api: httpx.AsyncClient, home: Home) -> None:
        stroller = await new_listing(api, home)
        drill = await new_listing(api, home, 1, title="Дрель на выходные", price="500", category="tools")
        h = home.h(home.residents[0])
        ids = lambda resp: [i["id"] for i in resp.json()]  # noqa: E731
        assert ids(await api.get("/api/v1/listings", headers=h)) == [drill["id"], stroller["id"]]
        assert ids(await api.get("/api/v1/listings?free=true", headers=h)) == [stroller["id"]]
        assert ids(await api.get("/api/v1/listings?category=tools", headers=h)) == [drill["id"]]
        assert ids(await api.get("/api/v1/listings?scope=mine", headers=h)) == [stroller["id"]]
        found = await api.get("/api/v1/listings", params={"q": "дрель"}, headers=h)
        assert ids(found)[0] == drill["id"]

        await api.patch(f"/api/v1/listings/{stroller['id']}", headers=h, json={"status": "closed"})
        assert ids(await api.get("/api/v1/listings", headers=h)) == [drill["id"]]
        assert ids(await api.get("/api/v1/listings?scope=closed", headers=h)) == [stroller["id"]]
        assert ids(await api.get("/api/v1/listings?scope=mine", headers=h)) == [stroller["id"]]

    async def test_status_and_delete_rights(self, api: httpx.AsyncClient, home: Home, broker: FakeBroker) -> None:
        item = await new_listing(api, home)
        url = f"/api/v1/listings/{item['id']}"
        foreign = await api.patch(url, headers=home.h(home.residents[1]), json={"status": "reserved"})
        assert foreign.status_code == 403
        reserved = await api.patch(url, headers=home.h(home.residents[0]), json={"status": "reserved"})
        assert reserved.json()["status_title"] == "Забронировано"
        # администратор дома может закрыть чужое объявление
        assert (await api.patch(url, headers=home.h(home.admin), json={"status": "closed"})).status_code == 200
        assert (await api.get(url, headers=home.h())).json()["status"] == "closed"

        assert (await api.delete(url, headers=home.h(home.residents[1]))).status_code == 403
        broker.published.clear()
        assert (await api.delete(url, headers=home.h(home.residents[0]))).status_code == 204
        assert broker.events("listing.updated", home.house.id) == [{"id": item["id"], "deleted": True}]
        assert (await api.get(url, headers=home.h())).status_code == 404

    async def test_contact_seller(self, api: httpx.AsyncClient, home: Home, broker: FakeBroker) -> None:
        item = await new_listing(api, home)
        url = f"/api/v1/listings/{item['id']}/contact"
        buyer = home.residents[1]
        broker.published.clear()
        resp = await api.post(url, headers=home.h(buyer), json={"message": "Можно сегодня вечером?"})
        assert resp.json() == {"ok": True}
        (msg,) = broker.sent(user_id=home.residents[0].max_user_id)
        assert "Мария Вторая, кв. 3" in msg["text"]
        assert "Сообщение: Можно сегодня вечером?" in msg["text"]
        assert msg["buttons"][0][0]["payload"] == f"listing_{item['id']}"

        own = await api.post(url, headers=home.h(home.residents[0]), json={})
        assert own.status_code == 409
        await api.patch(f"/api/v1/listings/{item['id']}", headers=home.h(home.residents[0]), json={"status": "closed"})
        closed = await api.post(url, headers=home.h(buyer), json={})
        assert closed.status_code == 409 and closed.json()["detail"] == "Объявление уже закрыто"


class TestAnnouncements:
    async def test_resident_cannot_pin_admin_can(self, api: httpx.AsyncClient, home: Home, broker: FakeBroker) -> None:
        mine = await api.post(
            "/api/v1/announcements",
            headers=home.h(home.residents[0]),
            json={"title": "Нашлись ключи", "text": "Лежат у консьержа", "pin": True},
        )
        assert mine.status_code == 201
        assert mine.json()["pinned"] is False and mine.json()["is_mine"] is True
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert msg["pin"] is False
        assert "📢 **Объявление: Нашлись ключи**" in msg["text"] and "Автор: Олег Первый" in msg["text"]

        broker.published.clear()
        admin = await api.post(
            "/api/v1/announcements", headers=home.h(), json={"title": "Отключение воды", "pin": True}
        )
        assert admin.json()["pinned"] is True
        assert broker.sent(chat_id=home.chat_id)[0]["pin"] is True

        listed = (await api.get("/api/v1/announcements", headers=home.h())).json()
        assert [a["title"] for a in listed] == ["Отключение воды", "Нашлись ключи"]

    async def test_pin_and_delete_rights(self, api: httpx.AsyncClient, home: Home) -> None:
        item = (
            await api.post("/api/v1/announcements", headers=home.h(home.residents[0]), json={"title": "Покраска"})
        ).json()
        url = f"/api/v1/announcements/{item['id']}"
        assert (await api.patch(url, headers=home.h(home.residents[0]), json={"pinned": True})).status_code == 403
        pinned = await api.patch(url, headers=home.h(), json={"pinned": True})
        assert pinned.json()["pinned"] is True and pinned.json()["author"]["id"] == home.residents[0].id
        assert (await api.delete(url, headers=home.h(home.residents[1]))).status_code == 403
        assert (await api.delete(url, headers=home.h(home.residents[0]))).status_code == 204
        assert (await api.delete(url, headers=home.h())).status_code == 404

    async def test_rude_announcement_is_rejected(self, api: httpx.AsyncClient, home: Home) -> None:
        resp = await api.post("/api/v1/announcements", headers=home.h(), json={"title": "Внимание", "text": RUDE})
        assert resp.status_code == 422
