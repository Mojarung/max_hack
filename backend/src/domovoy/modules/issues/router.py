from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from domovoy.api.deps import CtxDep, SessionDep
from domovoy.core.storage import save_uploads
from domovoy.modules.issues import service
from domovoy.modules.issues.catalog import ORG_KINDS, category
from domovoy.modules.issues.classifier import classify
from domovoy.modules.issues.schemas import (
    ClassificationOut,
    IssueDetail,
    IssueOut,
    StatusIn,
    TextIn,
    issue_detail,
)

router = APIRouter(prefix="/issues", tags=["Проблемы дома"])


async def _detail(session: SessionDep, issue_id: int, ctx: CtxDep) -> IssueDetail:
    issue = await service.get_issue(session, issue_id, ctx.house.id)
    voted = await service.has_voted(session, issue.id, ctx.user.id)
    return issue_detail(issue, voted, await service.timeline(session, issue.id))


@router.get("", response_model=list[IssueOut])
async def list_issues(
    session: SessionDep, ctx: CtxDep, status: str | None = None, q: str | None = None
) -> list[IssueOut]:
    return await service.list_issues(session, ctx.house.id, ctx.user.id, status, q)


@router.post("/similar", response_model=list[IssueOut])
async def similar(body: TextIn, session: SessionDep, ctx: CtxDep) -> list[IssueOut]:
    return await service.similar_issues(session, ctx.house.id, ctx.user.id, body.text)


@router.post("/classify", response_model=ClassificationOut)
async def classify_text(body: TextIn, session: SessionDep, ctx: CtxDep) -> ClassificationOut:
    result = await classify(body.text)
    cat = category(result.category)
    org = await service.responsible_org(session, ctx.house, cat.org_kind)
    return ClassificationOut(
        category=cat.code,
        category_title=cat.title,
        title=result.title,
        org_kind=cat.org_kind,
        org_name=org.name if org else ORG_KINDS[cat.org_kind],
        legal_basis=cat.legal_basis,
        deadline_hours=cat.deadline_hours,
        confidence=result.confidence,
        source=result.source,
    )


@router.get("/{issue_id}", response_model=IssueDetail)
async def get_issue(issue_id: int, session: SessionDep, ctx: CtxDep) -> IssueDetail:
    return await _detail(session, issue_id, ctx)


@router.post("", response_model=IssueDetail, status_code=201)
async def create_issue(
    session: SessionDep,
    ctx: CtxDep,
    description: Annotated[str, Form(min_length=5, max_length=4000)],
    title: Annotated[str | None, Form(max_length=200)] = None,
    location_hint: Annotated[str | None, Form(max_length=200)] = None,
    photos: Annotated[list[UploadFile] | None, File()] = None,
) -> IssueDetail:
    keys = await save_uploads("issues", photos or [])
    issue = await service.create_issue(
        session,
        user=ctx.user,
        house=ctx.house,
        description=description,
        title=title or None,
        location_hint=location_hint,
        photos=keys,
    )
    return await _detail(session, issue.id, ctx)


@router.post("/{issue_id}/vote", response_model=IssueDetail)
async def vote(issue_id: int, session: SessionDep, ctx: CtxDep) -> IssueDetail:
    issue = await service.get_issue(session, issue_id, ctx.house.id)
    await service.vote(session, issue, ctx.user)
    return await _detail(session, issue_id, ctx)


@router.delete("/{issue_id}/vote", response_model=IssueDetail)
async def unvote(issue_id: int, session: SessionDep, ctx: CtxDep) -> IssueDetail:
    issue = await service.get_issue(session, issue_id, ctx.house.id)
    await service.unvote(session, issue, ctx.user)
    return await _detail(session, issue_id, ctx)


@router.post("/{issue_id}/status", response_model=IssueDetail)
async def set_status(issue_id: int, body: StatusIn, session: SessionDep, ctx: CtxDep) -> IssueDetail:
    issue = await service.get_issue(session, issue_id, ctx.house.id)
    await service.set_status(session, issue, ctx.user, ctx.is_admin, body.status, body.note)
    return await _detail(session, issue_id, ctx)
