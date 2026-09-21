from fastapi import APIRouter

from domovoy.api.deps import CtxDep, SessionDep
from domovoy.modules.events import service
from domovoy.modules.events.service import CommentIn, CommentOut, EventDetail, EventIn, EventOut, comment_out

router = APIRouter(prefix="/events", tags=["События двора"])


@router.get("", response_model=list[EventOut])
async def list_events(session: SessionDep, ctx: CtxDep, scope: str = "upcoming") -> list[EventOut]:
    return await service.list_events(session, ctx.house.id, ctx.user.id, scope)


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(event_id: int, session: SessionDep, ctx: CtxDep) -> EventDetail:
    ev = await service.get_event(session, event_id, ctx.house.id)
    return await service.event_detail(session, ev, ctx.user.id)


@router.post("", response_model=EventDetail, status_code=201)
async def create_event(body: EventIn, session: SessionDep, ctx: CtxDep) -> EventDetail:
    ev = await service.create_event(session, user=ctx.user, house=ctx.house, data=body)
    return await service.event_detail(session, ev, ctx.user.id)


@router.post("/{event_id}/join", response_model=EventDetail)
async def join(event_id: int, session: SessionDep, ctx: CtxDep) -> EventDetail:
    ev = await service.get_event(session, event_id, ctx.house.id)
    await service.join(session, ev, ctx.user)
    return await service.event_detail(session, ev, ctx.user.id)


@router.delete("/{event_id}/join", response_model=EventDetail)
async def leave(event_id: int, session: SessionDep, ctx: CtxDep) -> EventDetail:
    ev = await service.get_event(session, event_id, ctx.house.id)
    await service.leave(session, ev, ctx.user)
    return await service.event_detail(session, ev, ctx.user.id)


@router.get("/{event_id}/comments", response_model=list[CommentOut])
async def comments(event_id: int, session: SessionDep, ctx: CtxDep) -> list[CommentOut]:
    await service.get_event(session, event_id, ctx.house.id)
    return await service.list_comments(session, event_id)


@router.post("/{event_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(event_id: int, body: CommentIn, session: SessionDep, ctx: CtxDep) -> CommentOut:
    ev = await service.get_event(session, event_id, ctx.house.id)
    return comment_out(await service.add_comment(session, ev, ctx.user, body.text))
