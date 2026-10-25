from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from domovoy.api.deps import CtxDep, SessionDep, require_admin_or_mock
from domovoy.modules.misc_models import Shelter
from domovoy.modules.safety import routing, service
from domovoy.modules.safety.routing import RouteOut
from domovoy.modules.safety.service import AlertIn, AlertOut, ShelterOut, alert_out

router = APIRouter(tags=["Безопасность"])

Lat = Annotated[float | None, Query(ge=-90, le=90, description="Широта жителя; пусто = координаты дома")]
Lon = Annotated[float | None, Query(ge=-180, le=180, description="Долгота жителя; пусто = координаты дома")]


@router.get("/shelters", response_model=list[ShelterOut])
async def shelters(session: SessionDep, ctx: CtxDep, lat: Lat = None, lon: Lon = None) -> list[ShelterOut]:
    """Ближайшие укрытия: реестр региона, демо-точки и заглублённые объекты OpenStreetMap."""
    return await service.nearest_shelters(
        session, lat if lat is not None else ctx.house.lat, lon if lon is not None else ctx.house.lon
    )


@router.get("/shelters/{shelter_id}/route", response_model=RouteOut)
async def shelter_route(
    shelter_id: int, session: SessionDep, ctx: CtxDep, lat: Lat = None, lon: Lon = None
) -> RouteOut:
    """Пешеходный маршрут до укрытия (OSRM); если роутер недоступен - прямая линия и оценка времени по 5 км/ч."""
    shelter = await session.get(Shelter, shelter_id)
    if shelter is None:
        raise HTTPException(404, "Укрытие не найдено")
    return await routing.walking_route(
        lat if lat is not None else ctx.house.lat,
        lon if lon is not None else ctx.house.lon,
        shelter.lat,
        shelter.lon,
    )


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
