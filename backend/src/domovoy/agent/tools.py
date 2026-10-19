"""Доменные инструменты агента Кузи.

Инструменты создаются под конкретный контекст (кто пишет и из какого дома), поэтому
модель не может передать чужой user_id или дом: права проверяются так же, как в REST API.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from langchain_core.tools import BaseTool, tool
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.agent.timeparse import parse_when
from domovoy.core.db import get_sessionmaker
from domovoy.modules.achievements.catalog import level_for
from domovoy.modules.announcements import service as announcements
from domovoy.modules.events import service as events
from domovoy.modules.events.models import Event
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.catalog import STATUS_TITLES
from domovoy.modules.issues.models import Issue
from domovoy.modules.market import service as market
from domovoy.modules.market.models import Listing
from domovoy.modules.safety import service as safety
from domovoy.modules.search.hybrid import hybrid_search
from domovoy.modules.users.models import House, User
from domovoy.modules.users.pulse import house_pulse

MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True, slots=True)
class AgentContext:
    user_id: int
    house_id: int
    is_admin: bool = False


KIND_WORDS = (
    ("субботник", "subbotnik"),
    ("уборк", "subbotnik"),
    ("собрани", "meeting"),
    ("праздник", "holiday"),
    ("турнир", "sport"),
    ("футбол", "sport"),
    ("дет", "kids"),
)


def infer_kind(title: str) -> str:
    low = title.lower()
    return next((kind for word, kind in KIND_WORDS if word in low), "other")


# В общем чате длинные списки мешают соседям: показываем начало, остальное в приложении
CHAT_LIST_LIMIT = 5


def short_list(title: str, lines: list[str], rest_hint: str) -> str:
    shown = lines[:CHAT_LIST_LIMIT]
    text = f"{title}:\n" + "\n".join(shown)
    hidden = len(lines) - len(shown)
    if hidden > 0:
        text += f"\n...и ещё {hidden}, {rest_hint}."
    return text


def _fmt_dt(dt: datetime) -> str:
    return dt.astimezone(MSK).strftime("%d.%m %H:%M")


def build_tools(ctx: AgentContext) -> list[BaseTool]:
    sm = get_sessionmaker()

    async def load(session: AsyncSession) -> tuple[User, House]:
        user = await session.get(User, ctx.user_id)
        house = await session.get(House, ctx.house_id)
        if user is None or house is None:
            raise HTTPException(404, "Не нашёл ваш дом")
        return user, house

    @tool
    async def house_status() -> str:
        """Состояние дома: настроение Кузи, открытые и просроченные заявки, ближайшие события."""
        async with sm() as session:
            p = await house_pulse(session, ctx.house_id)
        s = p.stats
        return (
            f"Здоровье дома {p.score}/100, уровень дома {p.level}. {p.phrase}\n"
            f"Открытых заявок: {s.open_issues}, просрочено: {s.overdue_issues}, решено за 30 дней: {s.resolved_30d}, "
            f"ближайших событий: {s.upcoming_events}, объявлений в «Вещах соседей»: {s.active_listings}."
        )

    @tool
    async def list_issues(status: str = "open") -> str:
        """Список заявок дома. status: open (открытые) или all (все)."""
        async with sm() as session:
            items = await issues.list_issues(
                session, ctx.house_id, ctx.user_id, None if status == "all" else "open", limit=50
            )
        if not items:
            return "Открытых заявок нет. Дом в порядке!"
        lines = [
            f"№{i.id} «{i.title}» - {i.status_title}"
            + (f", голосов {i.votes_count}/{i.votes_needed}" if i.status == "voting" else "")
            + (" (срок истёк!)" if i.is_overdue else "")
            for i in items
        ]
        return short_list(f"Заявки дома ({len(items)})", lines, "все заявки в приложении")

    @tool
    async def create_issue(description: str) -> str:
        """Создать заявку о поломке в доме по описанию жителя. Запускает голосование соседей."""
        async with sm() as session:
            user, house = await load(session)
            similar = await issues.similar_issues(session, house.id, user.id, description)
            if similar:
                d = similar[0]
                return (
                    f"Похожая заявка уже есть: №{d.id} «{d.title}» ({d.votes_count}/{d.votes_needed} голосов). "
                    "Лучше поддержать её, чтобы голоса не делились: нажмите «Поддерживаю» в чате или в приложении."
                )
            issue = await issues.create_issue(session, user=user, house=house, description=description)
            org = issue.responsible_org.name if issue.responsible_org else "исполнителю"
        return (
            f"Заявка №{issue.id} «{issue.title}» создана. Нужно {issue.votes_needed} голосов, "
            f"после этого я отправлю обращение: {org}. Срок по нормативу: {issue.deadline_hours} ч."
        )

    @tool
    async def vote_issue(issue_id: int) -> str:
        """Проголосовать за заявку соседа по её номеру."""
        async with sm() as session:
            user, _ = await load(session)
            try:
                issue = await issues.get_issue(session, issue_id, ctx.house_id)
                issue, reached = await issues.vote(session, issue, user)
            except HTTPException as exc:
                return str(exc.detail)
        if reached:
            return f"Голос учтён, и голосов теперь хватает. Отправляю обращение по заявке №{issue.id}."
        return f"Голос учтён: {issue.votes_count} из {issue.votes_needed}."

    @tool
    async def list_events() -> str:
        """Ближайшие события и мероприятия во дворе."""
        async with sm() as session:
            items = await events.list_events(session, ctx.house_id, ctx.user_id)
        if not items:
            return "Ближайших событий нет. Можно организовать субботник или встречу соседей!"
        lines = [
            f"№{e.id} «{e.title}» {_fmt_dt(e.starts_at)}, {e.place}, идут {e.participants_count}"
            + (" (вы записаны)" if e.joined_by_me else "")
            for e in items
        ]
        return short_list(f"Ближайшие события ({len(items)})", lines, "все события в приложении")

    @tool
    async def create_event(
        title: str, when: str, place: str = "Во дворе", description: str = "", kind: str = "other"
    ) -> str:
        """Создать событие двора и позвать соседей.

        when: дата и время словами («в субботу в 11», «завтра в 18:30», «25.10 в 10») или ISO 8601.
        kind: subbotnik, meeting, holiday, sport, kids или other.
        """
        starts_at = parse_when(when)
        if starts_at is None:
            return "Не понял дату. Уточните, пожалуйста, день и время, например «в субботу в 11»."
        if kind not in events.KINDS or kind == "other":
            kind = infer_kind(title)
        async with sm() as session:
            user, house = await load(session)
            try:
                ev = await events.create_event(
                    session,
                    user=user,
                    house=house,
                    data=events.EventIn(
                        title=title[:120], description=description, kind=kind, starts_at=starts_at, place=place[:200]
                    ),
                )
            except HTTPException as exc:
                return str(exc.detail)
        return (
            f"Готово! Событие №{ev.id} «{ev.title}» {_fmt_dt(ev.starts_at)} (МСК), место: {ev.place}. "
            "Я опубликовал анонс в чате и напомню записавшимся за пару часов."
        )

    @tool
    async def create_announcement(title: str, text: str = "", when: str = "", place: str = "") -> str:
        """Сделать объявление для всех жителей: сообщение Кузи в чате дома и запись на доске объявлений.

        Используй, когда просят «сделай объявление», «оповести соседей», «напиши всем».
        title: короткий заголовок («Субботник во дворе», «Отключение горячей воды»).
        text: текст объявления, вежливо, 1-4 предложения; можно пусто.
        when: только для мероприятия жителей (субботник, собрание, праздник) - дата и время словами
        («в субботу в 11»); тогда создаётся ещё и событие с кнопкой «Иду» и напоминанием.
        place: место мероприятия.
        """
        starts_at = parse_when(when) if when else None
        async with sm() as session:
            user, house = await load(session)
            event_id: int | None = None
            try:
                if starts_at is not None:
                    ev = await events.create_event(
                        session,
                        user=user,
                        house=house,
                        data=events.EventIn(
                            title=title[:120],
                            description=text[:2000],
                            kind=infer_kind(title),
                            starts_at=starts_at,
                            place=(place or "Во дворе")[:200],
                        ),
                        pin=ctx.is_admin,
                    )
                    event_id = ev.id
                    if not text:
                        text = (
                            f"Приглашаем всех соседей! Когда: {_fmt_dt(ev.starts_at)} (МСК). Место: {ev.place}. "
                            "Нажмите «Иду», и я напомню заранее."
                        )
                item = await announcements.create_announcement(
                    session,
                    user=user,
                    house=house,
                    title=title,
                    text=text,
                    pin=ctx.is_admin,
                    event_id=event_id,
                    # у события свой анонс в чате с кнопкой «Иду»: второе сообщение было бы лишним
                    post_to_chat=event_id is None,
                )
            except HTTPException as exc:
                return str(exc.detail)
        where = "в чате и на доске объявлений" + (" (закрепил в чате)" if ctx.is_admin else "")
        if event_id:
            return (
                f"Готово! Объявление «{item.title}» опубликовано {where}, событие №{event_id} создано: "
                "соседи могут нажать «Иду», я напомню им заранее."
            )
        return (
            f"Готово! Объявление «{item.title}» опубликовано {where}. "
            "Если это мероприятие, скажите дату и время, и я заведу событие с кнопкой «Иду»."
        )

    @tool
    async def list_listings(query: str = "") -> str:
        """Вещи соседей: объявления «отдам» и «продам» в доме. query: что ищем (необязательно)."""
        async with sm() as session:
            items = await market.list_listings(session, ctx.house_id, ctx.user_id, q=query or None, limit=50)
        if not items:
            return "В «Вещах соседей» по этому запросу пока пусто."
        lines = [f"№{i.id} «{i.title}» - {'даром' if i.is_free else f'{i.price} ₽'}" for i in items]
        return short_list(f"Вещи соседей ({len(items)})", lines, "все объявления в приложении")

    @tool
    async def nearest_shelters() -> str:
        """Ближайшие укрытия к дому с маршрутом в Яндекс Картах и текущая тревога."""
        async with sm() as session:
            _, house = await load(session)
            items = await safety.nearest_shelters(session, house.lat, house.lon, limit=3)
            alert = await safety.active_alert(session, house.id)
        head = "Сейчас действует тревога! " if alert else ""
        if not items:
            return head + "В справочнике нет укрытий рядом с домом."
        return (
            head
            + "Ближайшие укрытия:\n"
            + "\n".join(f"{s.name}, {s.address}, ~{s.distance_m} м. Маршрут: {s.yandex_url}" for s in items)
        )

    @tool
    async def my_profile() -> str:
        """Очки, уровень и награды собеседника."""
        async with sm() as session:
            user, _ = await load(session)
        level, title, next_points = level_for(user.points)
        tail = f", до следующего уровня {next_points - user.points} очков" if next_points else ""
        return (
            f"У вас {user.points} очков, уровень {level} «{title}»{tail}. Награды есть в приложении, во вкладке «Ещё»."
        )

    @tool
    async def search_house(query: str) -> str:
        """Поиск по заявкам, событиям и объявлениям дома (RAG). Используй, если вопрос про конкретную тему."""
        async with sm() as session:
            found_i = await hybrid_search(session, Issue, query, where=[Issue.house_id == ctx.house_id], limit=3)
            found_e = await hybrid_search(session, Event, query, where=[Event.house_id == ctx.house_id], limit=3)
            found_l = await hybrid_search(session, Listing, query, where=[Listing.house_id == ctx.house_id], limit=3)
        # статус словами, а не кодом «voting»: строка уходит жителю как есть
        lines = [f"Заявка №{i.id} «{i.title}» ({STATUS_TITLES.get(i.status, i.status).lower()})" for i, _ in found_i]
        lines += [f"Событие №{e.id} «{e.title}» {_fmt_dt(e.starts_at)}" for e, _ in found_e]
        lines += [f"Объявление №{x.id} «{x.title}»" for x, _ in found_l]
        return "Нашёл:\n" + "\n".join(lines) if lines else "По этому запросу ничего не нашлось."

    return [
        house_status,
        list_issues,
        create_issue,
        vote_issue,
        list_events,
        create_event,
        create_announcement,
        list_listings,
        nearest_shelters,
        my_profile,
        search_house,
    ]


def now_msk() -> str:
    return datetime.now(UTC).astimezone(MSK).strftime("%A, %d.%m.%Y %H:%M")
