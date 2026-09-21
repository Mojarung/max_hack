from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from domovoy.api.deps import CtxDep, SessionDep
from domovoy.core.config import get_settings
from domovoy.modules.achievements.catalog import level_for
from domovoy.modules.users.models import Membership, User
from domovoy.modules.users.pulse import PulseOut, house_pulse

router = APIRouter(tags=["Профиль и дом"])


class UserOut(BaseModel):
    id: int
    max_user_id: int
    first_name: str
    last_name: str
    username: str | None
    photo_url: str | None
    apartment: str | None
    points: int
    level: int
    level_title: str
    next_level_points: int | None


class HouseOut(BaseModel):
    id: int
    title: str
    address: str
    lat: float
    lon: float
    members_count: int
    vote_threshold_pct: int
    uk_name: str | None


class MeOut(BaseModel):
    user: UserOut
    house: HouseOut
    role: str
    mock: bool
    bot_username: str


class DevUser(BaseModel):
    max_user_id: int
    first_name: str
    last_name: str
    apartment: str | None
    role: str


def user_out(u: User) -> UserOut:
    level, title, next_points = level_for(u.points)
    return UserOut(
        id=u.id,
        max_user_id=u.max_user_id,
        first_name=u.first_name,
        last_name=u.last_name,
        username=u.username,
        photo_url=u.photo_url,
        apartment=u.apartment,
        points=u.points,
        level=level,
        level_title=title,
        next_level_points=next_points,
    )


@router.get("/me", response_model=MeOut)
async def me(ctx: CtxDep) -> MeOut:
    h = ctx.house
    s = get_settings()
    return MeOut(
        user=user_out(ctx.user),
        house=HouseOut(
            id=h.id,
            title=h.title,
            address=h.address,
            lat=h.lat,
            lon=h.lon,
            members_count=h.members_count,
            vote_threshold_pct=h.vote_threshold_pct,
            uk_name=h.uk_org.name if h.uk_org else None,
        ),
        role=ctx.role,
        mock=s.mock_max,
        bot_username=s.max_bot_username,
    )


@router.get("/house/pulse", response_model=PulseOut)
async def pulse(session: SessionDep, ctx: CtxDep) -> PulseOut:
    return await house_pulse(session, ctx.house.id)


@router.get("/dev/users", response_model=list[DevUser], tags=["Мок-режим"])
async def dev_users(session: SessionDep) -> list[DevUser]:
    if not get_settings().mock_max:
        raise HTTPException(404, "Мок-режим выключен")
    rows = await session.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(User.is_demo.is_(True))
        .order_by(User.id)
    )
    return [
        DevUser(
            max_user_id=u.max_user_id, first_name=u.first_name, last_name=u.last_name, apartment=u.apartment, role=r
        )
        for u, r in rows.unique().all()
    ]
