"""Хранилище эмулятора чата MAX: общее для API (сообщения жителей) и бота (MockGateway)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.modules.misc_models import MockChatMessage

MID_PREFIX = "mock-"


class ChatFrom(BaseModel):
    user_id: int
    name: str


class ChatMessageOut(BaseModel):
    id: str
    chat_id: int
    from_: ChatFrom | None = None
    text: str
    buttons: list[list[dict[str, str]]]
    photos: list[str] = []
    deleted: bool
    notice: str | None
    created_at: datetime

    def dump(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["from"] = data.pop("from_")
        return data


def mid_of(msg: MockChatMessage) -> str:
    return f"{MID_PREFIX}{msg.id}"


def id_from_mid(mid: str) -> int | None:
    if not mid.startswith(MID_PREFIX):
        return None
    try:
        return int(mid.removeprefix(MID_PREFIX))
    except ValueError:
        return None


def to_out(m: MockChatMessage) -> ChatMessageOut:
    sender = ChatFrom(user_id=m.from_user_max_id, name=m.from_name or "Житель") if m.from_user_max_id else None
    return ChatMessageOut(
        id=mid_of(m),
        chat_id=m.chat_id,
        from_=sender,
        text=m.text,
        buttons=m.buttons or [],
        photos=m.photos or [],
        deleted=m.deleted,
        notice=m.notice,
        created_at=m.created_at,
    )


async def store(
    session: AsyncSession,
    *,
    chat_id: int,
    text: str,
    from_user_max_id: int | None = None,
    from_name: str | None = None,
    buttons: list[list[dict[str, str]]] | None = None,
    photos: list[str] | None = None,
) -> MockChatMessage:
    msg = MockChatMessage(
        chat_id=chat_id,
        text=text,
        from_user_max_id=from_user_max_id,
        from_name=from_name,
        buttons=buttons or [],
        photos=photos or [],
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    await bus.emit(None, "chat.message", to_out(msg).dump())
    return msg


async def update(session: AsyncSession, mid: str, **fields: Any) -> MockChatMessage | None:
    msg_id = id_from_mid(mid)
    msg = await session.get(MockChatMessage, msg_id) if msg_id else None
    if msg is None:
        return None
    for key, value in fields.items():
        setattr(msg, key, value)
    await session.commit()
    await session.refresh(msg)
    await bus.emit(None, "chat.message", to_out(msg).dump())
    return msg


async def history(session: AsyncSession, chat_id: int, limit: int = 200) -> list[ChatMessageOut]:
    rows = list(
        await session.scalars(
            select(MockChatMessage)
            .where(MockChatMessage.chat_id == chat_id)
            .order_by(MockChatMessage.id.desc())
            .limit(limit)
        )
    )
    return [to_out(m) for m in reversed(rows)]
