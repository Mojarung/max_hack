"""Запуск процессов: жизненный цикл API, команды CLI, сид, импорт реестра укрытий и опрос Overpass."""

import asyncio
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
import structlog
from fakes import FakeBroker, FakeInternet, FakeMinio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import domovoy
from domovoy.api.app import lifespan
from domovoy.core import aio
from domovoy.core.realtime import hub
from domovoy.modules.issues.models import Issue
from domovoy.modules.misc_models import Shelter
from domovoy.modules.safety import importer
from domovoy.modules.safety.feed_models import AlertSource
from domovoy.modules.safety.osm import fetch_shelters as real_fetch_shelters
from domovoy.modules.users.models import House, Organization
from domovoy.seed import seed_demo
from integration.helpers import next_id

pytestmark = pytest.mark.integration

ORIGINAL_AIO_RUN = aio.run


class TestApiLifespan:
    async def test_startup_seeds_and_forwards_realtime(
        self, app: FastAPI, broker: FakeBroker, minio: FakeMinio
    ) -> None:
        broker.handlers.clear()
        minio.buckets.clear()
        async with lifespan(app):
            assert broker.started == 1 and minio.buckets == {"domovoy"}
            with hub.subscribe(424242) as queue:
                await broker.handlers["rt.#"]({"house_id": 424242, "event": "pulse.changed", "data": {}})
                assert queue.get_nowait()["event"] == "pulse.changed"
        assert broker.started == 0

    async def test_duplicate_action_race_is_409(self, app: FastAPI) -> None:
        handler = app.exception_handlers[IntegrityError]
        response = await handler(None, IntegrityError("INSERT", {}, Exception("duplicate key")))  # type: ignore[arg-type]
        assert response.status_code == 409 and response.body.decode() == '{"detail":"Действие уже выполнено"}'


class TestSeed:
    async def test_seed_is_idempotent(self, session: AsyncSession, minio: FakeMinio) -> None:
        async def counts() -> tuple[int, int, int]:
            houses = await session.scalar(select(func.count()).select_from(House).where(House.is_demo.is_(True)))
            orgs = await session.scalar(select(func.count()).select_from(Organization))
            demo_issues = await session.scalar(
                select(func.count()).select_from(Issue).join(House).where(House.max_chat_id == -100)
            )
            return houses or 0, orgs or 0, demo_issues or 0

        before = await counts()
        await seed_demo()
        assert await counts() == before
        assert before[0] == 2 and before[2] == 5
        roof = await session.scalar(
            select(Issue).join(House).where(House.max_chat_id == -100, Issue.title.startswith("Течёт крыша"))
        )
        assert roof is not None and len(roof.photos) == 2 and all(k in minio.objects for k in roof.photos)


@pytest.fixture
async def cli(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Запуск domovoy.main() в отдельном потоке; корутины команд выполняются в петле тестов."""
    loop = asyncio.get_running_loop()

    def run_on_test_loop(coro: Coroutine[Any, Any, None]) -> None:
        asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=60)

    monkeypatch.setattr(aio, "run", run_on_test_loop)

    async def call(*args: str) -> None:
        monkeypatch.setattr(sys, "argv", ["domovoy", *args])
        # CLI настраивает structlog под консоль; после команды возвращаем настройки тестов
        saved = structlog.get_config()
        try:
            await asyncio.to_thread(domovoy.main)
        finally:
            structlog.configure(**saved)

    return call


class TestCli:
    async def test_process_commands_start_their_runner(self, cli: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        import uvicorn

        from domovoy.bot import main as bot_main
        from domovoy.mcp_server import server
        from domovoy.worker import main as worker_main

        started: list[tuple[str, Any]] = []
        monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: started.append(("api", kw["port"])))
        monkeypatch.setattr(bot_main, "run", lambda: started.append(("bot", None)))
        monkeypatch.setattr(worker_main, "run", lambda: started.append(("worker", None)))
        monkeypatch.setattr(server, "run", lambda host, port: started.append(("mcp", port)))
        for command in ("api", "bot", "worker", "mcp"):
            await cli(command)
        await cli("api", "--port", "9001")
        assert started == [("api", 8000), ("bot", None), ("worker", None), ("mcp", 8765), ("api", 9001)]

    async def test_seed_and_add_alert_source(
        self, cli: Any, capsys: pytest.CaptureFixture[str], session: AsyncSession
    ) -> None:
        await cli("seed")
        ref = f"cli_channel_{next_id()}"
        await cli("add-alert-source", "--region", "RU-ULY", "--type", "telegram_web", "--ref", ref, "--title", "Канал")
        assert f"telegram_web, {ref}, «Канал», включён" in capsys.readouterr().out
        assert await session.scalar(select(AlertSource).where(AlertSource.ref == ref)) is not None

    async def test_import_shelters_command(self, cli: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        csv_file = tmp_path / "shelters.csv"
        csv_file.write_text(
            "name;address;lat;lon;capacity;kind\nУкрытие №1;ул. Мира, 1;52,97;36,06;150;shelter\n", encoding="utf-8-sig"
        )
        await cli(
            "import-shelters", str(csv_file), "--region", "RU-ORL", "--source", "Реестр укрытий Орловской области"
        )
        assert "Готово: добавлено 1, обновлено 0" in capsys.readouterr().out
        with pytest.raises(SystemExit) as bad:
            await cli("import-shelters", str(csv_file), "--region", "Орёл", "--source", "Реестр")
        assert bad.value.code == 2

    async def test_missing_arguments_are_reported(self, cli: Any) -> None:
        for args in (("import-shelters",), ("add-alert-source", "--region", "RU-ULY")):
            with pytest.raises(SystemExit) as err:
                await cli(*args)
            assert err.value.code == 2

    async def test_aio_run_uses_own_loop(self) -> None:
        done: list[bool] = []

        async def job() -> None:
            done.append(True)

        await asyncio.to_thread(ORIGINAL_AIO_RUN, job())
        assert done == [True]


class TestShelterImport:
    async def test_geocoding_and_update(self, tmp_path: Path, internet: FakeInternet, session: AsyncSession) -> None:
        region = f"RU-T{chr(65 + next_id() % 26)}{chr(65 + next_id() % 26)}"
        csv_file = tmp_path / "registry.csv"
        csv_file.write_text(
            "name,address,lat,lon,capacity,kind\n"
            "Школа №5,ул. Ленина 5,,,300,basement\n"
            "Неизвестно где,нет такого адреса,,,,\n"
            "Паркинг,ул. Мира 2,52.9,36.0,,parking\n",
            encoding="utf-8",
        )

        def nominatim(request: httpx.Request) -> httpx.Response:
            if request.url.params["q"] == "ул. Ленина 5":
                return httpx.Response(200, json=[{"lat": "52.96", "lon": "36.07"}])
            return httpx.Response(200, json=[])

        internet.handler = nominatim
        stats = await importer.import_shelters(csv_file, region, "Реестр тестового региона", pause_s=0)
        assert (stats.created, stats.updated, stats.geocoded, stats.skipped) == (2, 0, 1, 1)
        school = await session.scalar(select(Shelter).where(Shelter.region == region, Shelter.name == "Школа №5"))
        assert school is not None and (school.lat, school.official, school.kind) == (52.96, True, "basement")

        internet.handler = lambda request: httpx.Response(500)
        again = await importer.import_shelters(csv_file, region, "Реестр тестового региона", pause_s=0)
        assert (again.created, again.updated, again.skipped) == (0, 1, 2)

    async def test_bad_arguments(self, tmp_path: Path) -> None:
        with pytest.raises(importer.ImportError_, match="ISO 3166-2"):
            await importer.import_shelters(tmp_path / "x.csv", "Орёл", "Реестр")
        with pytest.raises(importer.ImportError_, match="источник"):
            await importer.import_shelters(tmp_path / "x.csv", "RU-ORL", "  ")


class TestOverpass:
    async def test_second_mirror_answers_after_first_fails(self, internet: FakeInternet) -> None:
        def mirrors(request: httpx.Request) -> httpx.Response:
            if "maps.mail.ru" in str(request.url):
                return httpx.Response(504, text="Gateway Timeout")
            element = {"type": "node", "id": 5, "lat": 54.0, "lon": 48.0, "tags": {"railway": "subway_entrance"}}
            return httpx.Response(200, json={"elements": [element]})

        internet.handler = mirrors
        items = await real_fetch_shelters(54.0, 48.0, 2500)
        assert items is not None and [i.kind for i in items] == ["metro"]
        assert [r.url.host for r in internet.requests] == ["maps.mail.ru", "overpass-api.de"]

    async def test_all_mirrors_down(self, internet: FakeInternet, monkeypatch: pytest.MonkeyPatch) -> None:
        assert await real_fetch_shelters(54.0, 48.0, 2500) is None
        from domovoy.core.config import get_settings

        monkeypatch.setattr(get_settings(), "overpass_timeout_seconds", 0.5)
        internet.requests.clear()
        assert await real_fetch_shelters(54.0, 48.0, 2500) is None
        assert internet.requests == []  # бюджет времени меньше секунды: зеркала даже не спрашиваем
