"""Источники официальных оповещений для администратора дома: что опрашиваем и когда последний раз получилось."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from domovoy.api.deps import CtxDep, SessionDep, require_admin_or_mock
from domovoy.core.config import get_settings
from domovoy.modules.safety.feed_models import AlertSource
from domovoy.modules.safety.regions import region_name

router = APIRouter(tags=["Безопасность"])


class AlertSourceOut(BaseModel):
    id: int
    type: str
    ref: str
    title: str
    enabled: bool
    last_checked_at: datetime | None
    last_post_id: str | None
    last_error: str | None


class AlertSourcesOut(BaseModel):
    # регион дома по ISO 3166-2 и его название; null - адрес дома ещё не выбран
    region: str | None
    region_name: str | None
    feeds_enabled: bool
    sources: list[AlertSourceOut]


@router.get("/alerts/sources", response_model=AlertSourcesOut)
async def sources(session: SessionDep, ctx: CtxDep) -> AlertSourcesOut:
    """Источники оповещений региона дома (администратор). Без региона список пуст."""
    require_admin_or_mock(ctx)
    region = ctx.house.region
    rows: list[AlertSource] = []
    if region:
        rows = list(
            await session.scalars(select(AlertSource).where(AlertSource.region == region).order_by(AlertSource.id))
        )
    return AlertSourcesOut(
        region=region,
        region_name=region_name(region),
        feeds_enabled=get_settings().alert_feeds_enabled,
        sources=[
            AlertSourceOut(
                id=s.id,
                type=s.type,
                ref=s.ref,
                title=s.title,
                enabled=s.enabled,
                last_checked_at=s.last_checked_at,
                last_post_id=s.last_post_id,
                last_error=s.last_error,
            )
            for s in rows
        ],
    )
