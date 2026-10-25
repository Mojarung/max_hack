"""Пешеходный маршрут до укрытия: публичный OSRM, при любой ошибке - прямая линия и оценка по 5 км/ч."""

import time
from typing import Any, Literal

import httpx
import structlog
from pydantic import BaseModel

from domovoy.core.config import get_settings
from domovoy.modules.safety.geo import haversine_m

log = structlog.get_logger(__name__)

USER_AGENT = "domovoy-kuzya/1.0 (route)"
WALK_SPEED_MPS = 5000 / 3600
ROUTE_CACHE_TTL_S = 10 * 60
ROUTE_CACHE_MAX = 500

Point = tuple[float, float]


class RouteOut(BaseModel):
    distance_m: int
    duration_s: int
    # [[lat, lon], ...] от жителя до укрытия
    points: list[Point]
    provider: Literal["osrm", "straight"]


_cache: dict[tuple[float, float, float, float], tuple[float, RouteOut]] = {}


def straight_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> RouteOut:
    distance = haversine_m(from_lat, from_lon, to_lat, to_lon)
    return RouteOut(
        distance_m=distance,
        duration_s=round(distance / WALK_SPEED_MPS),
        points=[(round(from_lat, 6), round(from_lon, 6)), (round(to_lat, 6), round(to_lon, 6))],
        provider="straight",
    )


def parse_osrm(data: dict[str, Any]) -> RouteOut | None:
    """Ответ OSRM /route/v1 с geometries=geojson → маршрут; None, если маршрута нет или ответ странный."""
    routes = data.get("routes") or []
    if data.get("code") != "Ok" or not routes:
        return None
    route = routes[0]
    coords = (route.get("geometry") or {}).get("coordinates") or []
    points = [(round(float(lat), 6), round(float(lon), 6)) for lon, lat in coords]
    if len(points) < 2:
        return None
    return RouteOut(
        distance_m=round(float(route.get("distance", 0))),
        duration_s=round(float(route.get("duration", 0))),
        points=points,
        provider="osrm",
    )


async def _osrm_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> RouteOut | None:
    settings = get_settings()
    url = f"{settings.osrm_url.rstrip('/')}/route/v1/foot/{from_lon:.6f},{from_lat:.6f};{to_lon:.6f},{to_lat:.6f}"
    try:
        async with httpx.AsyncClient(timeout=settings.osrm_timeout_seconds, headers={"User-Agent": USER_AGENT}) as http:
            resp = await http.get(url, params={"overview": "full", "geometries": "geojson"})
            resp.raise_for_status()
            return parse_osrm(resp.json())
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        log.warning("osrm.failed", error=f"{type(exc).__name__}: {exc}")
        return None


def _cache_get(key: tuple[float, float, float, float]) -> RouteOut | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    stamp, route = hit
    if time.monotonic() - stamp > ROUTE_CACHE_TTL_S:
        _cache.pop(key, None)
        return None
    return route


def _cache_put(key: tuple[float, float, float, float], route: RouteOut) -> None:
    now = time.monotonic()
    if len(_cache) >= ROUTE_CACHE_MAX:
        for k in [k for k, (stamp, _) in _cache.items() if now - stamp > ROUTE_CACHE_TTL_S]:
            _cache.pop(k, None)
    if len(_cache) >= ROUTE_CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (now, route)


async def walking_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> RouteOut:
    """Маршрут пешком с кэшем на 10 минут. Точку старта округляем до ~10 м, чтобы кэш срабатывал."""
    key = (round(from_lat, 4), round(from_lon, 4), round(to_lat, 5), round(to_lon, 5))
    cached = _cache_get(key)
    if cached is not None:
        return cached
    route = await _osrm_route(from_lat, from_lon, to_lat, to_lon) or straight_route(from_lat, from_lon, to_lat, to_lon)
    if route.provider == "osrm":
        _cache_put(key, route)
    return route
