"""Укрытия и оповещение о беспилотной опасности."""

import math
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.modules.misc_models import Alert, Shelter
from domovoy.modules.users.models import House

ALERT_TITLES = {"drone": "Беспилотная опасность", "air": "Воздушная тревога", "other": "Экстренное оповещение"}
DEFAULT_DRONE_MESSAGE = (
    "Внимание! Беспилотная опасность. Отойдите от окон, не снимайте БПЛА на телефон, "
    "спуститесь в укрытие или в помещение без окон. Следите за официальными сообщениями."
)


class ShelterOut(BaseModel):
    id: int
    name: str
    address: str
    lat: float
    lon: float
    capacity: int | None
    kind: str
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


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)))


def yandex_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> str:
    """Пешеходный маршрут в Яндекс Картах по координатам."""
    return f"https://yandex.ru/maps/?rtext={from_lat:.6f},{from_lon:.6f}~{to_lat:.6f},{to_lon:.6f}&rtt=pd"


def osm_link(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}"


async def nearest_shelters(session: AsyncSession, lat: float, lon: float, limit: int = 20) -> list[ShelterOut]:
    shelters = list(await session.scalars(select(Shelter)))
    items = [
        ShelterOut(
            id=s.id,
            name=s.name,
            address=s.address,
            lat=s.lat,
            lon=s.lon,
            capacity=s.capacity,
            kind=s.kind,
            distance_m=haversine_m(lat, lon, s.lat, s.lon),
            yandex_url=yandex_route(lat, lon, s.lat, s.lon),
            osm_url=osm_link(s.lat, s.lon),
        )
        for s in shelters
    ]
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
            text += f"\n\nБлижайшее укрытие: {s.name}, {s.address} (~{s.distance_m} м)."
            buttons.insert(0, [{"type": "link", "text": "Маршрут в Яндекс Картах", "url": s.yandex_url}])
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
