"""Обработка апдейтов MAX. Один код для настоящего MAX и эмулятора чата."""

import re
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.agent.runtime import run_agent
from domovoy.agent.tools import AgentContext
from domovoy.bot.gateway import Gateway
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.modules.events import service as events
from domovoy.modules.events.models import Event
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.models import Issue
from domovoy.modules.moderation.guardrails import moderate
from domovoy.modules.moderation.service import log_verdict
from domovoy.modules.users.models import House, Membership, User
from domovoy.modules.users.service import (
    ensure_house_for_chat,
    ensure_membership,
    first_house_of,
    house_by_chat,
    upsert_user,
)

log = structlog.get_logger(__name__)

MENU: list[list[dict[str, str]]] = [
    [{"type": "open_app", "text": "🏠 Открыть приложение дома", "payload": "home"}],
    [
        {"type": "open_app", "text": "📸 Сообщить о проблеме", "payload": "new_issue"},
        {"type": "open_app", "text": "🛡 Укрытия", "payload": "alert"},
    ],
]
HELP_TEXT = (
    "Я **Домовой Кузя**, хранитель вашего дома 🏠\n\n"
    "• сфотографируйте проблему, соседи проголосуют, и я сам отправлю обращение ответственным;\n"
    "• барахолка: отдайте или продайте вещь соседям;\n"
    "• субботники и события: напишите «Кузя, создай субботник в субботу в 11 у площадки»;\n"
    "• укрытия и оповещения о беспилотной опасности;\n"
    "• за помощь дому начисляю очки и ачивки.\n\n"
    "В общем чате обращайтесь ко мне по имени: «Кузя, какие проблемы в доме?». Грубость и рекламу я убираю."
)
MENTION_RE = re.compile(r"\bкуз[яеиюь]", re.IGNORECASE)


def _name(user: dict[str, Any]) -> str:
    return f"{user.get('first_name') or user.get('name') or ''} {user.get('last_name') or ''}".strip() or "сосед"


async def _members_and_house(session: AsyncSession, gw: Gateway, chat_id: int, title: str | None = None) -> House:
    count = await gw.members_count(chat_id)
    return await ensure_house_for_chat(session, chat_id, title, count)


async def handle_update(update: dict[str, Any], gw: Gateway) -> None:
    kind = update.get("update_type")
    handler = HANDLERS.get(kind or "")
    if handler is None:
        return
    try:
        await handler(update, gw)
    except Exception:
        log.exception("bot.update_failed", update_type=kind)


async def on_bot_added(update: dict[str, Any], gw: Gateway) -> None:
    chat_id = int(update["chat_id"])
    async with get_sessionmaker()() as session:
        house = await _members_and_house(session, gw, chat_id)
        inviter = await upsert_user(session, update.get("user") or {})
        await ensure_membership(session, inviter, house, role="admin")
        await session.commit()
    await gw.send(
        chat_id=chat_id,
        text="Всем привет! Я Домовой Кузя, теперь живу в этом чате 🏠\n\n" + HELP_TEXT,
        buttons=MENU,
    )


async def on_bot_started(update: dict[str, Any], gw: Gateway) -> None:
    user = update.get("user") or {}
    async with get_sessionmaker()() as session:
        await upsert_user(session, user)
        await session.commit()
    await gw.send(chat_id=int(update["chat_id"]), text=f"Привет, {_name(user)}! " + HELP_TEXT, buttons=MENU)


async def on_user_added(update: dict[str, Any], gw: Gateway) -> None:
    chat_id = int(update["chat_id"])
    user = update.get("user") or {}
    async with get_sessionmaker()() as session:
        house = await _members_and_house(session, gw, chat_id)
        member = await upsert_user(session, user)
        await ensure_membership(session, member, house)
        await session.commit()
    await gw.send(
        chat_id=chat_id,
        text=(
            f"Добро пожаловать, {_name(user)}! Я Кузя, домовой. "
            "Загляните в приложение дома: там проблемы, барахолка и события."
        ),
        buttons=MENU[:1],
    )


async def on_user_removed(update: dict[str, Any], gw: Gateway) -> None:
    async with get_sessionmaker()() as session:
        await _members_and_house(session, gw, int(update["chat_id"]))
        await session.commit()


async def _moderate_group_message(
    session: AsyncSession, gw: Gateway, *, chat_id: int, mid: str, text: str, user: User, house: House
) -> bool:
    """Возвращает True, если сообщение удалено модерацией."""
    verdict = await moderate(text)
    await log_verdict(session, source="chat", text=text, verdict=verdict, user_max_id=user.max_user_id, chat_id=chat_id)
    if not verdict.blocked:
        await session.commit()
        return False
    member = await ensure_membership(session, user, house)
    member.strikes += 1
    strikes, limit = member.strikes, get_settings().moderation_strikes_limit
    await session.commit()
    deleted = await gw.delete(mid=mid)
    action = "Сообщение удалено." if deleted else "Удалить не смог: дайте мне права администратора."
    warn = (
        f"⚠️ {user.full_name}, давайте общаться уважительно: {verdict.human_reason()}. {action} "
        f"Предупреждение {min(strikes, limit)}/{limit}."
    )
    if strikes >= limit:
        warn += " Лимит предупреждений исчерпан, я сообщил администраторам чата."
        await _notify_admins(
            session, gw, house, f"Житель {user.full_name} получил {strikes} предупреждения в чате дома."
        )
    await gw.send(chat_id=chat_id, text=warn)
    return True


async def _notify_admins(session: AsyncSession, gw: Gateway, house: House, text: str) -> None:
    admins = await session.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.house_id == house.id, Membership.role == "admin")
    )
    for admin in admins:
        await gw.send(user_id=admin.max_user_id, text=f"🛡 {text}")


async def on_message(update: dict[str, Any], gw: Gateway) -> None:
    message = update.get("message") or {}
    sender = message.get("sender") or {}
    if not sender or sender.get("is_bot"):
        return
    recipient = message.get("recipient") or {}
    body = message.get("body") or {}
    text: str = (body.get("text") or "").strip()
    chat_id = recipient.get("chat_id")
    is_group = recipient.get("chat_type") == "chat"
    if chat_id is None or not text:
        return
    chat_id = int(chat_id)

    async with get_sessionmaker()() as session:
        user = await upsert_user(session, sender)
        if is_group:
            house = await house_by_chat(session, chat_id) or await _members_and_house(session, gw, chat_id)
            await ensure_membership(session, user, house)
            if await _moderate_group_message(
                session, gw, chat_id=chat_id, mid=str(body.get("mid", "")), text=text, user=user, house=house
            ):
                return
        else:
            dm_house = await first_house_of(session, user) or await _default_house(session)
            if dm_house is None:
                await gw.send(chat_id=chat_id, text="Добавьте меня в чат вашего дома, и я начну помогать 🏠")
                return
            house = dm_house
            await ensure_membership(session, user, house)
            await session.commit()
        user_id, house_id, house_title, full_name = user.id, house.id, house.title, user.full_name

    low = text.lower()
    if low.startswith(("/start", "/help", "/помощь")):
        await gw.send(chat_id=chat_id, text=HELP_TEXT, buttons=MENU)
        return
    if low.startswith("/app"):
        await gw.send(chat_id=chat_id, text="Приложение дома:", buttons=MENU)
        return
    if is_group and not MENTION_RE.search(text) and "@" + get_settings().max_bot_username not in low:
        return  # в общем чате отвечаем только когда обращаются к Кузе

    reply = await run_agent(
        ctx=AgentContext(user_id=user_id, house_id=house_id),
        thread_id=f"chat:{chat_id}" if is_group else f"dm:{sender.get('user_id')}",
        speaker=full_name,
        house_title=house_title,
        text=text,
    )
    buttons = _buttons_for_tools(reply.tools_used)
    await gw.send(chat_id=chat_id, text=reply.text, buttons=buttons)


async def _default_house(session: AsyncSession) -> House | None:
    return await session.scalar(select(House).order_by(House.id).limit(1))


def _buttons_for_tools(tools: list[str]) -> list[list[dict[str, str]]] | None:
    mapping = {
        "list_issues": ("📋 Все проблемы", "issues"),
        "create_issue": ("📋 Заявка в приложении", "issues"),
        "list_events": ("📅 События", "events"),
        "create_event": ("📅 Открыть событие", "events"),
        "list_listings": ("🛍 Барахолка", "market"),
        "nearest_shelters": ("🛡 Карта укрытий", "alert"),
        "my_profile": ("🏆 Мои ачивки", "achievements"),
    }
    for name in tools:
        if name in mapping:
            text, payload = mapping[name]
            return [[{"type": "open_app", "text": text, "payload": payload}]]
    return None


async def on_callback(update: dict[str, Any], gw: Gateway) -> None:
    cb = update.get("callback") or {}
    payload: str = cb.get("payload") or ""
    callback_id: str = cb.get("callback_id") or ""
    message = update.get("message") or {}
    mid = (message.get("body") or {}).get("mid")
    original_text = (message.get("body") or {}).get("text")
    action, _, raw_id = payload.partition(":")
    if action not in ("vote", "join") or not raw_id.isdigit():
        await gw.answer_callback(callback_id=callback_id, notification="Кнопка устарела")
        return

    async with get_sessionmaker()() as session:
        user = await upsert_user(session, cb.get("user") or {})
        await session.commit()
        try:
            if action == "vote":
                issue = await session.get(Issue, int(raw_id))
                if issue is None:
                    raise HTTPException(404, "Заявка не найдена")
                await ensure_membership(session, user, issue.house)
                issue, reached = await issues.vote(session, issue, user)
                note = (
                    "Порог набран! Отправляю обращение 📨"
                    if reached
                    else f"Голос учтён: {issue.votes_count}/{issue.votes_needed}"
                )
                buttons = (
                    issues.vote_buttons(issue)
                    if issue.status == "voting"
                    else [[issues.app_button("Статус заявки", f"issue_{issue.id}")]]
                )
            else:
                ev = await session.get(Event, int(raw_id))
                if ev is None:
                    raise HTTPException(404, "Событие не найдено")
                await ensure_membership(session, user, await session.get(House, ev.house_id))  # type: ignore[arg-type]
                ev = await events.join(session, ev, user)
                note = "Записал! Напомню заранее 🙌"
                buttons = events.join_buttons(ev)
        except HTTPException as exc:
            await gw.answer_callback(callback_id=callback_id, notification=str(exc.detail))
            return
    await gw.answer_callback(callback_id=callback_id, notification=note)
    if mid:
        await gw.edit(mid=mid, text=original_text, buttons=buttons)


HANDLERS = {
    "bot_added": on_bot_added,
    "bot_started": on_bot_started,
    "user_added": on_user_added,
    "user_removed": on_user_removed,
    "message_created": on_message,
    "message_callback": on_callback,
}
