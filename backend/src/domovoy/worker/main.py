"""Фоновый воркер: отправка обращений, напоминания о событиях, эскалация просрочек."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select

from domovoy.core import aio, bus
from domovoy.core.bus import EXCHANGE, Q_ISSUE_DISPATCH, get_broker
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker, init_db
from domovoy.modules.events.models import Event, EventParticipant
from domovoy.modules.issues.models import Issue, IssueUpdate
from domovoy.modules.issues.schemas import issue_out
from domovoy.modules.issues.service import app_button
from domovoy.modules.users.models import House
from domovoy.worker.appeal import business_description, render_appeal, render_escalation

log = structlog.get_logger(__name__)
MSK = ZoneInfo("Europe/Moscow")
TICK_SECONDS = 60


async def dispatch_issue(issue_id: int) -> None:
    """Формирует обращение и «отправляет» его исполнителю.

    В MVP отправка модельная: текст сохраняется в карточке и в ленте статусов.
    В пилоте здесь подключается e-mail УК или ГИС ЖКХ (см. README).
    """
    async with get_sessionmaker()() as session:
        issue = await session.get(Issue, issue_id)
        if issue is None or issue.appeal_text:
            return
        issue.appeal_text = render_appeal(issue, await business_description(issue))
        org = issue.responsible_org.name if issue.responsible_org else "исполнителю"
        session.add(
            IssueUpdate(
                issue_id=issue.id,
                status="sent",
                note=f"Обращение сформировано и направлено: {org} (модельная отправка)",
            )
        )
        await session.commit()
        await session.refresh(issue)
        house = issue.house
        author_max_id = issue.author.max_user_id

    await bus.emit(house.id, "issue.updated", issue_out(issue, False).model_dump(mode="json"))
    deadline = issue.deadline_at.astimezone(MSK).strftime("%d.%m %H:%M") if issue.deadline_at else "-"
    text = (
        f"📨 Заявка **«{issue.title}»** набрала голоса. Я отправил обращение: {org}.\n"
        f"Срок по нормативу: до {deadline} (МСК). Слежу за сроком, при просрочке подготовлю жалобу в жилинспекцию."
    )
    buttons = [[app_button("Текст обращения и статус", f"issue_{issue.id}")]]
    if house.max_chat_id:
        await bus.bot_send(chat_id=house.max_chat_id, text=text, buttons=buttons)
    await bus.bot_send(user_id=author_max_id, text="Ваша заявка ушла исполнителю! " + text, buttons=buttons)


async def remind_events() -> None:
    now = datetime.now(UTC)
    horizon = now + timedelta(minutes=get_settings().event_reminder_minutes)
    async with get_sessionmaker()() as session:
        events = list(
            await session.scalars(
                select(Event).where(Event.reminded.is_(False), Event.starts_at > now, Event.starts_at <= horizon)
            )
        )
        plan: list[tuple[Event, list[tuple[int, str]], int | None]] = []
        for ev in events:
            ev.reminded = True
            participants = await session.scalars(select(EventParticipant).where(EventParticipant.event_id == ev.id))
            people = [(p.user.max_user_id, p.user.first_name) for p in participants]
            house = await session.get(House, ev.house_id)
            plan.append((ev, people, house.max_chat_id if house else None))
        await session.commit()

    for ev, people, chat_id in plan:
        local = ev.starts_at.astimezone(MSK).strftime("%H:%M")
        text = f"⏰ Напоминаю: «{ev.title}» сегодня в {local}, место: {ev.place}. Ждём вас!"
        buttons = [[app_button("Открыть событие", f"event_{ev.id}")]]
        for max_id, _ in people:
            await bus.bot_send(user_id=max_id, text=text, buttons=buttons)
        if chat_id:
            names = ", ".join(name for _, name in people[:10])
            await bus.bot_send(chat_id=chat_id, text=f"{text}\nИдут: {names}.", buttons=buttons)


async def escalate_overdue() -> None:
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        overdue = list(
            await session.scalars(
                select(Issue).where(
                    Issue.status.in_(("sent", "in_progress")), Issue.deadline_at < now, Issue.escalated_at.is_(None)
                )
            )
        )
        for issue in overdue:
            issue.escalated_at = now
            session.add(
                IssueUpdate(
                    issue_id=issue.id,
                    status=issue.status,
                    note="Срок истёк. Кузя подготовил жалобу в Госжилинспекцию:\n" + render_escalation(issue),
                )
            )
        await session.commit()
        for issue in overdue:
            await bus.emit(issue.house_id, "issue.updated", issue_out(issue, False).model_dump(mode="json"))
            await bus.emit(issue.house_id, "pulse.changed", {})
            if issue.house.max_chat_id:
                await bus.bot_send(
                    chat_id=issue.house.max_chat_id,
                    text=(
                        f"⏳ Исполнитель просрочил заявку «{issue.title}». "
                        "Я подготовил жалобу в Госжилинспекцию, текст в карточке заявки."
                    ),
                    buttons=[[app_button("Открыть заявку", f"issue_{issue.id}")]],
                )


async def scheduler() -> None:
    while True:
        for job in (remind_events, escalate_overdue):
            try:
                await job()
            except Exception:
                log.exception("worker.job_failed", job=job.__name__)
        await asyncio.sleep(TICK_SECONDS)


async def main() -> None:
    await init_db()
    broker = get_broker()

    @broker.subscriber(Q_ISSUE_DISPATCH, EXCHANGE)
    async def on_dispatch(msg: dict[str, Any]) -> None:
        await dispatch_issue(int(msg["issue_id"]))

    await broker.start()
    log.info("worker.started")
    try:
        await scheduler()
    finally:
        await broker.stop()


def run() -> None:
    aio.run(main())
