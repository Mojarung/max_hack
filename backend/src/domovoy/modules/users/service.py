from math import ceil
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core.config import get_settings
from domovoy.modules.users.models import House, Membership, User


async def upsert_user(session: AsyncSession, max_user: dict[str, Any], *, is_demo: bool = False) -> User:
    """Создаёт или обновляет пользователя по данным MAX (initData, апдейт бота)."""
    max_id = int(max_user.get("id") or max_user.get("user_id") or 0)
    user = await session.scalar(select(User).where(User.max_user_id == max_id))
    first = max_user.get("first_name") or max_user.get("name") or ""
    if user is None:
        user = User(
            max_user_id=max_id,
            first_name=first,
            last_name=max_user.get("last_name") or "",
            username=max_user.get("username"),
            photo_url=max_user.get("photo_url"),
            is_demo=is_demo,
        )
        session.add(user)
        await session.flush()
        return user
    if first:
        user.first_name = first
        user.last_name = max_user.get("last_name") or user.last_name
    user.username = max_user.get("username") or user.username
    user.photo_url = max_user.get("photo_url") or user.photo_url
    return user


async def ensure_membership(session: AsyncSession, user: User, house: House, role: str = "resident") -> Membership:
    member = await session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.house_id == house.id)
    )
    if member is None:
        member = Membership(user_id=user.id, house_id=house.id, role=role)
        session.add(member)
        await session.flush()
    return member


async def house_by_chat(session: AsyncSession, chat_id: int) -> House | None:
    return await session.scalar(select(House).where(House.max_chat_id == chat_id))


async def ensure_house_for_chat(
    session: AsyncSession, chat_id: int, title: str | None, members_count: int | None = None
) -> House:
    """Бот добавлен в новый чат: заводим дом с УК по умолчанию из демо-справочника."""
    house = await house_by_chat(session, chat_id)
    if house is None:
        template = await session.scalar(select(House).order_by(House.id).limit(1))
        house = House(
            max_chat_id=chat_id,
            title=title or "Мой дом",
            address=template.address if template else "",
            lat=template.lat if template else 55.7963,
            lon=template.lon if template else 49.1088,
            uk_org_id=template.uk_org_id if template else None,
            vote_threshold_pct=get_settings().default_vote_threshold_pct,
        )
        session.add(house)
    if members_count:
        house.members_count = members_count
    if title:
        house.title = title
    await session.flush()
    return house


async def first_house_of(session: AsyncSession, user: User) -> House | None:
    return await session.scalar(
        select(House).join(Membership, Membership.house_id == House.id).where(Membership.user_id == user.id).limit(1)
    )


def votes_needed(house: House) -> int:
    """Порог голосов = процент от участников чата, но не меньше минимального."""
    s = get_settings()
    return max(s.min_votes_needed, ceil(house.members_count * house.vote_threshold_pct / 100))
