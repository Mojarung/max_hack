from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from domovoy.api.deps import CtxDep, SessionDep
from domovoy.core import bus
from domovoy.core.storage import save_uploads
from domovoy.modules.common_schemas import Ok
from domovoy.modules.market import service
from domovoy.modules.market.service import ContactIn, ListingOut, ListingStatusIn, listing_out

router = APIRouter(prefix="/listings", tags=["Барахолка"])


@router.get("/categories")
async def categories() -> list[dict[str, str]]:
    return [{"code": k, "title": v} for k, v in service.CATEGORIES.items()]


@router.get("", response_model=list[ListingOut])
async def list_listings(
    session: SessionDep,
    ctx: CtxDep,
    q: str | None = None,
    category: str | None = None,
    free: bool | None = None,
    scope: service.ListingScope = "active",
) -> list[ListingOut]:
    """scope=mine показывает свои объявления вместе с закрытыми: их можно вернуть в продажу."""
    return await service.list_listings(session, ctx.house.id, ctx.user.id, q, category, free, scope=scope)


@router.get("/{listing_id}", response_model=ListingOut)
async def get_listing(listing_id: int, session: SessionDep, ctx: CtxDep) -> ListingOut:
    return listing_out(await service.get_listing(session, listing_id, ctx.house.id), ctx.user.id)


@router.post("", response_model=ListingOut, status_code=201)
async def create_listing(
    session: SessionDep,
    ctx: CtxDep,
    title: Annotated[str, Form(min_length=3, max_length=120)],
    description: Annotated[str, Form(max_length=2000)] = "",
    price: Annotated[int, Form(ge=0, le=10_000_000)] = 0,
    category: Annotated[str, Form()] = "other",
    photos: Annotated[list[UploadFile] | None, File()] = None,
) -> ListingOut:
    keys = await save_uploads("listings", photos or [])
    item = await service.create_listing(
        session,
        user=ctx.user,
        house=ctx.house,
        title=title,
        description=description,
        price=price,
        category=category,
        photos=keys,
    )
    return listing_out(item, ctx.user.id)


@router.patch("/{listing_id}", response_model=ListingOut)
async def update_status(listing_id: int, body: ListingStatusIn, session: SessionDep, ctx: CtxDep) -> ListingOut:
    item = await service.get_listing(session, listing_id, ctx.house.id)
    if item.author_id != ctx.user.id and not ctx.is_admin:
        raise HTTPException(403, "Менять объявление может только автор")
    item.status = body.status
    await session.commit()
    await session.refresh(item)
    await bus.emit(ctx.house.id, "listing.updated", listing_out(item, 0).model_dump(mode="json"))
    return listing_out(item, ctx.user.id)


@router.delete("/{listing_id}", status_code=204)
async def delete_listing(listing_id: int, session: SessionDep, ctx: CtxDep) -> Response:
    item = await service.get_listing(session, listing_id, ctx.house.id)
    if item.author_id != ctx.user.id and not ctx.is_admin:
        raise HTTPException(403, "Удалить объявление может только автор")
    await session.delete(item)
    await session.commit()
    await bus.emit(ctx.house.id, "listing.updated", {"id": listing_id, "deleted": True})
    return Response(status_code=204)


@router.post("/{listing_id}/contact", response_model=Ok)
async def contact(listing_id: int, body: ContactIn, session: SessionDep, ctx: CtxDep) -> Ok:
    item = await service.get_listing(session, listing_id, ctx.house.id)
    await service.contact_seller(item, ctx.user, body.message)
    return Ok()
