"""Общие настройки тестов: без RabbitMQ, MinIO и внешней сети.

Переменные окружения выставляются до импорта domovoy, поэтому настройки из .env (демо-стенд, токен бота,
настоящая LLM) в тесты не попадают. База для интеграционных тестов - отдельная domovoy_test, демо-базу
domovoy тесты не трогают никогда (см. tests/integration/conftest.py).
"""

import os

TEST_DATABASE_URL = os.environ.get(
    "DOMOVOY_TEST_DATABASE_URL", "postgresql+asyncpg://domovoy:domovoy@localhost:5432/domovoy_test"
)
if not TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
    raise RuntimeError("Тестовая база должна называться *_test, чтобы не задеть демо-стенд")

os.environ.update(
    {
        "DATABASE_URL": TEST_DATABASE_URL,
        "MAX_BOT_TOKEN": "",
        "MOCK_MAX": "true",
        "SEED_DEMO": "true",
        "LLM_PROVIDER": "stub",
        "OLLAMA_API_KEY": "",
        "INTERNAL_MCP_ENABLED": "false",
        "EXTRA_MCP_SERVERS": "[]",
        "ALERT_FEEDS_ENABLED": "false",
        "SMTP_HOST": "",
        "APPEAL_TEST_EMAIL": "",
        "DEFAULT_VOTE_THRESHOLD_PCT": "15",
        "MIN_VOTES_NEEDED": "3",
        "EVENT_REMINDER_MINUTES": "120",
        "MODERATION_STRIKES_LIMIT": "3",
        "PILOT_HOUSE_FALLBACK": "true",
        "MCP_ALLOW_PRIVATE_URLS": "false",
        "FILES_SECRET": "test-files-secret",
        "FILES_LINK_TTL_SECONDS": "900",
        "INIT_DATA_TTL_SECONDS": "86400",
        "MAX_API_URL": "https://max-api.test",
        "MAX_BOT_USERNAME": "domovoy_kuzya_bot",
        "VK_SERVICE_TOKEN": "",
        "ALERT_FEED_INTERVAL_SECONDS": "60",
        "ALERT_FEED_MAX_HOURS": "6",
        # на случай, если заглушка не сработает: сюда подключиться нельзя
        "RABBIT_URL": "amqp://guest:guest@127.0.0.1:1/",
        "S3_ENDPOINT": "127.0.0.1:1",
    }
)

# ruff: noqa: E402  импорты после настройки окружения
from collections.abc import Iterator

import httpx
import pytest
import structlog
from fakes import FakeBroker, FakeInternet, FakeMinio
from langgraph.checkpoint.memory import InMemorySaver

from domovoy.agent import runtime
from domovoy.api import app as api_app
from domovoy.bot import main as bot_main
from domovoy.core import bus, storage
from domovoy.modules.safety import osm
from domovoy.worker import main as worker_main

BROKER = FakeBroker()
MINIO = FakeMinio()
INTERNET = FakeInternet()

# Логи с обычным текстом трассировки: красивый вывод rich с локальными переменными в тестах медленный
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(colors=False, exception_formatter=structlog.dev.plain_traceback),
    ]
)


async def _no_overpass(lat: float, lon: float, radius_m: int) -> list[osm.OsmShelter] | None:
    return None


@pytest.fixture(scope="session", autouse=True)
def _offline() -> Iterator[None]:
    """Шина, хранилище, сеть и память агента подменяются на всю сессию, в том числе для сида базы."""
    mp = pytest.MonkeyPatch()
    for module in (bus, api_app, bot_main, worker_main):
        mp.setattr(module, "get_broker", lambda: BROKER)
    mp.setattr(storage, "get_minio", lambda: MINIO)

    async def offline_send(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        return INTERNET.respond(request)

    async def enter(self: httpx.AsyncHTTPTransport) -> httpx.AsyncHTTPTransport:
        return self

    async def nothing(self: httpx.AsyncHTTPTransport, *args: object) -> None:
        return None

    # Обычный транспорт httpx без пула соединений и SSL: любой запрос наружу уходит в INTERNET.
    # MockTransport и ASGITransport (клиент API в тестах) это не затрагивает.
    mp.setattr(httpx.AsyncHTTPTransport, "__init__", lambda self, *args, **kwargs: None)
    mp.setattr(httpx.AsyncHTTPTransport, "__aenter__", enter)
    mp.setattr(httpx.AsyncHTTPTransport, "__aexit__", nothing)
    mp.setattr(httpx.AsyncHTTPTransport, "aclose", nothing)
    mp.setattr(httpx.AsyncHTTPTransport, "handle_async_request", offline_send)
    # Overpass по умолчанию «не ответил»: укрытия берутся только из базы, фоновых задач с записью нет
    mp.setattr(osm, "fetch_shelters", _no_overpass)
    # psycopg не работает на ProactorEventLoop Windows, а память агента тестам не нужна
    mp.setattr(runtime._State, "checkpointer", InMemorySaver())
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def broker() -> Iterator[FakeBroker]:
    """Публикации текущего теста (список очищается перед каждым тестом)."""
    BROKER.published.clear()
    yield BROKER
    BROKER.published.clear()


@pytest.fixture
def minio() -> FakeMinio:
    return MINIO


@pytest.fixture
def internet() -> Iterator[FakeInternet]:
    INTERNET.handler = None
    INTERNET.requests.clear()
    yield INTERNET
    INTERNET.handler = None
    INTERNET.requests.clear()
