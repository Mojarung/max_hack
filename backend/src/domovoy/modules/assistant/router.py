"""Чат с Кузей внутри мини-приложения и реестр MCP-серверов агента."""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select

from domovoy.agent.mcp_tools import McpConnection, Transport, UnsafeMcpUrlError, ensure_public_url, list_server_tools
from domovoy.agent.runtime import MCP_TIMEOUT_SECONDS, invalidate_mcp_cache, run_agent
from domovoy.agent.tools import AgentContext
from domovoy.api.deps import CtxDep, SessionDep, require_admin
from domovoy.core.config import get_settings
from domovoy.modules.misc_models import McpServer
from domovoy.modules.moderation.guardrails import moderate

router = APIRouter(tags=["Ассистент и MCP"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatOut(BaseModel):
    reply: str
    tools_used: list[str]


class McpServerIn(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    transport: Literal["streamable_http", "sse"] = "streamable_http"
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)


class McpServerOut(BaseModel):
    id: int
    name: str
    transport: str
    url: str
    enabled: bool
    has_headers: bool


class McpToolOut(BaseModel):
    name: str
    description: str


async def _check_url(url: str) -> None:
    if get_settings().mcp_allow_private_urls:
        return
    try:
        await ensure_public_url(url)
    except UnsafeMcpUrlError as exc:
        raise HTTPException(422, str(exc)) from exc


def mcp_out(s: McpServer) -> McpServerOut:
    return McpServerOut(
        id=s.id, name=s.name, transport=s.transport, url=s.url, enabled=s.enabled, has_headers=bool(s.headers)
    )


@router.post("/assistant/chat", response_model=ChatOut)
async def chat(body: ChatIn, ctx: CtxDep) -> ChatOut:
    verdict = await moderate(body.message)
    if verdict.blocked:
        return ChatOut(
            reply=f"Давай общаться вежливо 🙏 Я не могу ответить на такое ({verdict.human_reason()}).", tools_used=[]
        )
    reply = await run_agent(
        ctx=AgentContext(user_id=ctx.user.id, house_id=ctx.house.id, is_admin=ctx.is_admin),
        thread_id=f"app:{ctx.house.id}:{ctx.user.id}",
        speaker=ctx.user.full_name,
        house_title=ctx.house.title,
        text=body.message,
    )
    return ChatOut(reply=reply.text, tools_used=reply.tools_used)


@router.get("/mcp/servers", response_model=list[McpServerOut])
async def list_servers(session: SessionDep, ctx: CtxDep) -> list[McpServerOut]:
    require_admin(ctx)
    return [mcp_out(s) for s in await session.scalars(select(McpServer).order_by(McpServer.id))]


@router.post("/mcp/servers", response_model=McpServerOut, status_code=201)
async def add_server(body: McpServerIn, session: SessionDep, ctx: CtxDep) -> McpServerOut:
    require_admin(ctx)
    if await session.scalar(select(McpServer).where(McpServer.name == body.name)):
        raise HTTPException(409, "Сервер с таким именем уже есть")
    await _check_url(str(body.url))
    srv = McpServer(name=body.name, transport=body.transport, url=str(body.url), headers=body.headers)
    session.add(srv)
    await session.commit()
    await session.refresh(srv)
    invalidate_mcp_cache()
    return mcp_out(srv)


@router.delete("/mcp/servers/{server_id}", status_code=204)
async def delete_server(server_id: int, session: SessionDep, ctx: CtxDep) -> Response:
    require_admin(ctx)
    srv = await session.get(McpServer, server_id)
    if srv is None:
        raise HTTPException(404, "Сервер не найден")
    await session.delete(srv)
    await session.commit()
    invalidate_mcp_cache()
    return Response(status_code=204)


@router.get("/mcp/servers/{server_id}/tools", response_model=list[McpToolOut])
async def server_tools(server_id: int, session: SessionDep, ctx: CtxDep) -> list[McpToolOut]:
    require_admin(ctx)
    srv = await session.get(McpServer, server_id)
    if srv is None:
        raise HTTPException(404, "Сервер не найден")
    transport: Transport = "sse" if srv.transport == "sse" else "streamable_http"
    await _check_url(srv.url)
    conn = McpConnection(name=srv.name, url=srv.url, transport=transport, headers=srv.headers or {})
    try:
        tools = await asyncio.wait_for(list_server_tools(conn, MCP_TIMEOUT_SECONDS), MCP_TIMEOUT_SECONDS)
    except Exception as exc:
        raise HTTPException(502, "MCP-сервер недоступен или ответил ошибкой") from exc
    return [McpToolOut(name=name, description=desc) for name, desc in tools]
