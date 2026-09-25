"""Обработка апдейтов MAX. Один код для настоящего MAX и эмулятора чата."""

import re
import time
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.agent.runtime import run_agent
from domovoy.agent.tools import AgentContext
from domovoy.bot.gateway import Gateway, media_of
from domovoy.bot.identity import BOT
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.modules.events import service as events
from domovoy.modules.events.models import Event
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.catalog import category
from domovoy.modules.issues.classifier import classify_rules
from domovoy.modules.issues.models import Issue
from domovoy.modules.moderation.guardrails import moderate
from domovoy.modules.moderation.service import log_verdict
from domovoy.modules.users.membership import check_access, current_house, sync_chat
from domovoy.modules.users.models import House, Membership, User
from domovoy.modules.users.service import (
    ensure_house_for_chat,
    ensure_membership,
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
# Жалобы, на которые Кузя отвечает в общем чате без обращения к нему
PROBLEM_WORDS = (
    "не работает",
    "сломал",
    "течет",
    "течёт",
    "протека",
    "прорвал",
    "засор",
    "нет воды",
    "нет света",
    "нет горячей",
    "нет отоплен",
    "не греет",
    "застрял",
    "воняет",
    "пахнет газ",
    "запах газ",
)
HINT_COOLDOWN_SECONDS = 30 * 60


# chat_id -> время последней подсказки: не заваливаем чат одинаковыми советами
_last_hint: dict[int, float] = {}


def addressed_to_bot(text: str, body: dict[str, Any], link: dict[str, Any] | None) -> bool:
    """В общем чате Кузя отвечает, только когда к нему обращаются: по имени, @нику, упоминанием или реплаем."""
    if MENTION_RE.search(text):
        return True
    if BOT.username and f"@{BOT.username.lower()}" in text.lower():
        return True
    for mark in body.get("markup") or []:
        if mark.get("type") != "user_mention":
            continue
        if BOT.user_id is not None and int(mark.get("user_id") or 0) == BOT.user_id:
            return True
        if BOT.username and str(mark.get("user_link") or "").lstrip("@").lower() == BOT.username.lower():
            return True
    if link and link.get("type") == "reply":
        sender = link.get("sender") or {}
        if sender.get("is_bot") or (BOT.user_id is not None and int(sender.get("user_id") or 0) == BOT.user_id):
            return True
    return False


def strip_mentions(text: str, body: dict[str, Any]) -> str:
    """Убирает из текста упоминание бота, чтобы агент видел только просьбу."""
    marks = sorted(
        (m for m in body.get("markup") or [] if m.get("type") == "user_mention"),
        key=lambda m: int(m.get("from") or 0),
        reverse=True,
    )
    for m in marks:
        if BOT.user_id is not None and int(m.get("user_id") or 0) != BOT.user_id:
            continue
        start, length = int(m.get("from") or 0), int(m.get("length") or 0)
        text = text[:start] + text[start + length :]
    if BOT.username:
        text = re.sub(rf"@{re.escape(BOT.username)}\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip(" ,") or text.strip()


def _name(user: dict[str, Any]) -> str:
    return f"{user.get('first_name') or user.get('name') or ''} {user.get('last_name') or ''}".strip() or "сосед"


async def _members_and_house(session: AsyncSession, gw: Gateway, chat_id: int, title: str | None = None) -> House:
    is_new = await house_by_chat(session, chat_id) is None
    if is_new and title is None:
        title = await gw.chat_title(chat_id)
    count = await gw.members_count(chat_id)
    house = await ensure_house_for_chat(session, chat_id, title, count)
    if is_new:
        # Кузю добавили в чат раньше, чем он начал вести дома (bot_added не придёт):
        # знакомимся со всеми участниками и администраторами сразу
        await sync_chat(session, house)
    return house


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
        # пригласивший - администратор, пока MAX не сообщит точный список (sync_chat ниже)
        await ensure_membership(session, inviter, house, role="admin")
        synced = await sync_chat(session, house)
        bot_is_admin = house.bot_is_admin
        await session.commit()
    text = "Всем привет! Я Домовой Кузя, теперь живу в этом чате 🏠\n\n" + HELP_TEXT
    if bot_is_admin is False:
        text += (
            "\n\n⚙️ Администраторы, сделайте меня администратором чата: так я смогу убирать спам "
            "и узнавать соседей, чтобы дом сам появился у них в приложении."
        )
    elif synced:
        text += f"\n\nЯ познакомился с {synced} соседями: дом уже есть у каждого в приложении."
    await gw.send(chat_id=chat_id, text=text, buttons=MENU)


async def on_bot_started(update: dict[str, Any], gw: Gateway) -> None:
    user = update.get("user") or {}
    async with get_sessionmaker()() as session:
        db_user = await upsert_user(session, user)
        house = await current_house(session, db_user)
        await session.commit()
    where = f"Ваш дом: {house.title}. " if house else ""
    await gw.send(chat_id=int(update["chat_id"]), text=f"Привет, {_name(user)}! {where}" + HELP_TEXT, buttons=MENU)


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
    """Житель вышел из чата дома: закрываем ему доступ к дому в приложении."""
    async with get_sessionmaker()() as session:
        house = await _members_and_house(session, gw, int(update["chat_id"]))
        max_id = int((update.get("user") or {}).get("user_id") or 0)
        user = await session.scalar(select(User).where(User.max_user_id == max_id)) if max_id else None
        if user is not None:
            member = await session.scalar(
                select(Membership).where(Membership.user_id == user.id, Membership.house_id == house.id)
            )
            if member is not None:
                await session.delete(member)
            if user.active_house_id == house.id:
                user.active_house_id = None
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
            # пишет в чате дома - значит, сейчас он «в этом доме»: личка и приложение покажут его же
            user.active_house_id = house.id
            if await _moderate_group_message(
                session, gw, chat_id=chat_id, mid=str(body.get("mid", "")), text=text, user=user, house=house
            ):
                return
        else:
            # тот же дом, что в мини-приложении: активный, иначе первый настоящий
            dm_house = await current_house(session, user)
            if dm_house is None and get_settings().pilot_house_fallback:
                dm_house = await _default_house(session)
            if dm_house is None:
                await gw.send(chat_id=chat_id, text="Добавьте меня в чат вашего дома, и я начну помогать 🏠")
                return
            house = dm_house
            await ensure_membership(session, user, house)
        role = await check_access(session, user, house) or "resident"
        await session.commit()
        user_id, house_id, house_title, full_name = user.id, house.id, house.title, user.full_name

    low = text.lower()
    if low.startswith(("/start", "/help", "/помощь")):
        await gw.send(chat_id=chat_id, text=HELP_TEXT, buttons=MENU)
        return
    if low.startswith("/app"):
        await gw.send(chat_id=chat_id, text="Приложение дома:", buttons=MENU)
        return
    if is_group and not addressed_to_bot(text, body, message.get("link")):
        await _maybe_hint_problem(gw, chat_id=chat_id, text=text, house_id=house_id, user_id=user_id)
        return

    reply = await run_agent(
        ctx=AgentContext(user_id=user_id, house_id=house_id, is_admin=role == "admin"),
        thread_id=f"chat:{chat_id}" if is_group else f"dm:{sender.get('user_id')}",
        speaker=full_name,
        house_title=house_title,
        text=strip_mentions(text, body) if is_group else text,
    )
    buttons = _buttons_for_tools(reply.tools_used)
    await gw.send(chat_id=chat_id, text=reply.text, buttons=buttons)


async def _maybe_hint_problem(gw: Gateway, *, chat_id: int, text: str, house_id: int, user_id: int) -> None:
    """Сосед пожаловался в чате, не обращаясь к Кузе: подсказываем, как превратить жалобу в заявку.

    Если такая заявка уже есть, зовём поддержать её. Не чаще раза в полчаса на чат, газ - всегда.
    """
    low = text.lower().replace("ё", "е")
    if not any(w.replace("ё", "е") in low for w in PROBLEM_WORDS):
        return
    guess = classify_rules(text)
    now = time.monotonic()
    if guess.category != "gas" and now - _last_hint.get(chat_id, -HINT_COOLDOWN_SECONDS) < HINT_COOLDOWN_SECONDS:
        return
    _last_hint[chat_id] = now
    if guess.category == "gas":
        await gw.send(
            chat_id=chat_id,
            text=(
                "🚨 Если пахнет газом: не включайте свет и огонь, откройте окна, выйдите из подъезда "
                "и звоните **104** или **112**. Затем напишите «Кузя, пахнет газом …», и я передам заявку."
            ),
        )
        return
    async with get_sessionmaker()() as session:
        similar = await issues.similar_issues(session, house_id, user_id, text)
    if similar:
        d = similar[0]
        await gw.send(
            chat_id=chat_id,
            text=(
                f"Похоже, об этом уже есть заявка: **{d.title}** ({d.votes_count} из {d.votes_needed} голосов). "
                "Поддержите её, чтобы я быстрее отправил обращение."
            ),
            buttons=[
                [{"type": "callback", "text": "👍 Меня это тоже касается", "payload": f"vote:{d.id}"}],
                [issues.app_button("Подробнее", f"issue_{d.id}")],
            ]
            if d.status == "voting"
            else [[issues.app_button("Статус заявки", f"issue_{d.id}")]],
        )
        return
    cat = category(guess.category)
    await gw.send(
        chat_id=chat_id,
        text=(
            f"Похоже на проблему дома ({cat.title.lower()}). Сфотографируйте и отправьте заявку: "
            "соседи поддержат, и я сам отправлю обращение ответственным. "
            "Или напишите мне: «Кузя, заведи заявку: …»."
        ),
        buttons=[[issues.app_button("📸 Сообщить о проблеме", "new_issue")]],
    )


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
    source_chat = (message.get("recipient") or {}).get("chat_id")
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
                await _join_from_house_chat(session, user, issue.house, source_chat)
                is_issue_message = not issue.chat_message_id or issue.chat_message_id == mid
                issue, reached = await issues.vote(session, issue, user, from_chat=is_issue_message)
                note = (
                    "Порог набран! Отправляю обращение 📨"
                    if reached
                    else f"Голос учтён: {issue.votes_count}/{issue.votes_needed}"
                )
                buttons = issues.chat_buttons(issue)
                if is_issue_message:
                    original_text = issues.issue_chat_text(issue)
            else:
                ev = await session.get(Event, int(raw_id))
                house = await session.get(House, ev.house_id) if ev else None
                if ev is None or house is None:
                    raise HTTPException(404, "Событие не найдено")
                await _join_from_house_chat(session, user, house, source_chat)
                ev = await events.join(session, ev, user)
                note = "Записал! Напомню заранее 🙌"
                buttons = events.join_buttons(ev)
        except HTTPException as exc:
            await gw.answer_callback(callback_id=callback_id, notification=str(exc.detail))
            return
    await gw.answer_callback(callback_id=callback_id, notification=note)
    if mid:
        # фото из исходного сообщения передаём обратно: PUT /messages заменяет все вложения
        await gw.edit(mid=mid, text=original_text, buttons=buttons, media=media_of(message.get("body")) or None)


async def _join_from_house_chat(session: AsyncSession, user: User, house: House, source_chat: object) -> None:
    """Кнопка сработала в чате этого дома: нажавший - его участник. Иначе нужна уже существующая роль."""
    if source_chat is not None and int(str(source_chat)) == house.max_chat_id:
        await ensure_membership(session, user, house)
        return
    role = await session.scalar(
        select(Membership.role).where(Membership.user_id == user.id, Membership.house_id == house.id)
    )
    if role is None:
        raise HTTPException(403, "Эта кнопка для жителей другого дома")


HANDLERS = {
    "bot_added": on_bot_added,
    "bot_started": on_bot_started,
    "user_added": on_user_added,
    "user_removed": on_user_removed,
    "message_created": on_message,
    "message_callback": on_callback,
}
