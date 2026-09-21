from fastapi import APIRouter

from domovoy.api.deps import CtxDep, SessionDep, require_admin_or_mock
from domovoy.modules.safety import service
from domovoy.modules.safety.service import AlertIn, AlertOut, ShelterOut, alert_out

router = APIRouter(tags=["Безопасность"])


@router.get("/shelters", response_model=list[ShelterOut])
async def shelters(
    session: SessionDep, ctx: CtxDep, lat: float | None = None, lon: float | None = None
) -> list[ShelterOut]:
    return await service.nearest_shelters(session, lat or ctx.house.lat, lon or ctx.house.lon)


@router.get("/alerts/active", response_model=AlertOut | None)
async def active(session: SessionDep, ctx: CtxDep) -> AlertOut | None:
    alert = await service.active_alert(session, ctx.house.id)
    return alert_out(alert) if alert else None


@router.post("/alerts", response_model=AlertOut, status_code=201)
async def start(body: AlertIn, session: SessionDep, ctx: CtxDep) -> AlertOut:
    require_admin_or_mock(ctx)
    return alert_out(await service.start_alert(session, ctx.house, body))


@router.post("/alerts/{alert_id}/end", response_model=AlertOut)
async def end(alert_id: int, session: SessionDep, ctx: CtxDep) -> AlertOut:
    require_admin_or_mock(ctx)
    return alert_out(await service.end_alert(session, ctx.house, alert_id))
