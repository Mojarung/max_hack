"""Основные возможности Кузи прямо в чате MAX, без мини-приложения.

Меню на кнопках-колбэках, подача заявки с фото и подтверждением, карточка заявки со сроком
и текстом обращения, смена статуса, списки заявок, событий, вещей, укрытия, профиль и выбор дома.
Черновик заявки живёт в памяти процесса бота (один процесс на все чаты) и сбрасывается через 30 минут.
"""

import base64
import ipaddress
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.bot.gateway import Buttons, Gateway
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.core.storage import save_bytes
from domovoy.modules.achievements.catalog import ACHIEVEMENTS, level_for
from domovoy.modules.events import service as events
from domovoy.modules.events.models import Event
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.catalog import OPEN_STATUSES, STATUS_TITLES, category
from domovoy.modules.issues.classifier import classify
from domovoy.modules.issues.models import Issue, IssueUpdate
from domovoy.modules.market import service as market
from domovoy.modules.misc_models import UserAchievement
from domovoy.modules.safety import service as safety
from domovoy.modules.users.membership import check_access, current_house, my_houses
from domovoy.modules.users.models import House, Membership, User

log = structlog.get_logger(__name__)

# Время в сообщениях Кузи - московское с пометкой «МСК», как в уведомлениях воркера (worker/main.py)
MSK = ZoneInfo("Europe/Moscow")
DRAFT_TTL_S = 30 * 60
MAX_DRAFT_PHOTOS = 5
MAX_PHOTO_BYTES = 10 * 1024 * 1024
LIST_LIMIT = 8

STATUS_ICON = {"voting": "✋", "sent": "📨", "in_progress": "🔧", "resolved": "✅", "rejected": "✖️"}


@dataclass
class Draft:
    """Черновик заявки: житель пишет текст и шлёт фото, Кузя показывает карточку для подтверждения."""

    house_id: int
    stage: str = "text"  # text - ждём описание, confirm - показали карточку
    text: str = ""
    photos: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)


# (чат, MAX id жителя) -> черновик
_drafts: dict[tuple[int, int], Draft] = {}
# (житель, объявление) -> когда последний раз писали продавцу: кнопку не превратить в спам
_last_contact: dict[tuple[int, int], float] = {}
CONTACT_COOLDOWN_S = 10 * 60


@dataclass
class Who:
    """Кто нажал кнопку или написал: житель, его дом и роль, где ответить."""

    user: User
    house: House
    is_admin: bool
    chat_id: int
    is_group: bool


def button(text: str, payload: str) -> dict[str, str]:
    return {"type": "callback", "text": text, "payload": payload}


def main_menu(*, dm: bool) -> Buttons:
    """В личке полное меню; в чате дома короткое, чтобы личные списки не засоряли общий чат."""
    if not dm:
        return [
            [button("📸 Сообщить о проблеме", "menu:report")],
            [button("📋 Заявки дома", "menu:issues"), button("📅 События", "menu:events")],
            [button("🛡 Укрытия", "menu:shelters")],
            [issues.app_button("🏠 Приложение дома", "home")],
        ]
    return [
        [button("📸 Сообщить о проблеме", "menu:report")],
        [button("📋 Заявки дома", "menu:issues"), button("🗂 Мои заявки", "menu:mine")],
        [button("📅 События", "menu:events"), button("🛍 Вещи соседей", "menu:market")],
        [button("🛡 Укрытия", "menu:shelters"), button("🏆 Профиль", "menu:profile")],
        [button("🏘 Мой дом", "menu:houses")],
        [issues.app_button("🏠 Приложение дома", "home")],
    ]


COMMANDS = {
    "/меню": "menu",
    "/menu": "menu",
    "меню": "menu",
    "/проблемы": "issues",
    "/заявки": "issues",
    "/мои": "mine",
    "/новая": "report",
    "/заявка": "report",
    "/сообщить": "report",
    "/события": "events",
    "/вещи": "market",
    "/барахолка": "market",
    "/укрытия": "shelters",
    "/профиль": "profile",
    "/дом": "houses",
    "/дома": "houses",
}


def command_of(text: str) -> str | None:
    word = text.strip().split(maxsplit=1)[0].lower() if text.strip() else ""
    word = word.split("@", 1)[0]
    return COMMANDS.get(word)


# ---------- форматирование ----------


def fmt_hours(hours: int) -> str:
    if hours < 24:
        return f"{hours} {_plural(hours, 'час', 'часа', 'часов')}"
    days = hours // 24
    return f"{days} {_plural(days, 'сутки', 'суток', 'суток')}" if days < 30 else f"{days} дней"


def fmt_dt(value: datetime) -> str:
    return value.astimezone(MSK).strftime("%d.%m в %H:%M МСК")


def fmt_left(deadline: datetime) -> str:
    left = deadline - datetime.now(UTC)
    hours = int(abs(left).total_seconds() // 3600)
    span = f"{hours} ч" if hours < 48 else f"{hours // 24} дн"
    return f"осталось {span}" if left.total_seconds() > 0 else f"просрочено на {span}"


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# ---------- фото из сообщения ----------


def image_urls(body: dict[str, Any]) -> list[str]:
    """Ссылки на фото из вложений сообщения MAX (в эмуляторе - data:-ссылки)."""
    out = []
    for att in body.get("attachments") or []:
        if att.get("type") == "image":
            url = (att.get("payload") or {}).get("url")
            if url:
                out.append(str(url))
    return out


def _allowed_url(url: str) -> bool:
    """Фото качаем только по https с публичного хоста: никаких localhost и адресов внутренней сети."""
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return False
    host = (parsed.host or "").lower()
    if parsed.scheme != "https" or not host or host == "localhost" or host.endswith((".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host  # доменное имя, не голый адрес


async def _download(url: str) -> bytes | None:
    try:
        if url.startswith("data:image/"):
            # data:-ссылки шлёт только эмулятор чата; от настоящего MAX их не принимаем
            if not get_settings().mock_max or len(url) > MAX_PHOTO_BYTES * 4 // 3 + 100:
                return None
            return base64.b64decode(url.split(",", 1)[1])
        if not _allowed_url(url):
            return None
        async with (
            httpx.AsyncClient(timeout=20, follow_redirects=False) as client,
            client.stream("GET", url) as resp,
        ):
            resp.raise_for_status()
            chunks, size = [], 0
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > MAX_PHOTO_BYTES:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
    except Exception:
        log.warning("chat.photo_download_failed", exc_info=True)
        return None


async def store_photos(urls: list[str], house_id: int) -> list[str]:
    keys = []
    for url in urls[:MAX_DRAFT_PHOTOS]:
        raw = await _download(url)
        if raw is None:
            continue
        try:
            keys.append(await save_bytes(f"issues/{house_id}", raw))
        except Exception:
            # нечитаемое фото или недоступно хранилище: заявку всё равно можно подать без него
            log.warning("chat.photo_store_failed", exc_info=True)
    return keys


# ---------- кто нажал ----------


async def resolve(session: AsyncSession, user: User, chat_id: int, is_group: bool) -> Who | None:
    """Дом жителя: в чате дома - этот дом, в личке - выбранный (как в мини-приложении)."""
    house: House | None
    if is_group:
        house = await session.scalar(select(House).where(House.max_chat_id == chat_id))
    else:
        house = await current_house(session, user)
    if house is None:
        return None
    role = await check_access(session, user, house)
    if role is None:
        return None
    return Who(user=user, house=house, is_admin=role == "admin", chat_id=chat_id, is_group=is_group)


# ---------- подача заявки ----------


def has_draft(chat_id: int, max_user_id: int) -> bool:
    draft = _drafts.get((chat_id, max_user_id))
    if draft and time.monotonic() - draft.started > DRAFT_TTL_S:
        _drafts.pop((chat_id, max_user_id), None)
        return False
    return draft is not None


def _purge_drafts() -> None:
    now = time.monotonic()
    for key in [k for k, d in _drafts.items() if now - d.started > DRAFT_TTL_S]:
        _drafts.pop(key, None)


def draft_wants(chat_id: int, max_user_id: int, *, has_photos: bool) -> bool:
    """Черновик ждёт сообщение: описание (стадия text) или фото. Карточка уже показана - текст идёт мимо."""
    if not has_draft(chat_id, max_user_id):
        return False
    return has_photos or _drafts[(chat_id, max_user_id)].stage == "text"


async def start_report(gw: Gateway, who: Who) -> None:
    _purge_drafts()
    _drafts[(who.chat_id, who.user.max_user_id)] = Draft(house_id=who.house.id)
    ask = (
        "Ответьте на это сообщение: что случилось и где?"
        if who.is_group
        else "Напишите одним сообщением, что случилось и где."
    )
    await gw.send(
        chat_id=who.chat_id,
        text=(f"📸 {ask} Можно приложить до пяти фото.\n\nНапример: «Течёт крыша над 9 этажом во втором подъезде»."),
        buttons=[[button("✖️ Отмена", "report:cancel")]],
    )


async def draft_message(gw: Gateway, who: Who, text: str, photo_urls: list[str]) -> None:
    """Сообщение жителя, у которого открыт черновик: описание, фото или исправленный текст."""
    draft = _drafts[(who.chat_id, who.user.max_user_id)]
    if photo_urls:
        room = MAX_DRAFT_PHOTOS - len(draft.photos)
        draft.photos = (draft.photos + await store_photos(photo_urls[:room], who.house.id))[:MAX_DRAFT_PHOTOS]
    if text:
        draft.text = text
    if not draft.text:
        await gw.send(
            chat_id=who.chat_id,
            text=f"Фото получил ({len(draft.photos)}). Теперь пару слов: что случилось и где?",
            buttons=[[button("✖️ Отмена", "report:cancel")]],
        )
        return
    if len(draft.text) < 5:
        await gw.send(chat_id=who.chat_id, text="Опишите чуть подробнее: что случилось и где.")
        return
    draft.stage = "confirm"
    await show_confirm(gw, who, draft)


async def show_confirm(gw: Gateway, who: Who, draft: Draft) -> None:
    result = await classify(draft.text)
    cat = category(result.category)
    async with get_sessionmaker()() as session:
        org = await issues.responsible_org(session, who.house, cat.org_kind)
        similar = await issues.similar_issues(session, who.house.id, who.user.id, draft.text)
    org_name = org.name if org else "ответственная служба"
    lines = [
        "📋 **Проверьте заявку**",
        "",
        draft.text[:600],
        "",
        f"🏷 Категория: {cat.title}",
        f"👷 Кто отвечает: {org_name}",
        f"⏱ Срок по закону: {fmt_hours(cat.deadline_hours)}",
        f"📜 Основание: {cat.legal_basis.split(';')[0]}",
        f"📷 Фото: {len(draft.photos)}",
    ]
    buttons: Buttons = []
    if cat.code == "gas":
        lines.insert(0, "🚨 Запах газа: не включайте свет и огонь, откройте окна и звоните **104** или **112**.\n")
        buttons.append([button("🚨 Передать в аварийную службу", "report:send")])
    else:
        dup = next((s for s in similar if s.status == "voting"), None)
        if dup:
            lines += [
                "",
                f"Похоже, такая заявка уже есть: «{dup.title}», поддержали {dup.votes_count} из {dup.votes_needed}. "
                "Если это она, поддержите её, и обращение уйдёт быстрее.",
            ]
            buttons.append([button(f"👍 Поддержать «{dup.title[:24]}»", f"vote:{dup.id}:card")])
        buttons.append([button("✅ Отправить соседям", "report:send")])
    buttons.append([button("✏️ Исправить", "report:edit"), button("✖️ Отмена", "report:cancel")])
    # фото показываем прямо в карточке: житель видит, что уйдёт соседям
    await gw.send(chat_id=who.chat_id, text="\n".join(lines), buttons=buttons, photos=list(draft.photos) or None)


async def report_action(gw: Gateway, who: Who, action: str) -> str:
    key = (who.chat_id, who.user.max_user_id)
    draft = _drafts.get(key)
    if action == "cancel":
        _drafts.pop(key, None)
        await gw.send(
            chat_id=who.chat_id, text="Отменил, заявка не отправлена.", buttons=main_menu(dm=not who.is_group)
        )
        return "Отменено"
    if draft is None:
        return "Черновик устарел, начните заново"
    if action == "edit":
        draft.stage = "text"
        await gw.send(
            chat_id=who.chat_id,
            text="Напишите описание заново одним сообщением. Фото сохранил.",
            buttons=[[button("✖️ Отмена", "report:cancel")]],
        )
        return "Жду новый текст"
    if action != "send" or not draft.text:
        return "Сначала напишите, что случилось"
    if draft.house_id != who.house.id:
        _drafts.pop(key, None)
        return "Вы сменили дом, начните заявку заново"
    async with get_sessionmaker()() as session:
        user = await session.get(User, who.user.id)
        house = await session.get(House, who.house.id)
        if user is None or house is None:
            return "Не нашёл ваш дом"
        issue = await issues.create_issue(session, user=user, house=house, description=draft.text, photos=draft.photos)
        issue_id, title, status = issue.id, issue.title, issue.status
        votes, needed = issue.votes_count, issue.votes_needed
    _drafts.pop(key, None)
    if status == "voting":
        text = (
            f"✅ Заявка №{issue_id} «{title}» опубликована в чате дома.\n"
            f"Ваш голос уже учтён: {votes} из {needed}. Когда соседи поддержат, я сам отправлю обращение."
        )
    else:
        text = f"📨 Заявка №{issue_id} «{title}» сразу отправлена исполнителю. Слежу за сроком."
    await gw.send(chat_id=who.chat_id, text=text, buttons=[[button("📋 Карточка заявки", f"issue:{issue_id}")]])
    return "Заявка создана"


# ---------- карточка заявки ----------


async def issue_card(session: AsyncSession, issue: Issue, who: Who) -> tuple[str, Buttons]:
    cat = category(issue.category)
    org = issue.responsible_org.name if issue.responsible_org else "ответственная служба"
    lines = [
        f"📋 **{issue.title}** · №{issue.id}",
        f"{STATUS_ICON.get(issue.status, '•')} {STATUS_TITLES.get(issue.status, issue.status)}",
    ]
    if issue.status == "voting":
        lines.append(f"👍 Поддержали {issue.votes_count} из {issue.votes_needed}")
    lines.append(f"👷 Исполнитель: {org}")
    if issue.deadline_at and issue.status in ("sent", "in_progress"):
        lines.append(f"⏱ Срок: до {fmt_dt(issue.deadline_at)} ({fmt_left(issue.deadline_at)})")
    else:
        lines.append(f"⏱ Срок по закону: {fmt_hours(cat.deadline_hours)} после отправки")
    if issue.location_hint:
        lines.append(f"📍 {issue.location_hint}")
    lines += ["", issue.description[:400]]
    updates = await issues.timeline(session, issue.id)
    if updates:
        lines += ["", "🕑 **Ход заявки**"]
        for u in updates[-4:]:
            note = u.note.split("\n", 1)[0][:110]
            lines.append(f"• {fmt_dt(u.created_at)}: {note}")

    buttons: Buttons = []
    voted = await issues.has_voted(session, issue.id, who.user.id)
    if issue.status == "voting" and not voted:
        buttons.append([button(f"👍 Поддерживаю ({issue.votes_count}/{issue.votes_needed})", f"vote:{issue.id}:card")])
    can_manage = who.is_admin or issue.author_id == who.user.id
    if can_manage and issue.status in ("sent", "in_progress"):
        row = [button("✅ Решено", f"status:{issue.id}:resolved")]
        if issue.status == "sent":
            row.insert(0, button("🔧 В работе", f"status:{issue.id}:in_progress"))
        buttons.append(row)
    extra = []
    if issue.appeal_text:
        extra.append(button("📄 Обращение", f"appeal:{issue.id}"))
    if issue.escalated_at:
        extra.append(button("⚖️ Жалоба в ГЖИ", f"complaint:{issue.id}"))
    if extra:
        buttons.append(extra)
    buttons.append([issues.app_button("Открыть в приложении", f"issue_{issue.id}")])
    return "\n".join(lines), buttons


async def _issue_of(session: AsyncSession, who: Who, issue_id: int) -> Issue:
    return await issues.get_issue(session, issue_id, who.house.id)


async def send_issue_card(gw: Gateway, who: Who, issue_id: int) -> str:
    async with get_sessionmaker()() as session:
        issue = await _issue_of(session, who, issue_id)
        text, buttons = await issue_card(session, issue, who)
    await gw.send(chat_id=who.chat_id, text=text, buttons=buttons, photos=None)
    return "Карточка заявки"


async def vote_from_card(gw: Gateway, who: Who, issue_id: int, mid: str | None) -> str:
    async with get_sessionmaker()() as session:
        issue = await _issue_of(session, who, issue_id)
        # очки за голос начисляются жителю этой сессии, а не копии из другой
        user = await session.get(User, who.user.id) or who.user
        issue, reached = await issues.vote(session, issue, user)
        text, buttons = await issue_card(session, issue, who)
    if mid:
        await gw.edit(mid=mid, text=text, buttons=buttons)
    return (
        "Голосов хватило! Отправляю обращение 📨"
        if reached
        else f"Голос учтён: {issue.votes_count} из {issue.votes_needed}"
    )


async def change_status(gw: Gateway, who: Who, issue_id: int, status: str, mid: str | None) -> str:
    if status not in ("in_progress", "resolved"):
        return "Кнопка устарела"
    async with get_sessionmaker()() as session:
        issue = await _issue_of(session, who, issue_id)
        if issue.status not in ("sent", "in_progress"):
            return "Статус можно менять после отправки обращения"
        issue = await issues.set_status(session, issue, who.user, who.is_admin, status, "")
        text, buttons = await issue_card(session, issue, who)
    if mid:
        await gw.edit(mid=mid, text=text, buttons=buttons)
    return "Отметил: решено 🎉" if status == "resolved" else "Отметил: в работе"


async def send_appeal(gw: Gateway, who: Who, issue_id: int, complaint: bool) -> str:
    async with get_sessionmaker()() as session:
        issue = await _issue_of(session, who, issue_id)
        if complaint:
            note = await session.scalar(
                select(IssueUpdate.note)
                .where(IssueUpdate.issue_id == issue.id, IssueUpdate.note.startswith("Срок истёк"))
                .order_by(IssueUpdate.id.desc())
                .limit(1)
            )
            body = note or "Жалобы пока нет: срок ещё не истёк."
        else:
            body = issue.appeal_text or "Обращение ещё не отправлено: идёт сбор голосов."
    head = "⚖️ **Жалоба в Госжилинспекцию**" if complaint else "📄 **Текст обращения**"
    await gw.send(chat_id=who.chat_id, text=f"{head}\n\n{body[:3500]}")
    return "Отправил текст"


# ---------- списки ----------


async def send_issue_list(gw: Gateway, who: Who, mine: bool) -> None:
    async with get_sessionmaker()() as session:
        where = [Issue.house_id == who.house.id]
        where.append(Issue.author_id == who.user.id if mine else Issue.status.in_(OPEN_STATUSES))
        rows = list(
            await session.scalars(select(Issue).where(*where).order_by(Issue.created_at.desc()).limit(LIST_LIMIT))
        )
    if not rows:
        text = "У вас пока нет заявок." if mine else "Открытых заявок нет. Дом в порядке 🏠"
        await gw.send(chat_id=who.chat_id, text=text, buttons=[[button("📸 Сообщить о проблеме", "menu:report")]])
        return
    lines = ["🗂 **Мои заявки**" if mine else "📋 **Заявки дома**", ""]
    buttons: Buttons = []
    for n, i in enumerate(rows, 1):
        state = STATUS_TITLES.get(i.status, i.status).lower()
        if i.status == "voting":
            state = f"голосов {i.votes_count} из {i.votes_needed}"
        elif i.deadline_at and i.status in ("sent", "in_progress"):
            state += f", {fmt_left(i.deadline_at)}"
        lines.append(f"{n}. {STATUS_ICON.get(i.status, '•')} {i.title}: {state}")
        buttons.append([button(f"{n}. {i.title[:30]}", f"issue:{i.id}")])
    buttons.append([issues.app_button("Все заявки в приложении", "issues")])
    await gw.send(chat_id=who.chat_id, text="\n".join(lines), buttons=buttons)


def _events_text_and_buttons(items: list[events.EventOut]) -> tuple[str, Buttons]:
    lines = ["📅 **Ближайшие события**", ""]
    buttons: Buttons = []
    for n, e in enumerate(items, 1):
        seats = f", свободно {e.max_participants - e.participants_count}" if e.max_participants else ""
        lines.append(f"{n}. {e.title}: {fmt_dt(e.starts_at)}, {e.place} · идут {e.participants_count}{seats}")
        if e.joined_by_me:
            buttons.append([button(f"✓ {n}. Вы идёте · отменить", f"leave:{e.id}:list")])
        else:
            buttons.append([button(f"🙋 {n}. Иду: {e.title[:26]}", f"join:{e.id}:list")])
    buttons.append([issues.app_button("Все события", "events")])
    return "\n".join(lines), buttons


async def send_events(gw: Gateway, who: Who, mid: str | None = None) -> None:
    async with get_sessionmaker()() as session:
        items = (await events.list_events(session, who.house.id, who.user.id))[:5]
    if not items:
        await gw.send(
            chat_id=who.chat_id,
            text=(
                "Ближайших событий нет. Чтобы позвать соседей, напишите: "
                "«Кузя, создай субботник в субботу в 11 у площадки»."
            ),
        )
        return
    text, buttons = _events_text_and_buttons(items)
    if mid:
        await gw.edit(mid=mid, text=text, buttons=buttons)
    else:
        await gw.send(chat_id=who.chat_id, text=text, buttons=buttons)


async def toggle_event(gw: Gateway, who: Who, event_id: int, join: bool, mid: str | None) -> str:
    async with get_sessionmaker()() as session:
        ev = await session.get(Event, event_id)
        if ev is None or ev.house_id != who.house.id:
            return "Событие не найдено"
        user = await session.get(User, who.user.id) or who.user
        if join:
            await events.join(session, ev, user)
        else:
            await events.leave(session, ev, user)
    await send_events(gw, who, mid)
    return "Записал! Напомню заранее 🙌" if join else "Отменил запись"


async def send_market(gw: Gateway, who: Who) -> None:
    async with get_sessionmaker()() as session:
        items = (await market.list_listings(session, who.house.id, who.user.id, limit=6))[:6]
    if not items:
        await gw.send(
            chat_id=who.chat_id,
            text="В «Вещах соседей» пока пусто.",
            buttons=[[issues.app_button("Разместить вещь", "market")]],
        )
        return
    lines = ["🛍 **Вещи соседей**", ""]
    buttons: Buttons = []
    for n, it in enumerate(items, 1):
        price = "даром" if it.is_free else f"{it.price} ₽"
        lines.append(f"{n}. {it.title}: {price}")
        buttons.append([button(f"{n}. {it.title[:30]}", f"listing:{it.id}")])
    buttons.append([issues.app_button("Разместить свою вещь", "market")])
    await gw.send(chat_id=who.chat_id, text="\n".join(lines), buttons=buttons)


async def send_listing(gw: Gateway, who: Who, listing_id: int) -> str:
    async with get_sessionmaker()() as session:
        item = await market.get_listing(session, listing_id, who.house.id)
        seller = item.author
        price = "даром" if item.price == 0 else f"{item.price} ₽"
        text = f"🛍 **{item.title}** · {price}\n{item.description[:500]}\n\nПродавец: {seller.full_name}" + (
            f", кв. {seller.apartment}" if seller.apartment else ""
        )
        photos = list(item.photos or [])
        mine = item.author_id == who.user.id
    buttons: Buttons = []
    if not mine:
        buttons.append([button("✉️ Написать продавцу", f"contact:{listing_id}")])
    buttons.append([issues.app_button("Открыть в приложении", f"listing_{listing_id}")])
    await gw.send(chat_id=who.chat_id, text=text, buttons=buttons, photos=photos)
    return "Объявление"


async def contact(who: Who, listing_id: int) -> str:
    key = (who.user.id, listing_id)
    now = time.monotonic()
    if now - _last_contact.get(key, -CONTACT_COOLDOWN_S) < CONTACT_COOLDOWN_S:
        return "Уже передал продавцу, ждите ответа в личных сообщениях"
    async with get_sessionmaker()() as session:
        item = await market.get_listing(session, listing_id, who.house.id)
        await market.contact_seller(item, who.user, "")
    _last_contact[key] = now
    return "Передал продавцу, он ответит вам в личных сообщениях"


async def send_shelters(gw: Gateway, who: Who) -> None:
    async with get_sessionmaker()() as session:
        items = await safety.nearest_shelters(session, who.house.lat, who.house.lon, limit=3)
    map_button = issues.app_button("🗺 Карта укрытий", "alert")
    if not items:
        await gw.send(chat_id=who.chat_id, text=safety.NO_SHELTERS_ADVICE, buttons=[[map_button]])
        return
    lines = ["🛡 **Ближайшие укрытия**", ""]
    buttons: Buttons = []
    for n, s in enumerate(items, 1):
        cap = f", до {s.capacity} чел." if s.capacity else ""
        addr = f"\n{s.address}" if s.address else ""
        lines.append(f"{n}. {s.name} ({s.kind_title.lower()}): {s.distance_m} м{cap}, {safety.shelter_note(s)}{addr}")
        buttons.append([{"type": "link", "text": f"🚶 №{n}: маршрут в Яндекс Картах", "url": s.yandex_url}])
    buttons.append([map_button])
    lines += ["", "При тревоге: отойдите от окон, спуститесь в укрытие или встаньте в коридоре без окон."]
    await gw.send(chat_id=who.chat_id, text="\n".join(lines), buttons=buttons)


async def send_profile(gw: Gateway, who: Who) -> None:
    async with get_sessionmaker()() as session:
        user = await session.get(User, who.user.id)
        if user is None:
            return
        earned = int(
            await session.scalar(
                select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == user.id)
            )
            or 0
        )
        top = list(
            await session.execute(
                select(User.first_name, User.last_name, User.points)
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.house_id == who.house.id)
                .order_by(User.points.desc())
                .limit(3)
            )
        )
        level, title, next_points = level_for(user.points)
        points = user.points
    lines = [
        f"🏆 **{who.user.full_name}**",
        f"Уровень {level} · {title} · {points} очков",
    ]
    if next_points:
        lines.append(f"До следующего уровня: {max(0, next_points - points)} очков")
    lines.append(f"Награды: {earned} из {len(ACHIEVEMENTS)}")
    medals = ("🥇", "🥈", "🥉")
    if top:
        lines += ["", "**Лучшие соседи**"] + [f"{medals[i]} {f} {last}: {p}" for i, (f, last, p) in enumerate(top)]
    await gw.send(
        chat_id=who.chat_id, text="\n".join(lines), buttons=[[issues.app_button("Мои награды", "achievements")]]
    )


async def send_houses(gw: Gateway, who: Who) -> None:
    async with get_sessionmaker()() as session:
        rows = await my_houses(session, who.user)
    if len(rows) < 2:
        await gw.send(
            chat_id=who.chat_id,
            text=(
                f"Ваш дом: **{who.house.title}**. "
                "Если вы есть в чате другого дома, где живёт Кузя, этот дом тоже появится здесь."
            ),
        )
        return
    buttons: Buttons = [
        [button(("✓ " if h.id == who.house.id else "") + h.title[:40], f"house:{h.id}")] for h, _ in rows[:8]
    ]
    await gw.send(
        chat_id=who.chat_id,
        text="🏘 Выберите дом: здесь, в личных сообщениях, я буду показывать его заявки и события.",
        buttons=buttons,
    )


async def pick_house(gw: Gateway, who: Who, house_id: int) -> str:
    async with get_sessionmaker()() as session:
        user = await session.get(User, who.user.id)
        rows = await my_houses(session, who.user)
        house = next((h for h, _ in rows if h.id == house_id), None)
        if user is None or house is None:
            return "Этого дома нет в вашем списке"
        user.active_house_id = house.id
        title = house.title
        await session.commit()
    await gw.send(chat_id=who.chat_id, text=f"Готово, ваш дом: **{title}**.", buttons=main_menu(dm=True))
    return "Дом выбран"


# ---------- точки входа из handlers ----------


PRIVATE_COMMANDS = frozenset({"mine", "profile", "houses"})


async def run_command(gw: Gateway, who: Who, name: str) -> None:
    if who.is_group and name in PRIVATE_COMMANDS:
        await gw.send(chat_id=who.chat_id, text="Это личное: напишите мне в личные сообщения, и я покажу 🙂")
        return
    if name == "menu":
        await gw.send(
            chat_id=who.chat_id, text=f"🏠 {who.house.title}. Что сделать?", buttons=main_menu(dm=not who.is_group)
        )
    elif name == "report":
        await start_report(gw, who)
    elif name == "issues":
        await send_issue_list(gw, who, mine=False)
    elif name == "mine":
        await send_issue_list(gw, who, mine=True)
    elif name == "events":
        await send_events(gw, who)
    elif name == "market":
        await send_market(gw, who)
    elif name == "shelters":
        await send_shelters(gw, who)
    elif name == "profile":
        await send_profile(gw, who)
    elif name == "houses":
        await send_houses(gw, who)


CALLBACK_ACTIONS = {
    "menu",
    "report",
    "issue",
    "vote",
    "status",
    "appeal",
    "complaint",
    "join",
    "leave",
    "listing",
    "contact",
    "house",
}


def is_flow_callback(payload: str) -> bool:
    """Колбэки, которые обрабатывает этот модуль. Старые «vote:N» и «join:N» остаются в handlers."""
    parts = payload.split(":")
    if parts[0] in ("vote", "join"):
        return len(parts) == 3
    return parts[0] in CALLBACK_ACTIONS


async def on_callback(gw: Gateway, who: Who, payload: str, mid: str | None) -> str:
    """Возвращает текст всплывающего уведомления для ответа на нажатие."""
    action, *args = payload.split(":")
    num = int(args[0]) if args and args[0].isdigit() else 0
    try:
        if action == "menu":
            await run_command(gw, who, args[0] if args else "menu")
            return "Открываю"
        if action == "report":
            return await report_action(gw, who, args[0] if args else "")
        if action == "issue":
            return await send_issue_card(gw, who, num)
        if action == "vote":
            return await vote_from_card(gw, who, num, mid)
        if action == "status":
            return await change_status(gw, who, num, args[1] if len(args) > 1 else "", mid)
        if action in ("appeal", "complaint"):
            return await send_appeal(gw, who, num, complaint=action == "complaint")
        if action in ("join", "leave"):
            return await toggle_event(gw, who, num, join=action == "join", mid=mid)
        if action == "listing":
            return await send_listing(gw, who, num)
        if action == "contact":
            return await contact(who, num)
        if action == "house":
            return await pick_house(gw, who, num)
    except HTTPException as exc:
        return str(exc.detail)
    return "Кнопка устарела"


def open_draft(who: Who) -> None:
    """Черновик без вопроса: житель сразу прислал фото, описание возьмём из подписи."""
    _drafts[(who.chat_id, who.user.max_user_id)] = Draft(house_id=who.house.id)


def strip_kuzya(text: str) -> str:
    """«Кузя, течёт крыша» -> «течёт крыша»: обращение к Кузе не часть описания."""
    words = text.split(maxsplit=1)
    if words and words[0].lower().rstrip(",:!").startswith("куз"):
        return words[1].strip() if len(words) > 1 else ""
    return text
