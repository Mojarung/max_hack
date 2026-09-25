"""ReAct-агент Кузи на LangGraph (langchain.agents.create_agent).

- память: чекпоинтер Postgres, поток на чат (в группе один поток на весь чат, каждое
  сообщение подписано именем автора, поэтому агент понимает, кто говорит);
- инструменты: доменные (tools.py) + инструменты подключённых MCP-серверов;
- устойчивость: облачная модель падает на stub, длинная история сворачивается в резюме.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import structlog
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware, SummarizationMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy import select

from domovoy.agent.llm import get_llm, get_stub, is_real_llm
from domovoy.agent.mcp_tools import McpConnection, Transport, UnsafeMcpUrlError, ensure_public_url, load_tools
from domovoy.agent.tools import AgentContext, build_tools, now_msk
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.modules.misc_models import McpServer

log = structlog.get_logger(__name__)

MCP_CACHE_SECONDS = 60
MCP_TIMEOUT_SECONDS = 8
RECURSION_LIMIT = 12

SYSTEM_PROMPT = """Ты Домовой Кузя, добрый и заботливый хранитель многоквартирного дома в чате жителей MAX.
Правила:
- Всегда вежлив, обращайся по имени, отвечай кратко и по-русски, без канцелярита. Можно одно эмодзи.
- Сообщения в группе приходят в формате «[Имя Фамилия]: текст». Отвечай тому, кто написал последним.
- Используй инструменты для фактов о доме. Не выдумывай номера заявок, сроки, законы и адреса.
- Нормативные сроки и основания бери только из ответов инструментов, это справочная информация.
- Если не хватает данных (например, даты события), вежливо уточни.
- При запахе газа сразу советуй звонить 104 или 112.
- Просьбу «сделай объявление», «оповести соседей» выполняй инструментом create_announcement. Если это мероприятие
  жителей и названа дата, передай её в when: появится ещё и событие с кнопкой «Иду».
- Не обсуждай политику, не давай медицинских и юридических гарантий.
Сейчас: {now} (Москва). Собеседник: {user_name}. Дом: {house_title}."""


@dataclass(frozen=True, slots=True)
class AgentReply:
    text: str
    tools_used: list[str]


class _State:
    checkpointer: BaseCheckpointSaver[Any] | None = None
    pool: AsyncConnectionPool | None = None
    mcp_tools: list[BaseTool] = []  # noqa: RUF012  общий кэш процесса
    mcp_loaded_at: float = 0.0
    lock = asyncio.Lock()


async def get_checkpointer() -> BaseCheckpointSaver[Any]:
    if _State.checkpointer is not None:
        return _State.checkpointer
    async with _State.lock:
        if _State.checkpointer is None:
            try:
                pool = AsyncConnectionPool(
                    get_settings().psycopg_url,
                    max_size=5,
                    open=False,
                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                )
                await pool.open(wait=True, timeout=10)
                saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
                await saver.setup()
                _State.pool, _State.checkpointer = pool, saver
            except Exception:
                log.warning("agent.checkpointer_fallback_memory", exc_info=True)
                _State.checkpointer = InMemorySaver()
    return _State.checkpointer


async def close_runtime() -> None:
    if _State.pool is not None:
        await _State.pool.close()


async def mcp_connections() -> list[McpConnection]:
    """Встроенный «Жилищный навигатор», серверы из EXTRA_MCP_SERVERS и из реестра в БД."""
    s = get_settings()
    conns: dict[str, McpConnection] = {}
    if s.internal_mcp_enabled:
        conns["gis_zhkh"] = McpConnection(name="gis_zhkh", url=s.internal_mcp_url)
    try:
        for item in json.loads(s.extra_mcp_servers or "[]"):
            conns[item["name"]] = McpConnection(
                name=item["name"],
                url=item["url"],
                transport="sse" if item.get("transport") == "sse" else "streamable_http",
                headers=item.get("headers") or {},
            )
    except (json.JSONDecodeError, KeyError, TypeError):
        log.warning("agent.extra_mcp_invalid")
    async with get_sessionmaker()() as session:
        registry = list(await session.scalars(select(McpServer).where(McpServer.enabled.is_(True))))
    for srv in registry:
        if not s.mcp_allow_private_urls:
            try:
                await ensure_public_url(srv.url)
            except UnsafeMcpUrlError:
                log.warning("agent.mcp_unsafe_url", server=srv.name)
                continue
        transport: Transport = "sse" if srv.transport == "sse" else "streamable_http"
        conns[srv.name] = McpConnection(name=srv.name, url=srv.url, transport=transport, headers=srv.headers or {})
    return list(conns.values())


async def load_mcp_tools(force: bool = False) -> list[BaseTool]:
    """Загружает инструменты всех MCP-серверов. Недоступный сервер пропускается, а не ломает агента."""
    if not force and time.monotonic() - _State.mcp_loaded_at < MCP_CACHE_SECONDS:
        return _State.mcp_tools
    tools: list[BaseTool] = []
    for conn in await mcp_connections():
        try:
            tools.extend(await asyncio.wait_for(load_tools(conn, MCP_TIMEOUT_SECONDS), MCP_TIMEOUT_SECONDS))
        except Exception:
            log.warning("agent.mcp_unavailable", server=conn.name, exc_info=True)
    _State.mcp_tools, _State.mcp_loaded_at = tools, time.monotonic()
    return tools


def invalidate_mcp_cache() -> None:
    _State.mcp_loaded_at = 0.0


async def run_agent(
    *,
    ctx: AgentContext,
    thread_id: str,
    speaker: str,
    house_title: str,
    text: str,
) -> AgentReply:
    tools = build_tools(ctx) + await load_mcp_tools()
    middleware: list[Any] = []
    if is_real_llm():
        middleware = [
            ModelFallbackMiddleware(get_stub()),
            SummarizationMiddleware(get_llm(), trigger=("messages", 40), keep=("messages", 16)),
        ]
    agent = create_agent(
        get_llm(),
        tools=tools,
        system_prompt=SYSTEM_PROMPT.format(now=now_msk(), user_name=speaker, house_title=house_title),
        middleware=middleware,
        checkpointer=await get_checkpointer(),
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=f"[{speaker}]: {text}")]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT},
    )
    messages = result["messages"]
    # инструменты, вызванные в этом ходе: всё после последнего HumanMessage
    last_human = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
    turn = messages[last_human + 1 :]
    used = [m.name for m in turn if isinstance(m, ToolMessage) and m.name]
    reply = next((m for m in reversed(turn) if isinstance(m, AIMessage) and m.content), None)
    content = reply.content if reply else "Я задумался и потерял мысль. Повтори, пожалуйста?"
    if isinstance(content, list):
        content = " ".join(str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in content)
    return AgentReply(text=str(content).strip(), tools_used=used)
