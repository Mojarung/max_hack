"""Геометрия на сфере и ключ ячейки кэша для укрытий."""

import math

EARTH_RADIUS_M = 6_371_000
# Ячейка кэша запросов к OSM: координаты, округлённые вниз до 0,02° (около 2 км по широте)
CELL_DEG = 0.02


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * EARTH_RADIUS_M * math.asin(math.sqrt(a)))


def cell_key(lat: float, lon: float) -> str:
    """«54.38:48.60» для любой точки внутри ячейки 0,02° × 0,02°."""
    return f"{math.floor(lat / CELL_DEG) * CELL_DEG:.2f}:{math.floor(lon / CELL_DEG) * CELL_DEG:.2f}"
