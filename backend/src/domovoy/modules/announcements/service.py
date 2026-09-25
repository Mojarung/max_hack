"""Объявления дома: доска в мини-приложении и сообщение Кузи в чате (по желанию закреплённое).

Создать объявление может любой житель (из приложения или попросив Кузю в чате), текст проходит модерацию.
Закреплять в чате и удалять чужие объявления может администратор дома.
"""

from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.modules.common_schemas import UserShort
from domovoy.modules.misc_models import Announcement
from domovoy.modules.moderation.guardrails import moderate
from domovoy.modules.users.models import House, User

LIST_LIMIT = 30


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    text: str = Field(default="", max_length=2000)
    pin: bool = Field(default=False, description="Закрепить в чате дома (только администратор)")


class AnnouncementOut(BaseModel):
    id: int
    title: str
    text: str
    pinned: bool
    event_id: int | None
    author: UserShort | None
    is_mine: bool
    created_at: datetime


def announcement_out(a: Announcement, author: User | None, user_id: int) -> AnnouncementOut:
    return AnnouncementOut(
        id=a.id,
        title=a.title,
        text=a.text,
        pinned=a.pinned,
        event_id=a.event_id,
        author=UserShort.of(author) if author else None,
        is_mine=a.author_id == user_id,
        created_at=a.created_at,
    )


def chat_text(title: str, text: str, author: User | None) -> str:
    body = f"📢 **Объявление: {title}**"
    if text.strip():
        body += f"\n\n{text.strip()}"
    if author is not None:
        body += f"\n\n— {author.full_name}"
    return body


async def create_announcement(
    session: AsyncSession,
    *,
    user: User,
    house: House,
    title: str,
    text: str = "",
    pin: bool = False,
    event_id: int | None = None,
    post_to_chat: bool = True,
) -> Announcement:
    verdict = await moderate(f"{title}\n{text}")
    if verdict.blocked:
        raise HTTPException(422, f"Кузя не пропустил объявление: {verdict.human_reason()}")
    item = Announcement(
        house_id=house.id,
        author_id=user.id,
        title=title.strip()[:120],
        text=text.strip()[:2000],
        pinned=pin,
        event_id=event_id,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    await bus.emit(house.id, "announcement.created", announcement_out(item, user, 0).model_dump(mode="json"))
    if post_to_chat and house.max_chat_id:
        buttons = [[{"type": "open_app", "text": "Все объявления дома", "payload": "announcements"}]]
        if event_id:
            buttons.insert(0, [{"type": "callback", "text": "🙋 Иду", "payload": f"join:{event_id}"}])
        await bus.bot_send(
            chat_id=house.max_chat_id, text=chat_text(item.title, item.text, user), buttons=buttons, pin=pin
        )
    return item


async def list_announcements(session: AsyncSession, house_id: int, user_id: int) -> list[AnnouncementOut]:
    rows = await session.execute(
        select(Announcement, User)
        .outerjoin(User, User.id == Announcement.author_id)
        .where(Announcement.house_id == house_id)
        .order_by(Announcement.pinned.desc(), Announcement.created_at.desc())
        .limit(LIST_LIMIT)
    )
    return [announcement_out(a, u, user_id) for a, u in rows.all()]


async def get_announcement(session: AsyncSession, item_id: int, house_id: int) -> Announcement:
    item = await session.get(Announcement, item_id)
    if item is None or item.house_id != house_id:
        raise HTTPException(404, "Объявление не найдено")
    return item
