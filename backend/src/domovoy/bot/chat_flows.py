"""Основные возможности Кузи прямо в чате MAX, без мини-приложения.

Меню на кнопках-колбэках, подача заявки с фото и подтверждением, карточка заявки со сроком
и текстом обращения, смена статуса, списки заявок, событий, вещей, укрытия, профиль и выбор дома.
Меню, списки и карточки - «экраны»: кнопка меняет экран на месте, на каждом есть «⬅️ Назад».
Списки идут страницами по 5 позиций со стрелками и подписью «Показано: 1-5 из 12».
Объявление в «Вещах соседей» размещается в sell_flow.py на том же черновике, что и заявка.
Черновик заявки живёт в памяти процесса бота (один процесс на все чаты) и сбрасывается через 30 минут.
"""

import time
from dataclasses import dataclass, field

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.bot import screens
from domovoy.bot.gateway import Buttons, Gateway
from domovoy.bot.photos import MAX_DRAFT_PHOTOS, store_photos
from domovoy.bot.ui import (
    Page,
    back_row,
    button,
    fmt_dt,
    fmt_hours,
    fmt_left,
    page_arg,
    pager_row,
    paginate,
    price_text,
)
from domovoy.core.db import get_sessionmaker
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

DRAFT_TTL_S = 30 * 60
MARKET_LIMIT = 200

STATUS_ICON = {"voting": "✋", "sent": "📨", "in_progress": "🔧", "resolved": "✅", "rejected": "✖️"}


@dataclass
class Draft:
    """Черновик заявки или объявления: житель пишет текст и шлёт фото, Кузя показывает карточку."""

    house_id: int
    kind: str = "issue"  # issue - заявка, listing - объявление в «Вещах соседей» (sell_flow.py)
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
    "/продать": "sell",
    "/отдать": "sell",
    "/разместить": "sell",
    "/укрытия": "shelters",
    "/профиль": "profile",
    "/дом": "houses",
    "/дома": "houses",
}


def command_of(text: str) -> str | None:
    word = text.strip().split(maxsplit=1)[0].lower() if text.strip() else ""
    word = word.split("@", 1)[0]
    return COMMANDS.get(word)


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


# ---------- экраны ----------


async def show(
    gw: Gateway,
    who: Who,
    mid: str | None,
    text: str,
    buttons: Buttons,
    *,
    photos: list[str] | None = None,
    in_place: bool = False,
) -> None:
    """Экран вместо нажатого сообщения (bot/screens.py): кнопки меняют его на месте."""
    await screens.show(
        gw,
        chat_id=who.chat_id,
        is_group=who.is_group,
        mid=mid,
        text=text,
        buttons=buttons,
        photos=photos,
        in_place=in_place,
    )


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


def get_draft(who: Who) -> Draft | None:
    return _drafts.get((who.chat_id, who.user.max_user_id))


def drop_draft(who: Who, kind: str) -> None:
    """Убрать черновик этого вида: отмена со старой карточки объявления не трогает начатую заявку."""
    draft = get_draft(who)
    if draft is not None and draft.kind == kind:
        _drafts.pop((who.chat_id, who.user.max_user_id), None)


async def close_draft(gw: Gateway, who: Who, mid: str | None, text: str) -> None:
    """Черновик отменён: его вопрос или карточку убираем, вместо них меню."""
    if mid and not screens.known(mid):
        await gw.delete(mid=mid)
        mid = None
    await show(gw, who, mid, text, main_menu(dm=not who.is_group))


async def draft_message(gw: Gateway, who: Who, text: str, photo_urls: list[str]) -> None:
    """Сообщение жителя, у которого открыт черновик: описание, фото или исправленный текст."""
    draft = _drafts[(who.chat_id, who.user.max_user_id)]
    if draft.kind == "listing":
        # sell_flow сам берёт черновики и экраны из этого модуля, поэтому импорт здесь, а не наверху
        from domovoy.bot import sell_flow

        await sell_flow.draft_message(gw, who, draft, text, photo_urls)
        return
    if photo_urls:
        room = MAX_DRAFT_PHOTOS - len(draft.photos)
        draft.photos = (draft.photos + await store_photos(photo_urls[:room], f"issues/{who.house.id}"))[
            :MAX_DRAFT_PHOTOS
        ]
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


async def report_action(gw: Gateway, who: Who, action: str, mid: str | None = None) -> str:
    key = (who.chat_id, who.user.max_user_id)
    draft = _drafts.get(key)
    if action == "cancel":
        drop_draft(who, "issue")
        await close_draft(gw, who, mid, "Отменил, заявка не отправлена.")
        return "Отменено"
    if draft is None or draft.kind != "issue":
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


async def issue_card(session: AsyncSession, issue: Issue, who: Who, origin: str = "issues") -> tuple[str, Buttons]:
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
    # хвост «:mine:2» помнит, из какого списка и с какой страницы открыли заявку: туда и вернёт «Назад»
    tail = "" if origin == "issues" else f":{origin}"
    extra = []
    if issue.appeal_text:
        extra.append(button("📄 Обращение", f"appeal:{issue.id}{tail}"))
    if issue.escalated_at:
        extra.append(button("⚖️ Жалоба в ГЖИ", f"complaint:{issue.id}{tail}"))
    if extra:
        buttons.append(extra)
    buttons.append([issues.app_button("Открыть в приложении", f"issue_{issue.id}")])
    buttons.append(back_row("⬅️ Назад к заявкам", f"menu:{origin}"))
    return "\n".join(lines), buttons


async def _issue_of(session: AsyncSession, who: Who, issue_id: int) -> Issue:
    return await issues.get_issue(session, issue_id, who.house.id)


async def send_issue_card(gw: Gateway, who: Who, issue_id: int, mid: str | None = None, origin: str = "issues") -> str:
    async with get_sessionmaker()() as session:
        issue = await _issue_of(session, who, issue_id)
        text, buttons = await issue_card(session, issue, who, origin)
    await show(gw, who, mid, text, buttons)
    return "Карточка заявки"


async def vote_from_card(gw: Gateway, who: Who, issue_id: int, mid: str | None) -> str:
    async with get_sessionmaker()() as session:
        issue = await _issue_of(session, who, issue_id)
        # очки за голос начисляются жителю этой сессии, а не копии из другой
        user = await session.get(User, who.user.id) or who.user
        issue, reached = await issues.vote(session, issue, user)
        text, buttons = await issue_card(session, issue, who)
    await show(gw, who, mid, text, buttons, in_place=True)
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
    await show(gw, who, mid, text, buttons, in_place=True)
    return "Отметил: решено 🎉" if status == "resolved" else "Отметил: в работе"


async def send_appeal(
    gw: Gateway, who: Who, issue_id: int, complaint: bool, mid: str | None = None, origin: str = "issues"
) -> str:
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
    back = back_row("⬅️ Назад к заявке", f"issue:{issue_id}" if origin == "issues" else f"issue:{issue_id}:{origin}")
    await show(gw, who, mid, f"{head}\n\n{body[:3500]}", [back])
    return "Отправил текст"


# ---------- списки ----------


async def send_issue_list(gw: Gateway, who: Who, mine: bool, mid: str | None = None, page: int = 1) -> None:
    async with get_sessionmaker()() as session:
        where = [Issue.house_id == who.house.id]
        where.append(Issue.author_id == who.user.id if mine else Issue.status.in_(OPEN_STATUSES))
        ids = list(
            await session.scalars(select(Issue.id).where(*where).order_by(Issue.created_at.desc(), Issue.id.desc()))
        )
        page_ids, pg = paginate(ids, page)
        found = {i.id: i for i in await session.scalars(select(Issue).where(Issue.id.in_(page_ids)))}
    rows = [found[i] for i in page_ids if i in found]
    if not rows:
        text = "У вас пока нет заявок." if mine else "Открытых заявок нет. Дом в порядке 🏠"
        await show(gw, who, mid, text, [[button("📸 Сообщить о проблеме", "menu:report")], back_row()])
        return
    name = "mine" if mine else "issues"
    origin = f"{name}{pg.tail}"
    lines = ["🗂 **Мои заявки**" if mine else "📋 **Заявки дома**", pg.shown, ""]
    buttons: Buttons = []
    for n, i in enumerate(rows, pg.first):
        state = STATUS_TITLES.get(i.status, i.status).lower()
        if i.status == "voting":
            state = f"голосов {i.votes_count} из {i.votes_needed}"
        elif i.deadline_at and i.status in ("sent", "in_progress"):
            state += f", {fmt_left(i.deadline_at)}"
        lines.append(f"{n}. {STATUS_ICON.get(i.status, '•')} {i.title}: {state}")
        buttons.append(
            [button(f"{n}. {i.title[:30]}", f"issue:{i.id}" if origin == "issues" else f"issue:{i.id}:{origin}")]
        )
    if arrows := pager_row(pg, f"menu:{name}"):
        buttons.append(arrows)
    buttons += [[issues.app_button("Все заявки в приложении", "issues")], back_row()]
    await show(gw, who, mid, "\n".join(lines), buttons)


def _events_text_and_buttons(items: list[events.EventOut], pg: Page) -> tuple[str, Buttons]:
    lines = ["📅 **Ближайшие события**", pg.shown, ""]
    buttons: Buttons = []
    for n, e in enumerate(items, pg.first):
        seats = f", свободно {e.max_participants - e.participants_count}" if e.max_participants else ""
        lines.append(f"{n}. {e.title}: {fmt_dt(e.starts_at)}, {e.place} · идут {e.participants_count}{seats}")
        if e.joined_by_me:
            buttons.append([button(f"✓ {n}. Вы идёте · отменить", f"leave:{e.id}:list{pg.tail}")])
        else:
            buttons.append([button(f"🙋 {n}. Иду: {e.title[:26]}", f"join:{e.id}:list{pg.tail}")])
    if arrows := pager_row(pg, "menu:events"):
        buttons.append(arrows)
    buttons += [[issues.app_button("Все события", "events")], back_row()]
    return "\n".join(lines), buttons


async def send_events(gw: Gateway, who: Who, mid: str | None = None, page: int = 1, *, in_place: bool = False) -> None:
    async with get_sessionmaker()() as session:
        items, pg = paginate(await events.list_events(session, who.house.id, who.user.id), page)
    if not items:
        text = (
            "Ближайших событий нет. Чтобы позвать соседей, напишите: "
            "«Кузя, создай субботник в субботу в 11 у площадки»."
        )
        await show(gw, who, mid, text, [back_row()], in_place=in_place)
        return
    text, buttons = _events_text_and_buttons(items, pg)
    await show(gw, who, mid, text, buttons, in_place=in_place)


async def toggle_event(gw: Gateway, who: Who, event_id: int, join: bool, mid: str | None, page: int = 1) -> str:
    async with get_sessionmaker()() as session:
        ev = await session.get(Event, event_id)
        if ev is None or ev.house_id != who.house.id:
            return "Событие не найдено"
        user = await session.get(User, who.user.id) or who.user
        if join:
            await events.join(session, ev, user)
        else:
            await events.leave(session, ev, user)
    await send_events(gw, who, mid, page, in_place=True)
    return "Записал! Напомню заранее 🙌" if join else "Отменил запись"


def sell_button(who: Who) -> dict[str, str]:
    """В личке вещь размещается прямо в чате (sell_flow.py), в чате дома - через приложение."""
    if who.is_group:
        return issues.app_button("Разместить свою вещь", "market")
    return button("➕ Разместить свою вещь", "sell:start")


async def send_market(gw: Gateway, who: Who, mid: str | None = None, page: int = 1) -> None:
    async with get_sessionmaker()() as session:
        items, pg = paginate(await market.list_listings(session, who.house.id, who.user.id, limit=MARKET_LIMIT), page)
    if not items:
        buttons: Buttons = [[sell_button(who)], back_row()]
        await show(gw, who, mid, "В «Вещах соседей» пока пусто.", buttons)
        return
    lines = ["🛍 **Вещи соседей**", pg.shown, ""]
    buttons = []
    for n, it in enumerate(items, pg.first):
        lines.append(f"{n}. {it.title}: {price_text(it.price)}")
        buttons.append([button(f"{n}. {it.title[:30]}", f"listing:{it.id}{pg.tail}")])
    if arrows := pager_row(pg, "menu:market"):
        buttons.append(arrows)
    buttons += [[sell_button(who)], back_row()]
    await show(gw, who, mid, "\n".join(lines), buttons)


async def send_listing(gw: Gateway, who: Who, listing_id: int, mid: str | None = None, page: int = 1) -> str:
    async with get_sessionmaker()() as session:
        item = await market.get_listing(session, listing_id, who.house.id)
        seller = item.author
        text = (
            f"🛍 **{item.title}** · {price_text(item.price)}\n{item.description[:500]}\n\nПродавец: {seller.full_name}"
            + (f", кв. {seller.apartment}" if seller.apartment else "")
        )
        photos = list(item.photos or [])
        mine = item.author_id == who.user.id
    buttons: Buttons = []
    if not mine:
        buttons.append([button("✉️ Написать продавцу", f"contact:{listing_id}")])
    buttons.append([issues.app_button("Открыть в приложении", f"listing_{listing_id}")])
    buttons.append(back_row("⬅️ Назад к вещам", f"menu:market{f':{page}' if page > 1 else ''}"))
    await show(gw, who, mid, text, buttons, photos=photos)
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


async def send_shelters(gw: Gateway, who: Who, mid: str | None = None) -> None:
    async with get_sessionmaker()() as session:
        items = await safety.nearest_shelters(session, who.house.lat, who.house.lon, limit=3)
    map_button = issues.app_button("🗺 Карта укрытий", "alert")
    if not items:
        await show(gw, who, mid, safety.NO_SHELTERS_ADVICE, [[map_button], back_row()])
        return
    lines = ["🛡 **Ближайшие укрытия**", ""]
    buttons: Buttons = []
    for n, s in enumerate(items, 1):
        cap = f", до {s.capacity} чел." if s.capacity else ""
        addr = f"\n{s.address}" if s.address else ""
        lines.append(f"{n}. {s.name} ({s.kind_title.lower()}): {s.distance_m} м{cap}, {safety.shelter_note(s)}{addr}")
        buttons.append([{"type": "link", "text": f"🚶 №{n}: маршрут в Яндекс Картах", "url": s.yandex_url}])
    buttons += [[map_button], back_row()]
    lines += ["", "При тревоге: отойдите от окон, спуститесь в укрытие или встаньте в коридоре без окон."]
    await show(gw, who, mid, "\n".join(lines), buttons)


async def send_profile(gw: Gateway, who: Who, mid: str | None = None) -> None:
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
    await show(gw, who, mid, "\n".join(lines), [[issues.app_button("Мои награды", "achievements")], back_row()])


async def send_houses(gw: Gateway, who: Who, mid: str | None = None) -> None:
    async with get_sessionmaker()() as session:
        rows = await my_houses(session, who.user)
    if len(rows) < 2:
        text = (
            f"Ваш дом: **{who.house.title}**. "
            "Если вы есть в чате другого дома, где живёт Кузя, этот дом тоже появится здесь."
        )
        await show(gw, who, mid, text, [back_row()])
        return
    buttons: Buttons = [
        [button(("✓ " if h.id == who.house.id else "") + h.title[:40], f"house:{h.id}")] for h, _ in rows[:8]
    ]
    buttons.append(back_row())
    await show(
        gw, who, mid, "🏘 Выберите дом: здесь, в личных сообщениях, я буду показывать его заявки и события.", buttons
    )


async def pick_house(gw: Gateway, who: Who, house_id: int, mid: str | None = None) -> str:
    async with get_sessionmaker()() as session:
        user = await session.get(User, who.user.id)
        rows = await my_houses(session, who.user)
        house = next((h for h, _ in rows if h.id == house_id), None)
        if user is None or house is None:
            return "Этого дома нет в вашем списке"
        user.active_house_id = house.id
        title = house.title
        await session.commit()
    await show(gw, who, mid, f"Готово, ваш дом: **{title}**.", main_menu(dm=True))
    return "Дом выбран"


# ---------- точки входа из handlers ----------


PRIVATE_COMMANDS = frozenset({"mine", "profile", "houses"})


async def run_command(gw: Gateway, who: Who, name: str, mid: str | None = None, page: int = 1) -> None:
    """Команда текстом или кнопкой меню; mid - экран, на котором нажали: его и меняем; page - страница списка."""
    if who.is_group and name in PRIVATE_COMMANDS:
        await show(gw, who, mid, "Это личное: напишите мне в личные сообщения, и я покажу 🙂", [back_row()])
        return
    if name == "menu":
        await show(gw, who, mid, f"🏠 {who.house.title}. Что сделать?", main_menu(dm=not who.is_group))
    elif name == "report":
        await start_report(gw, who)
    elif name == "issues":
        await send_issue_list(gw, who, mine=False, mid=mid, page=page)
    elif name == "mine":
        await send_issue_list(gw, who, mine=True, mid=mid, page=page)
    elif name == "events":
        await send_events(gw, who, mid, page)
    elif name == "market":
        await send_market(gw, who, mid, page)
    elif name == "sell":
        from domovoy.bot import sell_flow  # см. draft_message: sell_flow импортирует этот модуль

        await sell_flow.start(gw, who, mid)
    elif name == "shelters":
        await send_shelters(gw, who, mid)
    elif name == "profile":
        await send_profile(gw, who, mid)
    elif name == "houses":
        await send_houses(gw, who, mid)


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
    "sell",
}


def is_flow_callback(payload: str) -> bool:
    """Колбэки, которые обрабатывает этот модуль. Старые «vote:N» и «join:N» остаются в handlers."""
    parts = payload.split(":")
    if parts[0] in ("vote", "join"):
        return len(parts) >= 3
    return parts[0] in CALLBACK_ACTIONS


async def on_callback(gw: Gateway, who: Who, payload: str, mid: str | None) -> str:
    """Возвращает текст всплывающего уведомления для ответа на нажатие."""
    action, *args = payload.split(":")
    num = int(args[0]) if args and args[0].isdigit() else 0
    # из какого списка и с какой страницы открыли заявку («issue:5:mine:2»): туда и ведёт «Назад»
    name = "mine" if len(args) > 1 and args[1] == "mine" and not who.is_group else "issues"
    page = page_arg(args, 2)
    origin = f"{name}:{page}" if page > 1 else name
    try:
        if action == "menu":
            await run_command(gw, who, args[0] if args else "menu", mid, page_arg(args, 1))
            return "Открываю"
        if action == "report":
            return await report_action(gw, who, args[0] if args else "", mid)
        if action == "issue":
            return await send_issue_card(gw, who, num, mid, origin)
        if action == "vote":
            return await vote_from_card(gw, who, num, mid)
        if action == "status":
            return await change_status(gw, who, num, args[1] if len(args) > 1 else "", mid)
        if action in ("appeal", "complaint"):
            return await send_appeal(gw, who, num, action == "complaint", mid, origin)
        if action in ("join", "leave"):
            return await toggle_event(gw, who, num, join=action == "join", mid=mid, page=page_arg(args, 2))
        if action == "listing":
            return await send_listing(gw, who, num, mid, page_arg(args, 1))
        if action == "contact":
            return await contact(who, num)
        if action == "house":
            return await pick_house(gw, who, num, mid)
        if action == "sell":
            from domovoy.bot import sell_flow  # см. draft_message: sell_flow импортирует этот модуль

            return await sell_flow.action(gw, who, args[0] if args else "", mid)
    except HTTPException as exc:
        return str(exc.detail)
    return "Кнопка устарела"


def open_draft(who: Who, kind: str = "issue") -> Draft:
    """Черновик без вопроса: житель сразу прислал фото, описание возьмём из подписи."""
    _purge_drafts()
    draft = _drafts[(who.chat_id, who.user.max_user_id)] = Draft(house_id=who.house.id, kind=kind)
    return draft


def strip_kuzya(text: str) -> str:
    """«Кузя, течёт крыша» -> «течёт крыша»: обращение к Кузе не часть описания."""
    words = text.split(maxsplit=1)
    if words and words[0].lower().rstrip(",:!").startswith("куз"):
        return words[1].strip() if len(words) > 1 else ""
    return text
