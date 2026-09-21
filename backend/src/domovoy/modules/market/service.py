from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.core.embeddings import embed
from domovoy.core.storage import media_url
from domovoy.modules.achievements import service as achievements
from domovoy.modules.common_schemas import UserShort
from domovoy.modules.market.models import Listing
from domovoy.modules.moderation.guardrails import moderate
from domovoy.modules.search.hybrid import hybrid_search
from domovoy.modules.users.models import House, User

CATEGORIES: dict[str, str] = {
    "furniture": "Мебель",
    "electronics": "Техника",
    "kids": "Детское",
    "clothes": "Одежда",
    "tools": "Инструменты",
    "plants": "Растения",
    "food": "Еда и заготовки",
    "services": "Услуги соседям",
    "other": "Другое",
}
STATUS_TITLES = {"active": "Активно", "reserved": "Забронировано", "closed": "Закрыто"}


class ListingOut(BaseModel):
    id: int
    title: str
    description: str
    price: int
    is_free: bool
    category: str
    category_title: str
    status: str
    status_title: str
    photos: list[str]
    author: UserShort
    is_mine: bool
    created_at: datetime
    score: float | None = None


class ListingStatusIn(BaseModel):
    status: Literal["active", "reserved", "closed"]


class ContactIn(BaseModel):
    message: str = Field(default="", max_length=500)


def listing_out(item: Listing, user_id: int, score: float | None = None) -> ListingOut:
    return ListingOut(
        id=item.id,
        title=item.title,
        description=item.description,
        price=item.price,
        is_free=item.price == 0,
        category=item.category,
        category_title=CATEGORIES.get(item.category, "Другое"),
        status=item.status,
        status_title=STATUS_TITLES.get(item.status, item.status),
        photos=[media_url(k) for k in item.photos or []],
        author=UserShort.of(item.author),
        is_mine=item.author_id == user_id,
        created_at=item.created_at,
        score=score,
    )


async def get_listing(session: AsyncSession, listing_id: int, house_id: int) -> Listing:
    item = await session.get(Listing, listing_id)
    if item is None or item.house_id != house_id:
        raise HTTPException(404, "Объявление не найдено")
    return item


async def list_listings(
    session: AsyncSession,
    house_id: int,
    user_id: int,
    q: str | None = None,
    category: str | None = None,
    free: bool | None = None,
    limit: int = 60,
) -> list[ListingOut]:
    where = [Listing.house_id == house_id, Listing.status != "closed"]
    if category:
        where.append(Listing.category == category)
    if free:
        where.append(Listing.price == 0)
    if q:
        found = await hybrid_search(session, Listing, q, where=where, limit=limit)
        return [listing_out(i, user_id, s) for i, s in found]
    rows = await session.scalars(select(Listing).where(*where).order_by(Listing.created_at.desc()).limit(limit))
    return [listing_out(i, user_id) for i in rows]


async def create_listing(
    session: AsyncSession,
    *,
    user: User,
    house: House,
    title: str,
    description: str,
    price: int,
    category: str,
    photos: list[str],
) -> Listing:
    if category not in CATEGORIES:
        raise HTTPException(422, "Неизвестная категория")
    if price < 0:
        raise HTTPException(422, "Цена не может быть отрицательной")
    verdict = await moderate(f"{title}\n{description}")
    if verdict.blocked:
        raise HTTPException(422, f"Кузя не пропустил объявление: {verdict.human_reason()}")
    item = Listing(
        house_id=house.id,
        author_id=user.id,
        title=title.strip(),
        description=description.strip(),
        price=price,
        category=category,
        photos=photos,
        embedding=embed(f"{title} {description} {CATEGORIES[category]}"),
    )
    session.add(item)
    await session.flush()
    awarded = await achievements.record_action(session, user, house.id, "listing_created")
    if price == 0:
        awarded += await achievements.record_action(session, user, house.id, "listing_free")
    await session.commit()
    await session.refresh(item)
    await achievements.announce(house.id, user, awarded)
    await bus.emit(house.id, "listing.created", listing_out(item, 0).model_dump(mode="json"))
    await bus.emit(house.id, "pulse.changed", {})
    return item


async def contact_seller(item: Listing, buyer: User, message: str) -> None:
    if item.author_id == buyer.id:
        raise HTTPException(409, "Это ваше объявление")
    if item.status == "closed":
        raise HTTPException(409, "Объявление уже закрыто")
    who = f"{buyer.full_name}" + (f", кв. {buyer.apartment}" if buyer.apartment else "")
    contact = f" (@{buyer.username})" if buyer.username else ""
    text = f"📦 {who}{contact} интересуется вашим объявлением «{item.title}»."
    if message.strip():
        text += f"\n\nСообщение: {message.strip()}"
    text += "\n\nОтветьте соседу в личных сообщениях MAX."
    await bus.bot_send(
        user_id=item.author.max_user_id,
        text=text,
        buttons=[[{"type": "open_app", "text": "Открыть объявление", "payload": f"listing_{item.id}"}]],
    )
