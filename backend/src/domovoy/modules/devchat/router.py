"""Эмулятор чата MAX. Работает только при MOCK_MAX=true.

Сообщения жителей превращаются в апдейты того же формата, что присылает MAX
(`message_created`, `message_callback`), и уходят боту через RabbitMQ. Бот обрабатывает
их тем же кодом, что и настоящие апдейты, а отвечает через MockGateway.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from domovoy.api.deps import SessionDep
from domovoy.core import bus
from domovoy.core.config import get_settings
from domovoy.modules.common_schemas import Ok
from domovoy.modules.devchat import service
from domovoy.modules.users.models import House, User

router = APIRouter(prefix="/dev", tags=["Мок-режим"])


class SendIn(BaseModel):
    chat_id: int
    user_id: int
    text: str = Field(min_length=1, max_length=4000)


class CallbackIn(BaseModel):
    chat_id: int
    user_id: int
    message_id: str
    payload: str = Field(max_length=1024)


class ChatInfo(BaseModel):
    chat_id: int
    title: str
    type: str


def _ensure_mock() -> None:
    if not get_settings().mock_max:
        raise HTTPException(404, "Мок-режим выключен")


def max_user(u: User) -> dict[str, Any]:
    return {"user_id": u.max_user_id, "first_name": u.first_name, "last_name": u.last_name, "username": u.username}


async def _chat_type(session: SessionDep, chat_id: int) -> str:
    house = await session.scalar(select(House).where(House.max_chat_id == chat_id))
    return "chat" if house else "dialog"


async def _user(session: SessionDep, max_id: int) -> User:
    user = await session.scalar(select(User).where(User.max_user_id == max_id))
    if user is None:
        raise HTTPException(404, "Демо-пользователь не найден")
    return user


@router.get("/chats", response_model=list[ChatInfo])
async def chats(
    session: SessionDep, user_id: int | None = None, x_dev_user: Annotated[int | None, Header()] = None
) -> list[ChatInfo]:
    _ensure_mock()
    user_id = user_id or x_dev_user
    houses = await session.scalars(select(House).where(House.is_demo.is_(True), House.max_chat_id.is_not(None)))
    items = [ChatInfo(chat_id=h.max_chat_id or 0, title=f"Чат: {h.title}", type="chat") for h in houses]
    if user_id:
        items.append(ChatInfo(chat_id=user_id, title="Личка с Кузей", type="dialog"))
    return items


@router.get("/chat/messages")
async def messages(session: SessionDep, chat_id: int) -> list[dict[str, Any]]:
    _ensure_mock()
    return [m.dump() for m in await service.history(session, chat_id)]


@router.post("/chat/send", response_model=Ok)
async def send(body: SendIn, session: SessionDep) -> Ok:
    _ensure_mock()
    user = await _user(session, body.user_id)
    chat_type = await _chat_type(session, body.chat_id)
    if chat_type == "dialog" and body.chat_id != user.max_user_id:
        raise HTTPException(403, "Нельзя писать в чужую личку")
    msg = await service.store(
        session, chat_id=body.chat_id, text=body.text, from_user_max_id=user.max_user_id, from_name=user.full_name
    )
    await bus.publish(
        "bot.inbound",
        {
            "update_type": "message_created",
            "mock": True,
            "message": {
                "sender": max_user(user),
                "recipient": {"chat_id": body.chat_id, "chat_type": chat_type},
                "body": {"mid": service.mid_of(msg), "text": body.text},
            },
        },
    )
    return Ok()


@router.post("/chat/callback", response_model=Ok)
async def callback(body: CallbackIn, session: SessionDep) -> Ok:
    _ensure_mock()
    user = await _user(session, body.user_id)
    await bus.publish(
        "bot.inbound",
        {
            "update_type": "message_callback",
            "mock": True,
            "callback": {
                "callback_id": f"mock-cb-{uuid.uuid4().hex[:12]}",
                "payload": body.payload,
                "user": max_user(user),
            },
            "message": {
                "recipient": {"chat_id": body.chat_id, "chat_type": await _chat_type(session, body.chat_id)},
                "body": {"mid": body.message_id},
            },
        },
    )
    return Ok()
