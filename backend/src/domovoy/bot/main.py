"""Процесс бота: long polling MAX + очереди RabbitMQ (исходящие сообщения и апдейты эмулятора)."""

import asyncio
from typing import Any

import structlog
from sqlalchemy import select

from domovoy.bot.gateway import Gateway, MaxGateway, MockGateway
from domovoy.bot.handlers import handle_update
from domovoy.bot.identity import BOT
from domovoy.bot.max_client import MaxApiError, MaxClient
from domovoy.core import aio
from domovoy.core.bus import EXCHANGE, Q_BOT_INBOUND, Q_BOT_ISSUE_REFRESH, Q_BOT_SEND, get_broker
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker, init_db
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.models import Issue
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
        me = await self.client.me()
        # ник и id бота нужны, чтобы узнавать упоминания @бота в общем чате
        BOT.user_id = int(me.get("user_id") or 0) or None
        BOT.username = me.get("username") or BOT.username
        if BOT.username != get_settings().max_bot_username:
            log.warning("bot.username_mismatch", actual=BOT.username, configured=get_settings().max_bot_username)
        log.info("bot.polling_started", username=BOT.username, user_id=BOT.user_id)
        marker: int | None = None
        while True:
            try:
                updates, marker = await self.client.get_updates(marker)
            except (MaxApiError, OSError) as exc:
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
        chat_id = cmd.get("chat_id")
        gw = await runtime.target_gateway(chat_id, cmd.get("user_id"))
        try:
            mid = await gw.send(
                text=cmd["text"],
                chat_id=chat_id,
                user_id=cmd.get("user_id"),
                buttons=cmd.get("buttons"),
                photos=cmd.get("photos") or [],
            )
        except MaxApiError:
            log.exception("bot.send_failed", chat_id=chat_id, user_id=cmd.get("user_id"))
            return
        if mid and chat_id is not None and cmd.get("pin"):
            await gw.pin(chat_id=int(chat_id), mid=mid)
        issue_id = (cmd.get("ref") or {}).get("issue_id")
        if mid and issue_id:
            # запоминаем сообщение заявки: голоса из приложения обновят в нём счётчик
            async with get_sessionmaker()() as session:
                issue = await session.get(Issue, int(issue_id))
                if issue is not None:
                    issue.chat_message_id = mid
                    await session.commit()

    @broker.subscriber(Q_BOT_ISSUE_REFRESH, EXCHANGE)
    async def on_issue_refresh(cmd: dict[str, Any]) -> None:
        async with get_sessionmaker()() as session:
            issue = await session.get(Issue, int(cmd["issue_id"]))
        if issue is None or not issue.chat_message_id or not issue.house.max_chat_id:
            return
        gw = await runtime.target_gateway(issue.house.max_chat_id, None)
        try:
            await gw.edit(
                mid=issue.chat_message_id, text=issues.issue_chat_text(issue), buttons=issues.chat_buttons(issue)
            )
        except MaxApiError:
            log.warning("bot.issue_refresh_failed", issue_id=issue.id, exc_info=True)

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
