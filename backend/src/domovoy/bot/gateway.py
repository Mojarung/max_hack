"""Шлюзы отправки: настоящий MAX и эмулятор чата. Обработчики не знают, с каким работают."""

from typing import Any, Protocol

import structlog

from domovoy.bot.identity import BOT
from domovoy.bot.max_client import MaxApiError, MaxClient
from domovoy.core import bus
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.core.storage import media_url, read_object
from domovoy.modules.devchat import service as devchat

log = structlog.get_logger(__name__)

Buttons = list[list[dict[str, str]]]
# Вложения-медиа сообщения MAX (фото), которые надо сохранить при редактировании
Media = list[dict[str, Any]]
MAX_PHOTOS_IN_CHAT = 3


class Gateway(Protocol):
    async def send(
        self,
        *,
        text: str,
        chat_id: int | None = None,
        user_id: int | None = None,
        buttons: Buttons | None = None,
        photos: list[str] | None = None,
    ) -> str | None: ...

    async def edit(self, *, mid: str, text: str | None, buttons: Buttons, media: Media | None = None) -> None: ...

    async def pin(self, *, chat_id: int, mid: str) -> bool: ...

    async def delete(self, *, mid: str) -> bool: ...

    async def answer_callback(self, *, callback_id: str, notification: str) -> None: ...

    async def members_count(self, chat_id: int) -> int | None: ...

    async def chat_title(self, chat_id: int) -> str | None: ...


def deep_link(payload: str) -> str:
    return f"https://max.ru/{get_settings().max_bot_username}?startapp={payload}"


def media_of(message_body: dict[str, Any] | None) -> Media:
    """Фото из тела сообщения MAX в виде, пригодном для повторной отправки при редактировании."""
    out: Media = []
    for att in (message_body or {}).get("attachments") or []:
        if att.get("type") != "image":
            continue
        payload = att.get("payload") or {}
        if payload.get("token"):
            out.append({"type": "image", "payload": {"token": payload["token"]}})
        elif payload.get("url"):
            out.append({"type": "image", "payload": {"url": payload["url"]}})
    return out


def to_max_keyboard(buttons: Buttons | None, *, native_app: bool = True) -> list[dict[str, Any]] | None:
    """Внутренний формат кнопок → inline_keyboard MAX.

    Кнопка мини-приложения - нативная `open_app` (ник и id бота + payload = start_param), она открывает
    приложение внутри MAX. native_app=False или неизвестный id бота: диплинк https://max.ru/<бот>?startapp=...
    """
    if not buttons:
        return None
    native_app = native_app and BOT.user_id is not None and bool(BOT.username)
    rows: list[list[dict[str, Any]]] = []
    for row in buttons:
        out: list[dict[str, Any]] = []
        for b in row:
            if b["type"] == "callback":
                out.append({"type": "callback", "text": b["text"], "payload": b["payload"]})
            elif b["type"] == "open_app" and native_app:
                out.append(
                    {
                        "type": "open_app",
                        "text": b["text"],
                        "web_app": BOT.username,
                        "contact_id": BOT.user_id,
                        "payload": b["payload"],
                    }
                )
            elif b["type"] == "open_app":
                out.append({"type": "link", "text": b["text"], "url": deep_link(b["payload"])})
            elif b["type"] == "link":
                out.append({"type": "link", "text": b["text"], "url": b["url"]})
        if out:
            rows.append(out)
    return [{"type": "inline_keyboard", "payload": {"buttons": rows}}]


def _has_app_button(buttons: Buttons | None) -> bool:
    return any(b.get("type") == "open_app" for row in buttons or [] for b in row)


class MaxGateway:
    def __init__(self, client: MaxClient) -> None:
        self.client = client

    async def send(
        self,
        *,
        text: str,
        chat_id: int | None = None,
        user_id: int | None = None,
        buttons: Buttons | None = None,
        photos: list[str] | None = None,
    ) -> str | None:
        attachments: list[dict[str, Any]] = []
        for key in (photos or [])[:MAX_PHOTOS_IN_CHAT]:
            try:
                payload = await self.client.upload_image(await read_object(key))
                attachments.append({"type": "image", "payload": payload})
            except Exception:
                # без фото сообщение всё равно важнее: голосование не должно потеряться
                log.warning("bot.photo_upload_failed", key=key, exc_info=True)
        try:
            return await self.client.send_message(
                text=text,
                chat_id=chat_id,
                user_id=user_id,
                attachments=(attachments + (to_max_keyboard(buttons) or [])) or None,
            )
        except MaxApiError as exc:
            if exc.status != 400 or not _has_app_button(buttons):
                raise
            # MAX не принял кнопку open_app (например, у бота не настроено мини-приложение): шлём диплинком
            log.warning("bot.open_app_rejected", error=str(exc))
            return await self.client.send_message(
                text=text,
                chat_id=chat_id,
                user_id=user_id,
                attachments=(attachments + (to_max_keyboard(buttons, native_app=False) or [])) or None,
            )

    async def edit(self, *, mid: str, text: str | None, buttons: Buttons, media: Media | None = None) -> None:
        if media is None or text is None:
            # PUT /messages заменяет все вложения: забираем фото и текст исходного сообщения, чтобы их не потерять
            try:
                body = (await self.client.get_message(mid)).get("body") or {}
            except Exception:
                log.warning("bot.get_message_failed", mid=mid, exc_info=True)
                body = {}
            media = media if media is not None else media_of(body)
            text = text if text is not None else body.get("text")
        if text is None:
            return
        try:
            await self.client.edit_message(mid, text, media + (to_max_keyboard(buttons) or []))
        except MaxApiError as exc:
            if exc.status != 400 or not _has_app_button(buttons):
                raise
            await self.client.edit_message(mid, text, media + (to_max_keyboard(buttons, native_app=False) or []))

    async def pin(self, *, chat_id: int, mid: str) -> bool:
        try:
            await self.client.pin_message(chat_id, mid)
            return True
        except Exception:
            log.warning("bot.pin_failed", chat_id=chat_id, exc_info=True)
            return False

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

    async def chat_title(self, chat_id: int) -> str | None:
        try:
            return str((await self.client.get_chat(chat_id)).get("title") or "").strip() or None
        except Exception:
            log.warning("bot.chat_info_failed", chat_id=chat_id, exc_info=True)
            return None


class MockGateway:
    """Отправка в эмулятор чата. Личка с пользователем = чат с id, равным его max_user_id."""

    async def send(
        self,
        *,
        text: str,
        chat_id: int | None = None,
        user_id: int | None = None,
        buttons: Buttons | None = None,
        photos: list[str] | None = None,
    ) -> str | None:
        target = chat_id if chat_id is not None else user_id
        if target is None:
            return None
        async with get_sessionmaker()() as session:
            msg = await devchat.store(
                session,
                chat_id=target,
                text=text,
                buttons=buttons,
                photos=[media_url(k) for k in (photos or [])[:MAX_PHOTOS_IN_CHAT]],
            )
            return devchat.mid_of(msg)

    async def pin(self, *, chat_id: int, mid: str) -> bool:
        async with get_sessionmaker()() as session:
            return (await devchat.update(session, mid, notice="📌 Закреплено Кузей")) is not None

    async def edit(self, *, mid: str, text: str | None, buttons: Buttons, media: Media | None = None) -> None:
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

    async def chat_title(self, chat_id: int) -> str | None:
        return None
