from datetime import datetime

import httpx
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Select, func, select

from domovoy.api.deps import CtxDep, SessionDep, require_admin
from domovoy.core.config import get_settings
from domovoy.modules.achievements.catalog import ACHIEVEMENTS, level_for
from domovoy.modules.events.models import Event, EventParticipant
from domovoy.modules.issues.catalog import OPEN_STATUSES
from domovoy.modules.issues.models import Issue, IssueVote
from domovoy.modules.market.models import Listing
from domovoy.modules.misc_models import UserAchievement
from domovoy.modules.users.membership import discover_houses, my_houses, sync_chat
from domovoy.modules.users.models import House, Membership, Organization, User
from domovoy.modules.users.pulse import PulseOut, house_pulse

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Профиль и дом"])

GEOCODER_URL = "https://nominatim.openstreetmap.org/search"


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
    onboarded: bool = False


class HouseOut(BaseModel):
    id: int
    title: str
    address: str
    lat: float
    lon: float
    members_count: int
    vote_threshold_pct: int
    uk_name: str | None
    uk_email: str | None = None
    uk_phone: str | None = None
    info: str = ""
    setup_done: bool = True
    is_demo: bool = False
    has_chat: bool = False
    bot_is_admin: bool | None = None


class MeOut(BaseModel):
    user: UserOut
    house: HouseOut
    role: str
    mock: bool
    bot_username: str


class HouseBrief(BaseModel):
    id: int
    title: str
    address: str
    role: str
    is_demo: bool
    is_current: bool


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
        onboarded=u.onboarded,
    )


def house_out(h: House) -> HouseOut:
    uk = h.uk_org
    return HouseOut(
        id=h.id,
        title=h.title,
        address=h.address,
        lat=h.lat,
        lon=h.lon,
        members_count=h.members_count,
        vote_threshold_pct=h.vote_threshold_pct,
        uk_name=uk.name if uk else None,
        uk_email=uk.email if uk else None,
        uk_phone=uk.phone if uk else None,
        info=h.info or "",
        setup_done=h.setup_done,
        is_demo=h.is_demo,
        has_chat=h.max_chat_id is not None,
        bot_is_admin=h.bot_is_admin,
    )


@router.get("/me", response_model=MeOut)
async def me(ctx: CtxDep) -> MeOut:
    s = get_settings()
    return MeOut(
        user=user_out(ctx.user),
        house=house_out(ctx.house),
        role=ctx.role,
        mock=s.mock_max,
        bot_username=s.max_bot_username,
    )


@router.post("/me/onboarded", response_model=MeOut)
async def onboarded(session: SessionDep, ctx: CtxDep) -> MeOut:
    """Житель прошёл обучалку при первом входе: больше её не показываем (на любом устройстве)."""
    user = await session.get(User, ctx.user.id)
    if user is None:
        raise HTTPException(404, "Житель не найден")
    user.onboarded = True
    await session.commit()
    ctx.user = user
    return await me(ctx)


@router.get("/houses", response_model=list[HouseBrief])
async def houses(session: SessionDep, ctx: CtxDep, refresh: bool = False) -> list[HouseBrief]:
    """Дома жителя. refresh=true заново ищет чаты с Кузей, где он состоит (дома добавляются сами)."""
    user = await session.get(User, ctx.user.id)
    assert user is not None
    await discover_houses(session, user, force=refresh)
    await session.commit()
    return [
        HouseBrief(
            id=h.id, title=h.title, address=h.address, role=r, is_demo=h.is_demo, is_current=h.id == ctx.house.id
        )
        for h, r in await my_houses(session, user)
    ]


@router.get("/house/pulse", response_model=PulseOut)
async def pulse(session: SessionDep, ctx: CtxDep) -> PulseOut:
    return await house_pulse(session, ctx.house.id)


class HouseIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=256)
    address: str | None = Field(default=None, min_length=5, max_length=512)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    vote_threshold_pct: int | None = Field(default=None, ge=5, le=100)
    info: str | None = Field(default=None, max_length=4000, description="Информация о доме для жителей")
    uk_name: str | None = Field(default=None, min_length=3, max_length=256, description="Управляющая организация")
    uk_email: EmailStr | None = Field(default=None, description="E-mail УК для обращений")
    uk_phone: str | None = Field(default=None, max_length=64)
    setup_done: bool | None = None
    apartment: str | None = Field(default=None, max_length=16, description="Квартира текущего жителя")


UK_FIELDS = {"uk_name", "uk_email", "uk_phone"}


async def _own_uk(session: SessionDep, house: House) -> Organization:
    """УК дома для редактирования. Общую запись справочника (демо-УК) не меняем, а заводим свою."""
    if house.uk_org_id is not None:
        shared = await session.scalar(
            select(func.count()).select_from(House).where(House.uk_org_id == house.uk_org_id, House.id != house.id)
        )
        org = await session.get(Organization, house.uk_org_id)
        if org is not None and not shared and not house.is_demo:
            return org
    base = await session.get(Organization, house.uk_org_id) if house.uk_org_id else None
    org = Organization(
        kind="uk",
        name=base.name if base else "Управляющая организация",
        email=base.email if base else None,
        phone=base.phone if base else None,
    )
    session.add(org)
    await session.flush()
    house.uk_org_id = org.id
    return org


@router.patch("/house", response_model=MeOut)
async def update_house(body: HouseIn, session: SessionDep, ctx: CtxDep) -> MeOut:
    """Настройка дома администратором (адрес, координаты, УК, информация, порог голосов) и своей квартиры."""
    fields = body.model_dump(exclude_unset=True, exclude={"apartment"})
    if fields and not ctx.is_admin:
        raise HTTPException(403, "Настройки дома меняет администратор")
    house = await session.get(House, ctx.house.id)
    user = await session.get(User, ctx.user.id)
    if house is None or user is None:
        raise HTTPException(404, "Дом не найден")
    for key, value in fields.items():
        if key not in UK_FIELDS and value is not None:
            setattr(house, key, value.strip() if isinstance(value, str) else value)
    if UK_FIELDS & fields.keys():
        org = await _own_uk(session, house)
        if body.uk_name:
            org.name = body.uk_name.strip()
        if "uk_email" in fields:
            org.email = str(body.uk_email) if body.uk_email else None
        if "uk_phone" in fields:
            org.phone = (body.uk_phone or "").strip() or None
    if body.apartment is not None:
        user.apartment = body.apartment.strip() or None
    await session.commit()
    await session.refresh(house)
    ctx.house, ctx.user = house, user
    return await me(ctx)


class SyncOut(BaseModel):
    members: int
    bot_is_admin: bool | None


@router.post("/house/sync", response_model=SyncOut)
async def sync_house(session: SessionDep, ctx: CtxDep) -> SyncOut:
    """Сверить жителей и администраторов с чатом MAX (кнопка в настройках дома)."""
    require_admin(ctx)
    house = await session.get(House, ctx.house.id)
    assert house is not None
    members = await sync_chat(session, house)
    await session.commit()
    return SyncOut(members=members, bot_is_admin=house.bot_is_admin)


class GeoResult(BaseModel):
    title: str
    lat: float
    lon: float


@router.get("/house/geocode", response_model=list[GeoResult])
async def geocode(q: str, ctx: CtxDep) -> list[GeoResult]:
    """Координаты дома по адресу (OpenStreetMap Nominatim): нужны для карты укрытий."""
    require_admin(ctx)
    if len(q.strip()) < 5:
        return []
    try:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "domovoy-kuzya/1.0"}) as http:
            resp = await http.get(
                GEOCODER_URL,
                params={"q": q, "format": "json", "limit": 5, "countrycodes": "ru", "accept-language": "ru"},
            )
            resp.raise_for_status()
            rows = resp.json()
    except (httpx.HTTPError, ValueError):
        log.warning("geocode.failed", exc_info=True)
        raise HTTPException(502, "Поиск адреса сейчас недоступен, поставьте точку на карте вручную") from None
    return [GeoResult(title=r["display_name"], lat=float(r["lat"]), lon=float(r["lon"])) for r in rows]


class Neighbour(BaseModel):
    id: int
    first_name: str
    last_name: str
    photo_url: str | None
    apartment: str | None
    role: str
    points: int
    level_title: str


class ProfileAchievement(BaseModel):
    code: str
    title: str
    icon: str
    awarded_at: datetime


class ProfileStats(BaseModel):
    issues_created: int
    issues_open: int
    votes: int
    events_joined: int
    listings_active: int


class ProfileOut(BaseModel):
    user: Neighbour
    is_me: bool
    username: str | None
    member_since: datetime
    level: int
    next_level_points: int | None
    stats: ProfileStats
    achievements: list[ProfileAchievement]


def neighbour(u: User, role: str) -> Neighbour:
    _, title, _ = level_for(u.points)
    return Neighbour(
        id=u.id,
        first_name=u.first_name,
        last_name=u.last_name,
        photo_url=u.photo_url,
        apartment=u.apartment,
        role=role,
        points=u.points,
        level_title=title,
    )


@router.get("/people", response_model=list[Neighbour], tags=["Соседи"])
async def people(session: SessionDep, ctx: CtxDep) -> list[Neighbour]:
    rows = await session.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.house_id == ctx.house.id)
        .order_by(Membership.role, User.first_name, User.last_name)
        .limit(500)
    )
    return [neighbour(u, r) for u, r in rows.unique().all()]


@router.get("/people/{user_id}", response_model=ProfileOut, tags=["Соседи"])
async def profile(user_id: int, session: SessionDep, ctx: CtxDep) -> ProfileOut:
    """Профиль соседа. Видны только жители того же дома; телефонов и MAX id нет."""
    row = (
        await session.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(User.id == user_id, Membership.house_id == ctx.house.id)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Житель не найден в вашем доме")
    user, member = row
    house_id = ctx.house.id

    async def count(stmt: Select[tuple[int]]) -> int:
        return int(await session.scalar(stmt) or 0)

    stats = ProfileStats(
        issues_created=await count(
            select(func.count()).select_from(Issue).where(Issue.author_id == user.id, Issue.house_id == house_id)
        ),
        issues_open=await count(
            select(func.count())
            .select_from(Issue)
            .where(Issue.author_id == user.id, Issue.house_id == house_id, Issue.status.in_(OPEN_STATUSES))
        ),
        votes=await count(
            select(func.count())
            .select_from(IssueVote)
            .join(Issue, Issue.id == IssueVote.issue_id)
            .where(IssueVote.user_id == user.id, Issue.house_id == house_id, Issue.author_id != user.id)
        ),
        events_joined=await count(
            select(func.count())
            .select_from(EventParticipant)
            .join(Event, Event.id == EventParticipant.event_id)
            .where(EventParticipant.user_id == user.id, Event.house_id == house_id)
        ),
        listings_active=await count(
            select(func.count())
            .select_from(Listing)
            .where(Listing.author_id == user.id, Listing.house_id == house_id, Listing.status != "closed")
        ),
    )
    defs = {a.code: a for a in ACHIEVEMENTS}
    earned = await session.scalars(
        select(UserAchievement).where(UserAchievement.user_id == user.id).order_by(UserAchievement.created_at.desc())
    )
    level, _, next_points = level_for(user.points)
    return ProfileOut(
        user=neighbour(user, member.role),
        is_me=user.id == ctx.user.id,
        username=user.username,
        member_since=member.created_at,
        level=level,
        next_level_points=next_points,
        stats=stats,
        achievements=[
            ProfileAchievement(code=a.code, title=defs[a.code].title, icon=defs[a.code].icon, awarded_at=a.created_at)
            for a in earned
            if a.code in defs
        ],
    )


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
