"""Документы дома и личные, укрытия с маршрутом и тревоги через REST API."""

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fakes import FakeBroker, FakeInternet, FakeMinio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.api.deps import Ctx, require_admin_or_mock
from domovoy.core.config import get_settings
from domovoy.modules.safety import osm
from domovoy.modules.safety.feed_models import AlertSource
from domovoy.modules.safety.service import NO_SHELTERS_ADVICE
from integration.helpers import Home, make_home, next_id, png_bytes

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.4 test document"


async def upload(api: httpx.AsyncClient, home: Home, user_index: int = -1, **form: str) -> httpx.Response:
    user = home.admin if user_index < 0 else home.residents[user_index]
    files = {
        "file": (form.pop("filename", "protocol.pdf"), form.pop("content", PDF), form.pop("ctype", "application/pdf"))
    }
    return await api.post(
        "/api/v1/documents", headers=home.h(user), data={"title": "Протокол собрания", **form}, files=files
    )


class TestDocuments:
    async def test_house_document_is_admin_only(self, api: httpx.AsyncClient, home: Home) -> None:
        denied = await upload(api, home, 0, scope="house")
        assert denied.status_code == 403
        doc = (await upload(api, home, scope="house")).json()
        assert doc["scope"] == "house" and doc["can_delete"] is True
        assert (doc["content_type"], doc["size"], doc["filename"]) == ("application/pdf", len(PDF), "protocol.pdf")
        # жители видят документ дома, но удалить не могут
        seen = (await api.get("/api/v1/documents", headers=home.h(home.residents[0]))).json()
        assert [(d["id"], d["can_delete"]) for d in seen] == [(doc["id"], False)]
        url = f"/api/v1/documents/{doc['id']}"
        assert (await api.delete(url, headers=home.h(home.residents[0]))).status_code == 403

    async def test_personal_documents_are_private(self, api: httpx.AsyncClient, home: Home) -> None:
        mine = (await upload(api, home, 0, title="Договор аренды")).json()
        assert mine["scope"] == "personal" and mine["can_delete"] is True
        other = home.h(home.residents[1])
        assert (await api.get("/api/v1/documents", headers=other)).json() == []
        assert (await api.get(f"/api/v1/documents/{mine['id']}/link", headers=other)).status_code == 404
        # и администратор чужой личный документ не видит
        assert (await api.get("/api/v1/documents?scope=personal", headers=home.h())).json() == []
        own = (await api.get("/api/v1/documents?scope=personal", headers=home.h(home.residents[0]))).json()
        assert [d["id"] for d in own] == [mine["id"]]
        assert (await api.get("/api/v1/documents?scope=house", headers=home.h(home.residents[0]))).json() == []

    async def test_signed_link_downloads_file(self, api: httpx.AsyncClient, home: Home) -> None:
        doc = (await upload(api, home, filename="Протокол №1.pdf")).json()
        link = (await api.get(f"/api/v1/documents/{doc['id']}/link", headers=home.h())).json()
        assert link["expires_at"] > time.time()
        resp = await api.get(link["url"])
        assert resp.status_code == 200 and resp.content == PDF
        assert resp.headers["content-type"] == "application/pdf"
        assert "filename*=UTF-8''" in resp.headers["content-disposition"]
        assert resp.headers["cache-control"] == "private, no-store"

        query = parse_qs(urlparse(link["url"]).query)
        forged = await api.get(f"/api/v1/files/{doc['id']}", params={"exp": query["exp"][0], "sig": "0" * 32})
        assert forged.status_code == 403
        old = int(time.time()) - 10
        expired = await api.get(f"/api/v1/files/{doc['id']}", params={"exp": old, "sig": query["sig"][0]})
        assert expired.status_code == 403
        other_doc = await api.get(
            f"/api/v1/files/{doc['id'] + 999}", params=dict(exp=query["exp"][0], sig=query["sig"][0])
        )
        assert other_doc.status_code == 403

    async def test_photo_document_and_bad_files(self, api: httpx.AsyncClient, home: Home, minio: FakeMinio) -> None:
        photo = (await upload(api, home, filename="act.png", content=png_bytes(), ctype="image/png")).json()
        assert photo["content_type"] == "image/jpeg"
        empty = await upload(api, home, content=b"")
        assert empty.status_code == 422 and empty.json()["detail"] == "Файл пустой"
        exe = await upload(api, home, filename="virus.exe", content=b"MZ", ctype="application/x-msdownload")
        assert exe.status_code == 422
        broken = await upload(api, home, filename="x.png", content=b"not png", ctype="image/png")
        assert broken.status_code == 422

    async def test_delete_removes_file(self, api: httpx.AsyncClient, home: Home, minio: FakeMinio) -> None:
        doc = (await upload(api, home, 0, scope="personal")).json()
        before = set(minio.objects)
        assert (
            await api.delete(f"/api/v1/documents/{doc['id']}", headers=home.h(home.residents[0]))
        ).status_code == 204
        assert len(before - set(minio.objects)) == 1
        assert (await api.get("/api/v1/documents", headers=home.h(home.residents[0]))).json() == []


def remote_point() -> tuple[float, float]:
    """Точка, где в базе нет ни одного укрытия: у каждого теста своя и всегда на карте.

    Шаг 0,5° больше окна поиска укрытий (±0,05°), поэтому точки соседних тестов не пересекаются.
    """
    n = next_id()
    lat, lon = -60.0 + (n % 200) * 0.5, -170.0 + (n // 200) * 1.0
    assert -90 < lat < 90 and -180 < lon < 180
    return lat, lon


class TestShelters:
    async def test_nearest_demo_shelters_sorted(self, api: httpx.AsyncClient, home: Home) -> None:
        items = (await api.get("/api/v1/shelters", headers=home.h())).json()
        assert len(items) >= 6
        distances = [s["distance_m"] for s in items]
        assert distances == sorted(distances)
        first = items[0]
        assert first["source"] == "demo" and first["official"] is False
        assert first["yandex_url"].startswith("https://yandex.ru/maps/?rtext=")
        assert first["osm_url"].startswith("https://www.openstreetmap.org/?mlat=")

    async def test_empty_place_is_filled_from_overpass_once(
        self, api: httpx.AsyncClient, home: Home, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lat, lon = remote_point()
        calls: list[tuple[float, float]] = []
        osm_id = 900_000_000 + next_id()

        async def overpass(lat_: float, lon_: float, radius_m: int) -> list[osm.OsmShelter]:
            calls.append((lat_, lon_))
            element = {
                "type": "node",
                "id": osm_id,
                "lat": lat + 0.001,
                "lon": lon + 0.001,
                "tags": {"amenity": "parking", "parking": "underground", "name": "Паркинг у реки", "capacity": "120"},
            }
            item = osm.parse_element(element)
            assert item is not None
            return [item]

        monkeypatch.setattr(osm, "fetch_shelters", overpass)
        params = {"lat": lat, "lon": lon}
        first = (await api.get("/api/v1/shelters", params=params, headers=home.h())).json()
        assert [(s["name"], s["source"], s["capacity"]) for s in first] == [("Паркинг у реки", "osm", 120)]
        assert first[0]["osm_url"] == f"https://www.openstreetmap.org/node/{osm_id}"
        assert first[0]["source_title"]
        again = (await api.get("/api/v1/shelters", params=params, headers=home.h())).json()
        assert [s["id"] for s in again] == [first[0]["id"]]
        assert len(calls) == 1  # ячейка карты свежая, Overpass второй раз не спрашиваем

    async def test_route_by_osrm_and_fallback(self, api: httpx.AsyncClient, home: Home, internet: FakeInternet) -> None:
        shelter = (await api.get("/api/v1/shelters", headers=home.h())).json()[0]
        url = f"/api/v1/shelters/{shelter['id']}/route"
        lat, lon = home.house.lat + 0.0005 * (next_id() % 50), home.house.lon

        straight = (await api.get(url, params={"lat": lat, "lon": lon}, headers=home.h())).json()
        assert straight["provider"] == "straight" and len(straight["points"]) == 2

        def osrm(request: httpx.Request) -> httpx.Response:
            assert "/route/v1/foot/" in request.url.path
            geometry = {"coordinates": [[lon, lat], [lon + 0.001, lat + 0.001], [shelter["lon"], shelter["lat"]]]}
            return httpx.Response(
                200, json={"code": "Ok", "routes": [{"distance": 420.4, "duration": 300.6, "geometry": geometry}]}
            )

        internet.handler = osrm
        routed = (await api.get(url, params={"lat": lat, "lon": lon}, headers=home.h())).json()
        assert (routed["provider"], routed["distance_m"], routed["duration_s"]) == ("osrm", 420, 301)
        assert routed["points"][0] == [round(lat, 6), round(lon, 6)]
        assert (await api.get("/api/v1/shelters/999999/route", headers=home.h())).status_code == 404


class TestAlerts:
    async def test_start_and_end_alert(self, api: httpx.AsyncClient, home: Home, broker: FakeBroker) -> None:
        assert (await api.get("/api/v1/alerts/active", headers=home.h())).json() is None
        # в мок-режиме тестовую тревогу может включить любой житель
        started = await api.post("/api/v1/alerts", headers=home.h(home.residents[0]), json={"kind": "drone"})
        assert started.status_code == 201
        alert = started.json()
        assert alert["active"] is True and alert["kind_title"] == "Беспилотная опасность"
        assert alert["message"].startswith("Внимание! Беспилотная опасность")
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert msg["text"].startswith("🚨 **Беспилотная опасность**")
        assert "Ближайшее укрытие:" in msg["text"]
        assert msg["buttons"][0][0]["type"] == "link"

        pulse = (await api.get("/api/v1/house/pulse", headers=home.h())).json()
        assert pulse["mood"] == "alarm" and pulse["stats"]["active_alert"] is True
        assert (await api.get("/api/v1/alerts/active", headers=home.h())).json()["id"] == alert["id"]

        broker.published.clear()
        ended = (await api.post(f"/api/v1/alerts/{alert['id']}/end", headers=home.h())).json()
        assert ended["active"] is False and ended["ended_at"]
        assert broker.sent(chat_id=home.chat_id)[0]["text"].startswith("✅ Отбой")
        assert (await api.get("/api/v1/alerts/active", headers=home.h())).json() is None

    async def test_alert_without_shelters_gives_advice(self, api: httpx.AsyncClient, broker: FakeBroker) -> None:
        lat, lon = remote_point()
        home = await make_home(lat=lat, lon=lon)
        await api.post("/api/v1/alerts", headers=home.h(), json={"kind": "air", "message": "Воздушная тревога!"})
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert NO_SHELTERS_ADVICE in msg["text"] and "Воздушная тревога!" in msg["text"]

    async def test_foreign_alert_and_rights(
        self, api: httpx.AsyncClient, home: Home, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        other = await make_home()
        alert = (await api.post("/api/v1/alerts", headers=other.h(), json={})).json()
        assert (await api.post(f"/api/v1/alerts/{alert['id']}/end", headers=home.h())).status_code == 404
        # без мок-режима тревогу включает только администратор (вход через X-Dev-User тогда не работает)
        monkeypatch.setattr(get_settings(), "mock_max", False)
        with pytest.raises(HTTPException) as denied:
            require_admin_or_mock(Ctx(user=home.residents[0], house=home.house, role="resident"))
        assert denied.value.status_code == 403
        require_admin_or_mock(Ctx(user=home.admin, house=home.house, role="admin"))

    async def test_alert_sources_of_house_region(self, api: httpx.AsyncClient, session: AsyncSession) -> None:
        region = f"XX-T{next_id()}"
        home = await make_home(region=region)
        session.add_all(
            [
                AlertSource(region=region, type="telegram_web", ref=f"mchs_{region}", title="МЧС (Telegram)"),
                AlertSource(region="RU-ULY", type="telegram_web", ref=f"other_{region}", title="Чужой регион"),
            ]
        )
        await session.commit()
        data = (await api.get("/api/v1/alerts/sources", headers=home.h(home.residents[0]))).json()
        assert data["region"] == region and data["region_name"] is None and data["feeds_enabled"] is False
        assert [s["title"] for s in data["sources"]] == ["МЧС (Telegram)"]
        no_region = await make_home()
        assert (await api.get("/api/v1/alerts/sources", headers=no_region.h())).json()["sources"] == []
