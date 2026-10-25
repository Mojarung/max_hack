"""Агент Кузи в приложении, реестр MCP-серверов и «Жилищный навигатор» через настоящий клиент FastMCP в памяти."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastmcp import Client
from sqlalchemy import delete

from domovoy.agent import runtime
from domovoy.agent.mcp_tools import McpConnection, UnsafeMcpUrlError, list_server_tools, load_tools
from domovoy.agent.stub import StubChatModel
from domovoy.agent.tools import AgentContext
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.mcp_server import server as navigator
from domovoy.modules.assistant import router as assistant
from domovoy.modules.misc_models import McpServer
from integration.helpers import Home, next_id

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def fresh_mcp_cache() -> Iterator[None]:
    runtime.invalidate_mcp_cache()
    yield
    runtime.invalidate_mcp_cache()


@pytest.fixture
async def clean_registry() -> Any:
    yield
    async with get_sessionmaker()() as s:
        await s.execute(delete(McpServer))
        await s.commit()


@pytest.fixture
def in_memory_navigator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Любое подключение MCP идёт во встроенный «Жилищный навигатор» без сети."""
    monkeypatch.setattr(McpConnection, "client", lambda self, timeout: Client(navigator.mcp, timeout=timeout))


async def safe_url(url: str) -> None:
    return None


class TestAssistantChat:
    async def test_rude_message_is_refused(self, api: httpx.AsyncClient, home: Home) -> None:
        resp = await api.post("/api/v1/assistant/chat", headers=home.h(), json={"message": "Ты дурак, блин"})
        body = resp.json()
        assert body["tools_used"] == [] and body["reply"].startswith("Давай общаться вежливо")

    async def test_question_uses_house_tools(self, api: httpx.AsyncClient, home: Home) -> None:
        resp = await api.post("/api/v1/assistant/chat", headers=home.h(), json={"message": "Какие заявки открыты?"})
        body = resp.json()
        assert body["tools_used"] == ["list_issues"]
        assert "Открытых заявок нет" in body["reply"]


@pytest.mark.usefixtures("clean_registry")
class TestRegistry:
    async def test_admin_manages_servers(
        self, api: httpx.AsyncClient, home: Home, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(assistant, "ensure_public_url", safe_url)
        name = f"weather{next_id()}"
        body = {"name": name, "url": "https://mcp.example.org/mcp", "headers": {"X-Key": "secret"}, "transport": "sse"}
        assert (await api.get("/api/v1/mcp/servers", headers=home.h(home.residents[0]))).status_code == 403
        created = await api.post("/api/v1/mcp/servers", headers=home.h(), json=body)
        assert created.status_code == 201
        srv = created.json()
        assert (srv["name"], srv["transport"], srv["has_headers"], srv["enabled"]) == (name, "sse", True, True)
        assert (await api.post("/api/v1/mcp/servers", headers=home.h(), json=body)).status_code == 409
        listed = (await api.get("/api/v1/mcp/servers", headers=home.h())).json()
        assert [s["name"] for s in listed] == [name]

        async def tools(conn: McpConnection, request_timeout: float) -> list[tuple[str, str]]:
            assert (conn.transport, conn.headers) == ("sse", {"X-Key": "secret"})
            return [("forecast", "Прогноз погоды")]

        monkeypatch.setattr(assistant, "list_server_tools", tools)
        url = f"/api/v1/mcp/servers/{srv['id']}"
        assert (await api.get(f"{url}/tools", headers=home.h())).json() == [
            {"name": "forecast", "description": "Прогноз погоды"}
        ]

        async def down(conn: McpConnection, request_timeout: float) -> list[tuple[str, str]]:
            raise ConnectionError("refused")

        monkeypatch.setattr(assistant, "list_server_tools", down)
        assert (await api.get(f"{url}/tools", headers=home.h())).status_code == 502
        assert (await api.delete(url, headers=home.h())).status_code == 204
        assert (await api.delete(url, headers=home.h())).status_code == 404
        assert (await api.get(f"{url}/tools", headers=home.h())).status_code == 404

    async def test_private_urls_are_rejected(
        self, api: httpx.AsyncClient, home: Home, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = {"name": f"local{next_id()}", "url": "http://127.0.0.1:8765/mcp"}
        resp = await api.post("/api/v1/mcp/servers", headers=home.h(), json=body)
        assert resp.status_code == 422 and resp.json()["detail"] == "Адреса внутренних сетей запрещены"
        # разрешено явно (своя сеть стенда): проверка адреса пропускается
        monkeypatch.setattr(get_settings(), "mcp_allow_private_urls", True)
        assert (await api.post("/api/v1/mcp/servers", headers=home.h(), json=body)).status_code == 201

    async def test_connections_from_settings_and_registry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def check(url: str) -> None:
            if "evil" in url:
                raise UnsafeMcpUrlError("internal")

        monkeypatch.setattr(runtime, "ensure_public_url", check)
        settings = get_settings()
        monkeypatch.setattr(settings, "internal_mcp_enabled", True)
        extra = '[{"name": "weather", "url": "https://w.example.org/sse", "transport": "sse", "headers": {"A": "1"}}]'
        monkeypatch.setattr(settings, "extra_mcp_servers", extra)
        async with get_sessionmaker()() as s:
            s.add_all(
                [
                    McpServer(name="good", url="https://good.example.org/mcp"),
                    McpServer(name="evil", url="https://evil.example.org/mcp"),
                    McpServer(name="off", url="https://off.example.org/mcp", enabled=False),
                ]
            )
            await s.commit()
        conns = {c.name: c for c in await runtime.mcp_connections()}
        assert set(conns) == {"gis_zhkh", "weather", "good"}
        assert conns["weather"].transport == "sse" and conns["weather"].headers == {"A": "1"}

        monkeypatch.setattr(settings, "extra_mcp_servers", "{broken json")
        assert {c.name for c in await runtime.mcp_connections()} == {"gis_zhkh", "good"}


class TestNavigator:
    async def test_tools_over_mcp(self, home: Home, in_memory_navigator: None) -> None:
        conn = McpConnection(name="gis_zhkh", url="http://navigator/mcp")
        names = [n for n, _ in await list_server_tools(conn, 5)]
        assert {"house_passport", "utility_tariffs", "capital_repair_plan", "open_issues", "search_issues"} <= set(
            names
        )

        tools = {t.name: t for t in await load_tools(conn, 5)}
        assert tools["gis_zhkh__utility_tariffs"].description.startswith("[MCP gis_zhkh]")
        tariffs = await tools["gis_zhkh__utility_tariffs"].ainvoke({})
        assert "Холодная вода" in tariffs and navigator.DATA_NOTE in tariffs
        passport = await tools["gis_zhkh__house_passport"].ainvoke({"house_id": home.house.id})
        assert home.house.address in passport and '"year_built": 1987' in passport
        assert "Ремонт крыши" in await tools["gis_zhkh__capital_repair_plan"].ainvoke({})
        assert await tools["gis_zhkh__open_issues"].ainvoke({"house_id": home.house.id}) == '{"result": []}'
        error = await tools["gis_zhkh__search_issues"].coroutine()  # type: ignore[misc]
        assert error.startswith("MCP-сервер gis_zhkh вернул ошибку")

    async def test_navigator_lists_issues(self, home: Home) -> None:
        from domovoy.modules.issues import service as issues
        from domovoy.modules.users.models import House, User

        async with get_sessionmaker()() as s:
            user, house = await s.get(User, home.admin.id), await s.get(House, home.house.id)
            assert user and house
            issue = await issues.create_issue(s, user=user, house=house, description="Течёт крыша над 9 этажом")
        rows = await navigator.open_issues(home.house.id)
        assert rows == [{"id": issue.id, "title": issue.title, "status": "Идёт голосование", "votes": "1/3"}]
        found = await navigator.search_issues("крыша течёт", home.house.id)
        assert found[0]["id"] == issue.id
        assert (await navigator.house_passport(None))["title"]  # без номера - первый дом
        assert await navigator.open_issues(10**8) == []
        assert await navigator.search_issues("крыша", 10**8) == []

    async def test_agent_answers_with_mcp_tool(
        self, home: Home, in_memory_navigator: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "internal_mcp_enabled", True)
        reply = await runtime.run_agent(
            ctx=AgentContext(user_id=home.admin.id, house_id=home.house.id, is_admin=True),
            thread_id=f"test:{next_id()}",
            speaker="Админ Тестов",
            house_title=home.house.title,
            text="Какие тарифы на воду в этом году?",
        )
        assert reply.tools_used == ["gis_zhkh__utility_tariffs"]
        assert "Холодная вода: 38.9 ₽ за м³" in reply.text
        passport = await runtime.run_agent(
            ctx=AgentContext(user_id=home.admin.id, house_id=home.house.id),
            thread_id=f"test:{next_id()}",
            speaker="Админ Тестов",
            house_title=home.house.title,
            text="Какой год постройки у дома?",
        )
        assert "Год постройки: 1987" in passport.text

    async def test_unreachable_server_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def broken(conn: McpConnection, request_timeout: float) -> list[Any]:
            raise ConnectionError("refused")

        monkeypatch.setattr(get_settings(), "internal_mcp_enabled", True)
        monkeypatch.setattr(runtime, "load_tools", broken)
        assert await runtime.load_mcp_tools(force=True) == []
        # кэш на минуту: без force сервер второй раз не спрашиваем
        monkeypatch.setattr(runtime, "load_tools", None)
        assert await runtime.load_mcp_tools() == []

    async def test_real_llm_gets_fallback_middleware(self, home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runtime, "is_real_llm", lambda: True)
        monkeypatch.setattr(runtime, "get_llm", StubChatModel)
        reply = await runtime.run_agent(
            ctx=AgentContext(user_id=home.admin.id, house_id=home.house.id),
            thread_id=f"test:{next_id()}",
            speaker="Админ Тестов",
            house_title=home.house.title,
            text="Привет!",
        )
        assert reply.text.startswith("Привет, Админ!") and reply.tools_used == []
