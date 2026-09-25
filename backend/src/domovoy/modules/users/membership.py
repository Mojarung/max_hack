"""Кто в каком доме и с какими правами. Источник правды - чат дома в MAX.

- Житель состоит в доме, если он участник чата, где живёт Кузя.
- Администратор дома = администратор или владелец этого чата.
- Активный дом (`User.active_house_id`) один для мини-приложения и лички с ботом,
  поэтому оба канала показывают один и тот же дом.

Без токена MAX (мок-режим) и для демо-дома сверка с MAX пропускается: права берутся из БД.
Если боту не хватает прав на список участников, существующие членства не трогаем.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.bot.max_client import MaxApiError
from domovoy.core.max_api import get_max_client
from domovoy.modules.users.models import House, Membership, User
from domovoy.modules.users.service import ensure_membership, upsert_user

log = structlog.get_logger(__name__)

RECHECK = timedelta(minutes=10)
DISCOVERY_CONCURRENCY = 5


def _now() -> datetime:
    return datetime.now(UTC)


def _fresh(ts: datetime | None) -> bool:
    return ts is not None and _now() - ts < RECHECK


def role_of(member: dict[str, Any]) -> str:
    return "admin" if member.get("is_owner") or member.get("is_admin") else "resident"


def _checkable(house: House) -> bool:
    return get_max_client() is not None and not house.is_demo and house.max_chat_id is not None


async def get_membership(session: AsyncSession, user_id: int, house_id: int) -> Membership | None:
    return await session.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.house_id == house_id)
    )


async def check_access(session: AsyncSession, user: User, house: House, *, force: bool = False) -> str | None:
    """Роль жителя в доме с учётом чата MAX или None, если доступа нет.

    Результат сверки кэшируется на 10 минут в `Membership.checked_at`, чтобы не спрашивать MAX на каждый запрос.
    """
    member = await get_membership(session, user.id, house.id)
    if member is None and not _checkable(house):
        return None
    if not _checkable(house) or (member is not None and not force and _fresh(member.checked_at)):
        return member.role if member else None
    client = get_max_client()
    assert client is not None and house.max_chat_id is not None
    try:
        found = await client.chat_members(house.max_chat_id, [user.max_user_id])
    except (MaxApiError, OSError):
        # боту не дали прав администратора: доверяем тому, что уже знаем
        log.warning("membership.check_failed", house_id=house.id, exc_info=True)
        return member.role if member else None
    me = next((m for m in found if int(m.get("user_id") or 0) == user.max_user_id), None)
    if me is None:
        if member is not None and house.bot_is_admin:
            # житель вышел из чата: доступ к дому закрываем
            await session.delete(member)
            if user.active_house_id == house.id:
                user.active_house_id = None
            await session.flush()
            log.info("membership.revoked", house_id=house.id, user_id=user.id)
            return None
        return member.role if member else None
    if member is None:
        member = await ensure_membership(session, user, house, role=role_of(me))
    member.role = role_of(me)
    member.checked_at = _now()
    await session.flush()
    return member.role


async def discover_houses(session: AsyncSession, user: User, *, force: bool = False) -> int:
    """Ищет чаты с Кузей, где состоит житель, и добавляет эти дома. Возвращает число новых домов."""
    client = get_max_client()
    if client is None or (not force and _fresh(user.chats_checked_at)):
        return 0
    known = select(Membership.house_id).where(Membership.user_id == user.id)
    houses = list(
        await session.scalars(
            select(House).where(House.is_demo.is_(False), House.max_chat_id.is_not(None), House.id.not_in(known))
        )
    )
    sem = asyncio.Semaphore(DISCOVERY_CONCURRENCY)

    async def probe(house: House) -> tuple[House, dict[str, Any] | None]:
        async with sem:
            try:
                found = await client.chat_members(int(house.max_chat_id or 0), [user.max_user_id])
            except (MaxApiError, OSError):
                return house, None
        return house, next((m for m in found if int(m.get("user_id") or 0) == user.max_user_id), None)

    added = 0
    for house, member in await asyncio.gather(*(probe(h) for h in houses)):
        if member is None:
            continue
        m = await ensure_membership(session, user, house, role=role_of(member))
        m.checked_at = _now()
        added += 1
    user.chats_checked_at = _now()
    await session.flush()
    if added:
        log.info("membership.discovered", user_id=user.id, added=added)
    return added


async def sync_chat(session: AsyncSession, house: House) -> int:
    """Полная сверка чата: права бота, все участники и администраторы. Возвращает число участников.

    Вызывается, когда Кузю добавили в чат, и по кнопке администратора. Жители сразу видят дом в приложении,
    даже если ещё ни разу не писали в чат.
    """
    client = get_max_client()
    if client is None or house.max_chat_id is None or house.is_demo:
        return 0
    chat_id = house.max_chat_id
    try:
        me = await client.my_membership(chat_id)
        house.bot_is_admin = bool(me.get("is_admin") or me.get("is_owner"))
    except (MaxApiError, OSError):
        log.warning("membership.bot_rights_unknown", house_id=house.id, exc_info=True)
    try:
        members = await client.chat_members(chat_id)
    except (MaxApiError, OSError):
        log.warning("membership.members_unavailable", house_id=house.id, exc_info=True)
        await session.flush()
        return 0
    now = _now()
    seen: set[int] = set()
    for m in members:
        if m.get("is_bot") or not m.get("user_id"):
            continue
        user = await upsert_user(session, {**m, "photo_url": m.get("avatar_url")})
        member = await ensure_membership(session, user, house, role=role_of(m))
        member.role = role_of(m)
        member.checked_at = now
        seen.add(user.id)
    if members:
        house.members_count = max(len(seen), 1)
        if house.bot_is_admin:
            # кто ушёл из чата, теряет доступ к дому
            await session.execute(
                delete(Membership).where(Membership.house_id == house.id, Membership.user_id.not_in(seen))
            )
    await session.flush()
    log.info("membership.chat_synced", house_id=house.id, members=len(seen), bot_admin=house.bot_is_admin)
    return len(seen)


async def my_houses(session: AsyncSession, user: User) -> list[tuple[House, str]]:
    """Дома жителя: сначала настоящие, потом демо; внутри по времени вступления."""
    rows = await session.execute(
        select(House, Membership.role)
        .join(Membership, Membership.house_id == House.id)
        .where(Membership.user_id == user.id)
        .order_by(House.is_demo, Membership.id)
    )
    return [(h, r) for h, r in rows.unique().all()]


async def current_house(session: AsyncSession, user: User) -> House | None:
    """Активный дом жителя; если не выбран - первый настоящий, потом демо."""
    if user.active_house_id is not None and await get_membership(session, user.id, user.active_house_id):
        return await session.get(House, user.active_house_id)
    houses = await my_houses(session, user)
    return houses[0][0] if houses else None


def set_active(user: User, house: House) -> None:
    if user.active_house_id != house.id:
        user.active_house_id = house.id
