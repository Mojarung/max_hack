"""Зависимости FastAPI: сессия БД и контекст жителя (пользователь, дом, роль)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core.config import get_settings
from domovoy.core.db import get_session
from domovoy.core.max_auth import InitDataError, validate_init_data
from domovoy.modules.users.models import House, Membership, User
from domovoy.modules.users.service import (
    ensure_membership,
    first_house_of,
    house_by_chat,
    upsert_user,
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(slots=True)
class Ctx:
    user: User
    house: House
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def resolve_ctx(
    session: AsyncSession,
    init_data: str | None,
    dev_user: int | None,
    house_id: int | None,
) -> Ctx:
    settings = get_settings()
    chat_id: int | None = None
    if init_data:
        try:
            data = validate_init_data(init_data, settings.bot_token, settings.init_data_ttl_seconds)
        except InitDataError as exc:
            raise HTTPException(401, str(exc)) from exc
        user = await upsert_user(session, data.user)
        if data.chat and data.chat.get("type") == "CHAT":
            chat_id = int(data.chat["id"])
    elif dev_user is not None and settings.mock_max:
        found = await session.scalar(select(User).where(User.max_user_id == dev_user))
        if found is None:
            raise HTTPException(401, "Демо-пользователь не найден")
        user = found
    else:
        raise HTTPException(401, "Откройте приложение из MAX")

    # Дом из заголовка принимается только если житель уже в нём состоит: заголовок присылает клиент.
    if house_id is not None:
        role = await member_role(session, user.id, house_id)
        chosen = await session.get(House, house_id) if role else None
        if chosen is None or role is None:
            raise HTTPException(403, "Вы не состоите в этом доме")
        await session.commit()
        return Ctx(user=user, house=chosen, role=role)

    # Доверенные источники дома: чат из подписанного initData, затем существующее членство.
    house: House | None = None
    if chat_id is not None:
        house = await house_by_chat(session, chat_id)
    if house is None:
        house = await first_house_of(session, user)
    if house is None and settings.pilot_house_fallback:
        # Житель открыл приложение из лички, ещё не написав в чат дома: подключаем к пилотному дому.
        house = await session.scalar(select(House).order_by(House.id).limit(1))
    if house is None:
        raise HTTPException(404, "Дом ещё не подключён: добавьте Кузю в чат дома и откройте приложение оттуда")

    member = await ensure_membership(session, user, house)
    await session.commit()
    return Ctx(user=user, house=house, role=member.role)


async def get_ctx(
    session: SessionDep,
    x_max_init_data: Annotated[str | None, Header()] = None,
    x_dev_user: Annotated[int | None, Header()] = None,
    x_house_id: Annotated[int | None, Header()] = None,
) -> Ctx:
    return await resolve_ctx(session, x_max_init_data, x_dev_user, x_house_id)


CtxDep = Annotated[Ctx, Depends(get_ctx)]


def require_admin_or_mock(ctx: Ctx) -> None:
    """Тестовая тревога в мок-режиме доступна всем демо-жителям, иначе только администратору."""
    if not (ctx.is_admin or get_settings().mock_max):
        raise HTTPException(403, "Действие доступно только администратору дома")


def require_admin(ctx: Ctx) -> None:
    if not ctx.is_admin:
        raise HTTPException(403, "Действие доступно только администратору дома")


async def member_role(session: AsyncSession, user_id: int, house_id: int) -> str | None:
    return await session.scalar(
        select(Membership.role).where(Membership.user_id == user_id, Membership.house_id == house_id)
    )
