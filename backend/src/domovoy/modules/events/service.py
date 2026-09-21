from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.core.embeddings import embed
from domovoy.modules.achievements import service as achievements
from domovoy.modules.common_schemas import UserShort
from domovoy.modules.events.models import Event, EventComment, EventParticipant
from domovoy.modules.moderation.guardrails import moderate
from domovoy.modules.moderation.service import log_verdict
from domovoy.modules.users.models import House, User

MSK = ZoneInfo("Europe/Moscow")

KINDS: dict[str, str] = {
    "subbotnik": "Субботник",
    "meeting": "Собрание",
    "holiday": "Праздник",
    "sport": "Спорт",
    "kids": "Для детей",
    "other": "Встреча",
}
EventKind = Literal["subbotnik", "meeting", "holiday", "sport", "kids", "other"]


class EventIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=2000)
    kind: EventKind = "other"
    starts_at: datetime
    place: str = Field(default="Во дворе", max_length=200)
    max_participants: int | None = Field(default=None, ge=1, le=10000)


class EventOut(BaseModel):
    id: int
    title: str
    description: str
    kind: str
    kind_title: str
    starts_at: datetime
    place: str
    max_participants: int | None
    participants_count: int
    joined_by_me: bool
    comments_count: int
    author: UserShort
    created_at: datetime
    score: float | None = None


class EventDetail(EventOut):
    participants: list[UserShort]


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class CommentOut(BaseModel):
    id: int
    event_id: int
    author: UserShort
    text: str
    created_at: datetime


def event_out(ev: Event, joined: bool, score: float | None = None) -> EventOut:
    return EventOut(
        id=ev.id,
        title=ev.title,
        description=ev.description,
        kind=ev.kind,
        kind_title=KINDS.get(ev.kind, "Встреча"),
        starts_at=ev.starts_at,
        place=ev.place,
        max_participants=ev.max_participants,
        participants_count=ev.participants_count,
        joined_by_me=joined,
        comments_count=ev.comments_count,
        author=UserShort.of(ev.author),
        created_at=ev.created_at,
        score=score,
    )


def comment_out(c: EventComment) -> CommentOut:
    return CommentOut(id=c.id, event_id=c.event_id, author=UserShort.of(c.author), text=c.text, created_at=c.created_at)


async def get_event(session: AsyncSession, event_id: int, house_id: int) -> Event:
    ev = await session.get(Event, event_id)
    if ev is None or ev.house_id != house_id:
        raise HTTPException(404, "Событие не найдено")
    return ev


async def is_joined(session: AsyncSession, event_id: int, user_id: int) -> bool:
    return (await session.get(EventParticipant, (event_id, user_id))) is not None


async def event_detail(session: AsyncSession, ev: Event, user_id: int) -> EventDetail:
    participants = await session.scalars(
        select(EventParticipant).where(EventParticipant.event_id == ev.id).order_by(EventParticipant.created_at)
    )
    base = event_out(ev, await is_joined(session, ev.id, user_id))
    return EventDetail(**base.model_dump(), participants=[UserShort.of(p.user) for p in participants])


async def list_events(session: AsyncSession, house_id: int, user_id: int, scope: str = "upcoming") -> list[EventOut]:
    now = datetime.now(UTC)
    stmt = select(Event).where(Event.house_id == house_id)
    if scope == "past":
        stmt = stmt.where(Event.starts_at < now).order_by(Event.starts_at.desc())
    else:
        stmt = stmt.where(Event.starts_at >= now).order_by(Event.starts_at)
    events = list(await session.scalars(stmt.limit(50)))
    joined = set(
        await session.scalars(
            select(EventParticipant.event_id).where(
                EventParticipant.user_id == user_id, EventParticipant.event_id.in_([e.id for e in events])
            )
        )
    )
    return [event_out(e, e.id in joined) for e in events]


def join_buttons(ev: Event) -> list[list[dict[str, str]]]:
    return [
        [{"type": "callback", "text": f"🙋 Иду ({ev.participants_count})", "payload": f"join:{ev.id}"}],
        [{"type": "open_app", "text": "Подробнее и чат события", "payload": f"event_{ev.id}"}],
    ]


async def create_event(session: AsyncSession, *, user: User, house: House, data: EventIn) -> Event:
    starts_at = data.starts_at if data.starts_at.tzinfo else data.starts_at.replace(tzinfo=UTC)
    if starts_at < datetime.now(UTC):
        raise HTTPException(422, "Дата события уже прошла, выберите будущую")
    verdict = await moderate(f"{data.title}\n{data.description}")
    if verdict.blocked:
        raise HTTPException(422, f"Кузя не пропустил событие: {verdict.human_reason()}")
    ev = Event(
        house_id=house.id,
        author_id=user.id,
        title=data.title.strip(),
        description=data.description.strip(),
        kind=data.kind,
        starts_at=starts_at,
        place=data.place.strip() or "Во дворе",
        max_participants=data.max_participants,
        participants_count=1,
        embedding=embed(f"{data.title} {data.description} {data.place} {KINDS[data.kind]}"),
    )
    session.add(ev)
    await session.flush()
    session.add(EventParticipant(event_id=ev.id, user_id=user.id))
    awarded = await achievements.record_action(session, user, house.id, "event_created")
    await session.commit()
    await session.refresh(ev)
    await achievements.announce(house.id, user, awarded)
    await bus.emit(house.id, "event.created", event_out(ev, False).model_dump(mode="json"))
    await bus.emit(house.id, "pulse.changed", {})
    if house.max_chat_id:
        local = ev.starts_at.astimezone(MSK).strftime("%d.%m в %H:%M")
        await bus.bot_send(
            chat_id=house.max_chat_id,
            text=(
                f"📣 **{ev.title}**\n🗓 {local} (МСК)\n📍 {ev.place}\n"
                f"{ev.description[:300]}\n\nОрганизатор: {user.full_name}. Жмите «Иду», я напомню за пару часов!"
            ),
            buttons=join_buttons(ev),
        )
    return ev


async def join(session: AsyncSession, ev: Event, user: User) -> Event:
    if ev.starts_at < datetime.now(UTC):
        raise HTTPException(409, "Событие уже прошло")
    if await is_joined(session, ev.id, user.id):
        raise HTTPException(409, "Вы уже записаны")
    if ev.max_participants and ev.participants_count >= ev.max_participants:
        raise HTTPException(409, "Мест больше нет")
    session.add(EventParticipant(event_id=ev.id, user_id=user.id))
    ev.participants_count += 1
    awarded = await achievements.record_action(session, user, ev.house_id, "event_joined")
    if ev.kind == "subbotnik":
        awarded += await achievements.record_action(session, user, ev.house_id, "subbotnik_joined")
    await session.commit()
    await session.refresh(ev)
    await achievements.announce(ev.house_id, user, awarded)
    await bus.emit(ev.house_id, "event.updated", event_out(ev, False).model_dump(mode="json"))
    return ev


async def leave(session: AsyncSession, ev: Event, user: User) -> Event:
    row = await session.get(EventParticipant, (ev.id, user.id))
    if row is None:
        raise HTTPException(409, "Вы не были записаны")
    await session.delete(row)
    ev.participants_count = max(0, ev.participants_count - 1)
    await achievements.revoke_action(session, user, "event_joined")
    await session.commit()
    await session.refresh(ev)
    await bus.emit(ev.house_id, "event.updated", event_out(ev, False).model_dump(mode="json"))
    return ev


async def add_comment(session: AsyncSession, ev: Event, user: User, text: str) -> EventComment:
    verdict = await moderate(text)
    await log_verdict(session, source="app", text=text, verdict=verdict, user_max_id=user.max_user_id)
    if verdict.blocked:
        await session.commit()
        raise HTTPException(422, f"Кузя не пропустил комментарий: {verdict.human_reason()}. Давайте вежливо 🙏")
    comment = EventComment(event_id=ev.id, author_id=user.id, text=text.strip())
    session.add(comment)
    ev.comments_count += 1
    await session.flush()
    awarded = await achievements.record_action(session, user, ev.house_id, "comment_created")
    await session.commit()
    await session.refresh(comment)
    await achievements.announce(ev.house_id, user, awarded)
    await bus.emit(ev.house_id, "comment.created", comment_out(comment).model_dump(mode="json"))
    return comment


async def list_comments(session: AsyncSession, event_id: int) -> list[CommentOut]:
    rows = await session.scalars(
        select(EventComment).where(EventComment.event_id == event_id).order_by(EventComment.id).limit(300)
    )
    return [comment_out(c) for c in rows]
