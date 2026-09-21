"""Шлюзы отправки: настоящий MAX и эмулятор чата. Обработчики не знают, с каким работают."""

from typing import Any, Protocol

import structlog

from domovoy.bot.max_client import MaxClient
from domovoy.core import bus
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.modules.devchat import service as devchat

log = structlog.get_logger(__name__)

Buttons = list[list[dict[str, str]]]


class Gateway(Protocol):
    async def send(
        self, *, text: str, chat_id: int | None = None, user_id: int | None = None, buttons: Buttons | None = None
    ) -> str | None: ...

    async def edit(self, *, mid: str, text: str | None, buttons: Buttons) -> None: ...

    async def delete(self, *, mid: str) -> bool: ...

    async def answer_callback(self, *, callback_id: str, notification: str) -> None: ...

    async def members_count(self, chat_id: int) -> int | None: ...


def deep_link(payload: str) -> str:
    return f"https://max.ru/{get_settings().max_bot_username}?startapp={payload}"


def to_max_keyboard(buttons: Buttons | None) -> list[dict[str, Any]] | None:
    """Внутренний формат кнопок → inline_keyboard MAX. Кнопка мини-приложения идёт диплинком startapp."""
    if not buttons:
        return None
    rows: list[list[dict[str, Any]]] = []
    for row in buttons:
        out: list[dict[str, Any]] = []
        for b in row:
            if b["type"] == "callback":
                out.append({"type": "callback", "text": b["text"], "payload": b["payload"]})
            elif b["type"] == "open_app":
                out.append({"type": "link", "text": b["text"], "url": deep_link(b["payload"])})
            elif b["type"] == "link":
                out.append({"type": "link", "text": b["text"], "url": b["url"]})
        if out:
            rows.append(out)
    return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]


class MaxGateway:
    def __init__(self, client: MaxClient) -> None:
        self.client = client

    async def send(
        self, *, text: str, chat_id: int | None = None, user_id: int | None = None, buttons: Buttons | None = None
    ) -> str | None:
        return await self.client.send_message(
            text=text, chat_id=chat_id, user_id=user_id, attachments=to_max_keyboard(buttons)
        )

    async def edit(self, *, mid: str, text: str | None, buttons: Buttons) -> None:
        if text is None:
            return
        await self.client.edit_message(mid, text, to_max_keyboard(buttons))

    async def delete(self, *, mid: str) -> bool:
        try:
            await self.client.delete_message(mid)
            return True
        except Exception:
            log.warning("bot.delete_failed", mid=mid, exc_info=True)
            return False

    async def answer_callback(self, *, callback_id: str, notification: str) -> None:
        await self.client.answer_callback(callback_id, notification)

    async def members_count(self, chat_id: int) -> int | None:
        try:
            return int((await self.client.get_chat(chat_id)).get("participants_count") or 0) or None
        except Exception:
            log.warning("bot.chat_info_failed", chat_id=chat_id, exc_info=True)
            return None


class MockGateway:
    """Отправка в эмулятор чата. Личка с пользователем = чат с id, равным его max_user_id."""

    async def send(
        self, *, text: str, chat_id: int | None = None, user_id: int | None = None, buttons: Buttons | None = None
    ) -> str | None:
        target = chat_id if chat_id is not None else user_id
        if target is None:
            return None
        async with get_sessionmaker()() as session:
            msg = await devchat.store(session, chat_id=target, text=text, buttons=buttons)
            return devchat.mid_of(msg)

    async def edit(self, *, mid: str, text: str | None, buttons: Buttons) -> None:
        fields: dict[str, Any] = {"buttons": buttons}
        if text is not None:
            fields["text"] = text
        async with get_sessionmaker()() as session:
            await devchat.update(session, mid, **fields)

    async def delete(self, *, mid: str) -> bool:
        async with get_sessionmaker()() as session:
            return (
                await devchat.update(session, mid, deleted=True, notice="Сообщение удалено модератором Кузей")
            ) is not None

    async def answer_callback(self, *, callback_id: str, notification: str) -> None:
        # в MAX это всплывающее уведомление; в эмуляторе показываем тост через SSE
        await bus.emit(None, "chat.notice", {"callback_id": callback_id, "text": notification})

    async def members_count(self, chat_id: int) -> int | None:
        return None
