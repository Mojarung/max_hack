"""Укрытия и оповещение о беспилотной опасности.

Укрытия берутся из базы (реестры регионов, демо-точки, уже найденные объекты OSM). Если рядом с точкой
их мало, сервис один раз в неделю на ячейку карты спрашивает Overpass про заглублённые объекты
(подземные паркинги, переходы, метро, бункеры) и сохраняет их. Когда в базе уже что-то есть, ответ
уходит сразу, а OSM дотягивается фоновой задачей; когда нет ничего, ждём Overpass, но не дольше
бюджета. Любая ошибка сети - запись в лог, пауза 10 минут перед новой попыткой и ответ из того, что есть.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.core.db import get_sessionmaker
from domovoy.modules.misc_models import Alert, Shelter, ShelterFetch
from domovoy.modules.safety import osm
from domovoy.modules.safety.catalog import kind_title, source_note, source_title
from domovoy.modules.safety.geo import cell_key, haversine_m
from domovoy.modules.users.models import House

log = structlog.get_logger(__name__)

ALERT_TITLES = {"drone": "Беспилотная опасность", "air": "Воздушная тревога", "other": "Экстренное оповещение"}
DEFAULT_DRONE_MESSAGE = (
    "Внимание! Беспилотная опасность. Отойдите от окон, не снимайте БПЛА на телефон, "
    "спуститесь в укрытие или в помещение без окон. Следите за официальными сообщениями."
)
NO_SHELTERS_ADVICE = "Рядом нет укрытий в реестре и на карте. Спуститесь в подвал или встаньте в помещении без окон."

# Предварительный отбор из базы: прямоугольник ±0,05° (около 5 км по широте), потом точное расстояние
BBOX_DEG = 0.05
# Если в этом радиусе меньше limit точек, дотягиваем из OSM
NEAR_RADIUS_M = 1500
OSM_RADIUS_M = 2500
FETCH_TTL = timedelta(days=7)
# После неудачи Overpass ячейку не трогаем 10 минут: иначе каждый запрос ждал бы таймаут заново
RETRY_AFTER_S = 10 * 60

_failed_at: dict[str, float] = {}
_inflight: set[str] = set()
_background: set[asyncio.Task[None]] = set()


class ShelterOut(BaseModel):
    id: int
    name: str
    address: str
    lat: float
    lon: float
    capacity: int | None
    kind: str
    kind_title: str
    official: bool
    source: str
    source_title: str
    distance_m: int
    yandex_url: str
    osm_url: str


class AlertIn(BaseModel):
    kind: Literal["drone", "air", "other"] = "drone"
    message: str = Field(default="", max_length=1000)


class AlertOut(BaseModel):
    id: int
    kind: str
    kind_title: str
    message: str
    active: bool
    created_at: datetime
    ended_at: datetime | None


def yandex_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> str:
    """Пешеходный маршрут в Яндекс Картах по координатам."""
    return f"https://yandex.ru/maps/?rtext={from_lat:.6f},{from_lon:.6f}~{to_lat:.6f},{to_lon:.6f}&rtt=pd"


def osm_link(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}"


def shelter_out(s: Shelter, lat: float, lon: float) -> ShelterOut:
    return ShelterOut(
        id=s.id,
        name=s.name,
        address=s.address,
        lat=s.lat,
        lon=s.lon,
        capacity=s.capacity,
        kind=s.kind,
        kind_title=kind_title(s.kind),
        official=bool(s.official),
        source=s.source,
        source_title=source_title(s.source),
        distance_m=haversine_m(lat, lon, s.lat, s.lon),
        yandex_url=yandex_route(lat, lon, s.lat, s.lon),
        osm_url=osm.osm_object_url(s.osm_id) if s.osm_id else osm_link(s.lat, s.lon),
    )


def shelter_note(s: ShelterOut) -> str:
    """Пометка источника для текста в чате: «из реестра», «по данным OpenStreetMap»."""
    return source_note(s.source, s.official)


async def _shelters_around(session: AsyncSession, lat: float, lon: float) -> list[Shelter]:
    return list(
        await session.scalars(
            select(Shelter).where(
                Shelter.lat.between(lat - BBOX_DEG, lat + BBOX_DEG),
                Shelter.lon.between(lon - BBOX_DEG, lon + BBOX_DEG),
            )
        )
    )


async def _cell_is_fresh(session: AsyncSession, cell: str) -> bool:
    row = await session.get(ShelterFetch, cell)
    return row is not None and datetime.now(UTC) - row.fetched_at < FETCH_TTL


async def _store_osm(session: AsyncSession, items: list[osm.OsmShelter], cell: str) -> None:
    """Upsert по osm_id и отметка ячейки. Гонка двух запросов на одну ячейку решается уникальным индексом."""
    now = datetime.now(UTC)
    existing = {
        s.osm_id: s for s in await session.scalars(select(Shelter).where(Shelter.osm_id.in_([i.osm_id for i in items])))
    }
    for item in items:
        row = existing.get(item.osm_id)
        if row is None:
            session.add(
                Shelter(
                    name=item.name,
                    address=item.address,
                    lat=item.lat,
                    lon=item.lon,
                    capacity=item.capacity,
                    kind=item.kind,
                    source="osm",
                    osm_id=item.osm_id,
                    official=False,
                    fetched_at=now,
                )
            )
            continue
        row.name, row.address, row.lat, row.lon = item.name, item.address, item.lat, item.lon
        row.capacity, row.kind, row.fetched_at = item.capacity, item.kind, now
    mark = await session.get(ShelterFetch, cell)
    if mark is None:
        session.add(ShelterFetch(cell=cell, fetched_at=now))
    else:
        mark.fetched_at = now
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        log.info("shelters.osm_race", cell=cell)


def recently_failed(cell: str, now: float | None = None) -> bool:
    stamp = _failed_at.get(cell)
    return stamp is not None and (time.monotonic() if now is None else now) - stamp < RETRY_AFTER_S


async def _fetch_cell(lat: float, lon: float, cell: str) -> list[osm.OsmShelter] | None:
    """Overpass для ячейки: один запрос за раз, неудача запоминается на RETRY_AFTER_S."""
    if cell in _inflight:
        return None
    _inflight.add(cell)
    try:
        fetched = await osm.fetch_shelters(lat, lon, OSM_RADIUS_M)
    finally:
        _inflight.discard(cell)
    if fetched is None:
        _failed_at[cell] = time.monotonic()
    else:
        _failed_at.pop(cell, None)
    return fetched


async def _refresh_in_background(lat: float, lon: float, cell: str) -> None:
    try:
        fetched = await _fetch_cell(lat, lon, cell)
        if fetched is None:
            return
        async with get_sessionmaker()() as session:
            await _store_osm(session, fetched, cell)
    except Exception:
        # фоновая задача: ошибка должна попасть в лог, а не потеряться в «Task exception was never retrieved»
        log.warning("shelters.refresh_failed", cell=cell, exc_info=True)


def _schedule_refresh(lat: float, lon: float, cell: str) -> None:
    if cell in _inflight:
        return
    task = asyncio.get_running_loop().create_task(_refresh_in_background(lat, lon, cell))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def nearest_shelters(session: AsyncSession, lat: float, lon: float, limit: int = 20) -> list[ShelterOut]:
    """Ближайшие укрытия к точке, по расстоянию. При нехватке точек рядом дотягивает объекты OSM."""
    shelters = await _shelters_around(session, lat, lon)
    near = sum(1 for s in shelters if haversine_m(lat, lon, s.lat, s.lon) <= NEAR_RADIUS_M)
    cell = cell_key(lat, lon)
    if near < limit and not recently_failed(cell) and not await _cell_is_fresh(session, cell):
        if near == 0:
            # показать нечего: ждём Overpass, но не дольше его бюджета времени
            fetched = await _fetch_cell(lat, lon, cell)
            if fetched is not None:
                await _store_osm(session, fetched, cell)
                shelters = await _shelters_around(session, lat, lon)
        else:
            # что-то уже есть: отвечаем сразу, объекты OSM появятся к следующему запросу
            _schedule_refresh(lat, lon, cell)
    items = [shelter_out(s, lat, lon) for s in shelters]
    return sorted(items, key=lambda x: x.distance_m)[:limit]


def alert_out(a: Alert) -> AlertOut:
    return AlertOut(
        id=a.id,
        kind=a.kind,
        kind_title=ALERT_TITLES.get(a.kind, a.kind),
        message=a.message,
        active=a.active,
        created_at=a.created_at,
        ended_at=a.ended_at,
    )


async def active_alert(session: AsyncSession, house_id: int) -> Alert | None:
    return await session.scalar(
        select(Alert)
        .where(Alert.active.is_(True), (Alert.house_id == house_id) | Alert.house_id.is_(None))
        .order_by(Alert.id.desc())
        .limit(1)
    )


async def start_alert(session: AsyncSession, house: House, data: AlertIn) -> Alert:
    alert = Alert(house_id=house.id, kind=data.kind, message=data.message.strip() or DEFAULT_DRONE_MESSAGE)
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    await bus.emit(house.id, "alert.started", alert_out(alert).model_dump(mode="json"))
    await bus.emit(house.id, "pulse.changed", {})
    if house.max_chat_id:
        shelters = await nearest_shelters(session, house.lat, house.lon, limit=1)
        text = f"🚨 **{ALERT_TITLES[alert.kind]}**\n{alert.message}"
        buttons = [[{"type": "open_app", "text": "Карта укрытий", "payload": "alert"}]]
        if shelters:
            s = shelters[0]
            where = f", {s.address}" if s.address else ""
            text += f"\n\nБлижайшее укрытие: {s.name} ({s.kind_title.lower()}){where}, ~{s.distance_m} м, "
            text += f"{shelter_note(s)}."
            buttons.insert(0, [{"type": "link", "text": "Маршрут в Яндекс Картах", "url": s.yandex_url}])
        else:
            text += f"\n\n{NO_SHELTERS_ADVICE}"
        await bus.bot_send(chat_id=house.max_chat_id, text=text, buttons=buttons)
    return alert


async def end_alert(session: AsyncSession, house: House, alert_id: int) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None or alert.house_id not in (house.id, None):
        raise HTTPException(404, "Оповещение не найдено")
    alert.active = False
    alert.ended_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(alert)
    await bus.emit(house.id, "alert.ended", alert_out(alert).model_dump(mode="json"))
    await bus.emit(house.id, "pulse.changed", {})
    if house.max_chat_id:
        await bus.bot_send(chat_id=house.max_chat_id, text="✅ Отбой опасности. Кузя рядом, берегите себя.")
    return alert
