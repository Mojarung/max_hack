from fastapi import APIRouter, Query
from pydantic import BaseModel

from domovoy.api.deps import CtxDep, SessionDep
from domovoy.modules.events.models import Event
from domovoy.modules.events.service import EventOut, event_out
from domovoy.modules.issues.schemas import IssueOut
from domovoy.modules.issues.service import list_issues
from domovoy.modules.market.service import ListingOut, list_listings
from domovoy.modules.search.hybrid import hybrid_search

router = APIRouter(tags=["Поиск"])


class SearchOut(BaseModel):
    issues: list[IssueOut]
    events: list[EventOut]
    listings: list[ListingOut]


@router.get("/search", response_model=SearchOut)
async def search(session: SessionDep, ctx: CtxDep, q: str = Query(min_length=2, max_length=200)) -> SearchOut:
    events = await hybrid_search(session, Event, q, where=[Event.house_id == ctx.house.id], limit=10)
    return SearchOut(
        issues=(await list_issues(session, ctx.house.id, ctx.user.id, q=q, limit=10)),
        events=[event_out(e, False, s) for e, s in events],
        listings=await list_listings(session, ctx.house.id, ctx.user.id, q=q, limit=10),
    )
