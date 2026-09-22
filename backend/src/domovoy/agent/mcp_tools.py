"""Подключение MCP-серверов к агенту через клиент FastMCP.

Свой тонкий адаптер вместо langchain-mcp-adapters: последняя версия адаптера требует mcp<2,
а FastMCP 4 требует mcp>=2. Каждый MCP-инструмент превращается в StructuredTool LangChain
с JSON-схемой аргументов из MCP; вызов открывает короткую сессию к серверу.
"""

import asyncio
import ipaddress
import json
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

from fastmcp import Client
from fastmcp.client.transports import SSETransport, StreamableHttpTransport
from langchain_core.tools import BaseTool, StructuredTool

Transport = Literal["streamable_http", "sse"]
MAX_RESULT_CHARS = 4000


@dataclass(frozen=True, slots=True)
class McpConnection:
    name: str
    url: str
    transport: Transport = "streamable_http"
    headers: dict[str, str] = field(default_factory=dict)

    def client(self, timeout: float) -> Client[Any]:
        headers = self.headers or None
        if self.transport == "sse":
            return Client(SSETransport(self.url, headers=headers), timeout=timeout)
        return Client(StreamableHttpTransport(self.url, headers=headers), timeout=timeout)


class UnsafeMcpUrlError(ValueError):
    pass


async def ensure_public_url(url: str) -> None:
    """Защита от SSRF: адрес MCP-сервера из реестра не должен вести во внутреннюю сеть."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeMcpUrlError("Нужен адрес http(s)://")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or 443)
    except OSError as exc:
        raise UnsafeMcpUrlError("Адрес MCP-сервера не резолвится") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeMcpUrlError("Адреса внутренних сетей запрещены")


def _render(result: Any) -> str:
    if result.structured_content is not None:
        text = json.dumps(result.structured_content, ensure_ascii=False)
    else:
        text = "\n".join(getattr(block, "text", "") or "" for block in result.content)
    return text[:MAX_RESULT_CHARS] or "Инструмент вернул пустой ответ."


async def list_server_tools(conn: McpConnection, request_timeout: float) -> list[tuple[str, str]]:
    async with conn.client(request_timeout) as client:
        return [(t.name, t.description or "") for t in await client.list_tools()]


async def load_tools(conn: McpConnection, request_timeout: float) -> list[BaseTool]:
    async with conn.client(request_timeout) as client:
        mcp_tools = await client.list_tools()

    tools: list[BaseTool] = []
    for t in mcp_tools:
        remote_name = t.name

        async def call(_remote: str = remote_name, **kwargs: Any) -> str:
            async with conn.client(request_timeout) as client:
                result = await client.call_tool(_remote, kwargs, raise_on_error=False)
            if result.is_error:
                return f"MCP-сервер {conn.name} вернул ошибку: {_render(result)}"
            return _render(result)

        schema = t.input_schema or {"type": "object", "properties": {}}
        tools.append(
            StructuredTool(
                name=f"{conn.name}__{remote_name}"[:64],
                description=f"[MCP {conn.name}] {t.description or remote_name}",
                args_schema=schema,
                coroutine=call,
            )
        )
    return tools
