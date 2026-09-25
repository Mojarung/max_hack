from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from domovoy.api.deps import CtxDep, SessionDep
from domovoy.core import bus
from domovoy.modules.announcements import service
from domovoy.modules.announcements.service import AnnouncementIn, AnnouncementOut, announcement_out
from domovoy.modules.users.models import User

router = APIRouter(prefix="/announcements", tags=["Объявления дома"])


class PinIn(BaseModel):
    pinned: bool


@router.get("", response_model=list[AnnouncementOut])
async def list_announcements(session: SessionDep, ctx: CtxDep) -> list[AnnouncementOut]:
    return await service.list_announcements(session, ctx.house.id, ctx.user.id)


@router.post("", response_model=AnnouncementOut, status_code=201)
async def create(body: AnnouncementIn, session: SessionDep, ctx: CtxDep) -> AnnouncementOut:
    item = await service.create_announcement(
        session, user=ctx.user, house=ctx.house, title=body.title, text=body.text, pin=body.pin and ctx.is_admin
    )
    return announcement_out(item, ctx.user, ctx.user.id)


@router.patch("/{item_id}", response_model=AnnouncementOut)
async def pin(item_id: int, body: PinIn, session: SessionDep, ctx: CtxDep) -> AnnouncementOut:
    if not ctx.is_admin:
        raise HTTPException(403, "Закреплять объявления может администратор дома")
    item = await service.get_announcement(session, item_id, ctx.house.id)
    item.pinned = body.pinned
    await session.commit()
    author = await session.get(User, item.author_id) if item.author_id else None
    out = announcement_out(item, author, ctx.user.id)
    await bus.emit(ctx.house.id, "announcement.updated", out.model_dump(mode="json"))
    return out


@router.delete("/{item_id}", status_code=204)
async def delete(item_id: int, session: SessionDep, ctx: CtxDep) -> Response:
    item = await service.get_announcement(session, item_id, ctx.house.id)
    if item.author_id != ctx.user.id and not ctx.is_admin:
        raise HTTPException(403, "Удалить объявление может автор или администратор")
    await session.delete(item)
    await session.commit()
    await bus.emit(ctx.house.id, "announcement.updated", {"id": item_id, "deleted": True})
    return Response(status_code=204)
