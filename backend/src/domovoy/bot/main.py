"""Процесс бота: long polling MAX + очереди RabbitMQ (исходящие сообщения и апдейты эмулятора)."""

import asyncio
from typing import Any

import httpx
import structlog
from sqlalchemy import select

from domovoy.bot.gateway import Gateway, MaxGateway, MockGateway
from domovoy.bot.handlers import handle_update
from domovoy.bot.max_client import MaxApiError, MaxClient
from domovoy.core import aio
from domovoy.core.bus import EXCHANGE, Q_BOT_INBOUND, Q_BOT_SEND, get_broker
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker, init_db
from domovoy.modules.users.models import House, User

log = structlog.get_logger(__name__)

MAX_CONCURRENT_UPDATES = 8
POLL_ERROR_BACKOFF = 5


class BotRuntime:
    def __init__(self) -> None:
        s = get_settings()
        self.mock = MockGateway()
        self.client = MaxClient(s.max_api_url, s.bot_token, s.max_poll_timeout) if s.has_max_token else None
        self.max: Gateway | None = MaxGateway(self.client) if self.client else None
        self.sem = asyncio.Semaphore(MAX_CONCURRENT_UPDATES)
        self.tasks: set[asyncio.Task[None]] = set()

    def spawn(self, update: dict[str, Any], gw: Gateway) -> None:
        async def run() -> None:
            async with self.sem:
                await handle_update(update, gw)

        task = asyncio.create_task(run())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def target_gateway(self, chat_id: int | None, user_id: int | None) -> Gateway:
        """Демо-чаты и демо-жители обслуживаются эмулятором, остальные настоящим MAX."""
        async with get_sessionmaker()() as session:
            if chat_id is not None:
                is_demo = await session.scalar(select(House.is_demo).where(House.max_chat_id == chat_id))
                if is_demo is None:
                    is_demo = bool(await session.scalar(select(User.is_demo).where(User.max_user_id == chat_id)))
            else:
                is_demo = bool(await session.scalar(select(User.is_demo).where(User.max_user_id == user_id)))
        if is_demo or self.max is None:
            return self.mock
        return self.max

    async def poll(self) -> None:
        assert self.client is not None
        while True:
            try:
                me = await self.client.me()
            except (MaxApiError, OSError, httpx.TransportError) as exc:
                log.warning("bot.poll_error", error=str(exc))
                await asyncio.sleep(POLL_ERROR_BACKOFF)
                continue
            break
        log.info("bot.polling_started", username=me.get("username"))
        marker: int | None = None
        while True:
            try:
                updates, marker = await self.client.get_updates(marker)
            except (MaxApiError, OSError, httpx.TransportError) as exc:
                log.warning("bot.poll_error", error=str(exc))
                await asyncio.sleep(POLL_ERROR_BACKOFF)
                continue
            for update in updates:
                self.spawn(update, self.max)  # type: ignore[arg-type]


async def main() -> None:
    settings = get_settings()
    await init_db()
    runtime = BotRuntime()
    broker = get_broker()

    @broker.subscriber(Q_BOT_SEND, EXCHANGE)
    async def on_send(cmd: dict[str, Any]) -> None:
        gw = await runtime.target_gateway(cmd.get("chat_id"), cmd.get("user_id"))
        try:
            await gw.send(
                text=cmd["text"], chat_id=cmd.get("chat_id"), user_id=cmd.get("user_id"), buttons=cmd.get("buttons")
            )
        except MaxApiError:
            log.exception("bot.send_failed", chat_id=cmd.get("chat_id"), user_id=cmd.get("user_id"))

    @broker.subscriber(Q_BOT_INBOUND, EXCHANGE)
    async def on_inbound(update: dict[str, Any]) -> None:
        runtime.spawn(update, runtime.mock)

    await broker.start()
    log.info("bot.started", mock=settings.mock_max, max_token=settings.has_max_token)
    try:
        if runtime.client is not None:
            await runtime.poll()
        else:
            log.warning("bot.no_token", hint="MAX_BOT_TOKEN не задан: работает только эмулятор чата")
            await asyncio.Event().wait()
    finally:
        await broker.stop()
        if runtime.client is not None:
            await runtime.client.close()


def run() -> None:
    aio.run(main())
