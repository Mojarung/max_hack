from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from domovoy.core.storage import media_url
from domovoy.modules.common_schemas import UserShort
from domovoy.modules.issues.catalog import ORG_KINDS, STATUS_TITLES, category
from domovoy.modules.issues.models import Issue, IssueUpdate


class OrgOut(BaseModel):
    name: str
    kind: str
    kind_title: str
    phone: str | None = None


class IssueOut(BaseModel):
    id: int
    title: str
    description: str
    category: str
    category_title: str
    status: str
    status_title: str
    votes_count: int
    votes_needed: int
    voted_by_me: bool
    photos: list[str]
    author: UserShort
    responsible_org: OrgOut | None
    created_at: datetime
    sent_at: datetime | None
    deadline_at: datetime | None
    is_overdue: bool
    score: float | None = None


class TimelineItem(BaseModel):
    status: str
    status_title: str
    note: str
    created_at: datetime


class IssueDetail(IssueOut):
    legal_basis: str
    deadline_hours: int
    appeal_text: str | None
    # model - только текст в карточке; test_email:<адрес> - письмо на тестовый адрес (модельная интеграция)
    appeal_channel: str | None = None
    location_hint: str | None
    timeline: list[TimelineItem]


class TextIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


class StatusIn(BaseModel):
    status: Literal["in_progress", "resolved", "rejected"]
    note: str = Field(default="", max_length=1000)


class ClassificationOut(BaseModel):
    category: str
    category_title: str
    title: str
    org_kind: str
    org_name: str
    legal_basis: str
    deadline_hours: int
    confidence: float
    source: str


def is_overdue(issue: Issue) -> bool:
    return (
        issue.status in ("sent", "in_progress")
        and issue.deadline_at is not None
        and issue.deadline_at < datetime.now(UTC)
    )


def org_out(issue: Issue) -> OrgOut | None:
    org = issue.responsible_org
    if org is None:
        return None
    return OrgOut(name=org.name, kind=org.kind, kind_title=ORG_KINDS.get(org.kind, org.kind), phone=org.phone)


def issue_out(issue: Issue, voted_by_me: bool, score: float | None = None) -> IssueOut:
    return IssueOut(
        id=issue.id,
        title=issue.title,
        description=issue.description,
        category=issue.category,
        category_title=category(issue.category).title,
        status=issue.status,
        status_title=STATUS_TITLES.get(issue.status, issue.status),
        votes_count=issue.votes_count,
        votes_needed=issue.votes_needed,
        voted_by_me=voted_by_me,
        photos=[media_url(k) for k in issue.photos or []],
        author=UserShort.of(issue.author),
        responsible_org=org_out(issue),
        created_at=issue.created_at,
        sent_at=issue.sent_at,
        deadline_at=issue.deadline_at,
        is_overdue=is_overdue(issue),
        score=score,
    )


def issue_detail(issue: Issue, voted_by_me: bool, timeline: list[IssueUpdate]) -> IssueDetail:
    base = issue_out(issue, voted_by_me)
    return IssueDetail(
        **base.model_dump(),
        legal_basis=issue.legal_basis,
        deadline_hours=issue.deadline_hours,
        appeal_text=issue.appeal_text,
        appeal_channel=issue.appeal_channel,
        location_hint=issue.location_hint,
        timeline=[
            TimelineItem(
                status=t.status,
                status_title=STATUS_TITLES.get(t.status, t.status),
                note=t.note,
                created_at=t.created_at,
            )
            for t in timeline
        ],
    )
