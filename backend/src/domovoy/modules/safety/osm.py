"""Заглублённые объекты из OpenStreetMap через Overpass: запасной источник укрытий.

Официальных убежищ в OSM почти нет (по всей России около 25 объектов), зато есть то, что МЧС называет
укрытием простейшего типа: подземные паркинги, подземные переходы, входы в метро, бункеры.
Зеркала Overpass иногда отвечают 504, поэтому запрос идёт по списку адресов с таймаутом, а при
неудаче возвращается None, и сервис живёт на том, что уже лежит в базе.
"""

import math
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from domovoy.core.config import get_settings
from domovoy.modules.safety.catalog import KIND_TITLES

log = structlog.get_logger(__name__)

USER_AGENT = "domovoy-kuzya/1.0 (shelters)"
# Один подземный переход в OSM часто разбит на несколько коротких отрезков: соседние точки склеиваем
UNDERPASS_MERGE_M = 60
# Тип объекта зашит в младший разряд: id * 10 + код. Ид узлов, линий и отношений в OSM пересекаются.
_TYPE_CODES = {"node": 1, "way": 2, "relation": 3}
_TYPE_BY_CODE = {code: name for name, code in _TYPE_CODES.items()}

# Глобальный bbox вместо around: с around Overpass сначала перебирает частый тег (amenity=parking) по всему
# миру и отвечает за 30-40 с, с bbox укладывается в 15 с (замер 20.10.2026 на зеркале mail.ru).
OVERPASS_QUERY = """[out:json][timeout:{timeout}][bbox:{south},{west},{north},{east}];
(
  nwr["amenity"="parking"]["parking"="underground"];
  way["highway"~"^(footway|steps)$"]["tunnel"="yes"];
  nwr["railway"="subway_entrance"];
  nwr["building"="bunker"];
  nwr["shelter_type"="bomb_shelter"];
  nwr["bunker_type"="bomb_shelter"];
);
out center tags;
"""
METERS_PER_DEG = 111_320


def bbox_around(lat: float, lon: float, radius_m: int) -> tuple[float, float, float, float]:
    """(юг, запад, север, восток): квадрат со стороной 2 × radius_m вокруг точки."""
    dlat = radius_m / METERS_PER_DEG
    dlon = radius_m / (METERS_PER_DEG * max(math.cos(math.radians(lat)), 0.1))
    return (round(lat - dlat, 5), round(lon - dlon, 5), round(lat + dlat, 5), round(lon + dlon, 5))


@dataclass(frozen=True)
class OsmShelter:
    osm_id: int
    kind: str
    name: str
    address: str
    lat: float
    lon: float
    capacity: int | None

    @property
    def url(self) -> str:
        return osm_object_url(self.osm_id)


def encode_osm_id(osm_type: str, raw_id: int) -> int:
    return raw_id * 10 + _TYPE_CODES[osm_type]


def osm_object_url(osm_id: int) -> str:
    osm_type = _TYPE_BY_CODE.get(osm_id % 10, "node")
    return f"https://www.openstreetmap.org/{osm_type}/{osm_id // 10}"


def kind_of(tags: dict[str, str]) -> str | None:
    """Вид укрытия по тегам OSM; None, если объект нам не подходит."""
    if tags.get("shelter_type") == "bomb_shelter" or tags.get("bunker_type") == "bomb_shelter":
        return "shelter"
    if tags.get("building") == "bunker":
        return "bunker"
    if tags.get("railway") == "subway_entrance":
        return "metro"
    if tags.get("amenity") == "parking" and tags.get("parking") == "underground":
        return "parking"
    if tags.get("highway") in ("footway", "steps") and tags.get("tunnel") == "yes":
        return "underpass"
    return None


def format_address(tags: dict[str, str]) -> str:
    street = tags.get("addr:street", "").strip()
    number = tags.get("addr:housenumber", "").strip()
    if not street:
        return tags.get("addr:full", "").strip()
    return f"{street}, {number}" if number else street


def _capacity(tags: dict[str, str]) -> int | None:
    raw = tags.get("capacity", "").strip()
    return int(raw) if raw.isdigit() else None


def parse_element(element: dict[str, Any]) -> OsmShelter | None:
    """Элемент ответа Overpass (`out center tags`) → укрытие или None, если нет координат или вида."""
    osm_type = element.get("type")
    raw_id = element.get("id")
    if osm_type not in _TYPE_CODES or not isinstance(raw_id, int):
        return None
    tags: dict[str, str] = element.get("tags") or {}
    kind = kind_of(tags)
    if kind is None:
        return None
    point = element if osm_type == "node" else element.get("center") or {}
    lat, lon = point.get("lat"), point.get("lon")
    if not isinstance(lat, int | float) or not isinstance(lon, int | float):
        return None
    return OsmShelter(
        osm_id=encode_osm_id(osm_type, raw_id),
        kind=kind,
        name=tags.get("name", "").strip() or KIND_TITLES[kind],
        address=format_address(tags),
        lat=float(lat),
        lon=float(lon),
        capacity=_capacity(tags),
    )


def _distance_m(a: OsmShelter, b: OsmShelter) -> float:
    # Для склейки хватает плоского приближения: расстояния до 100 м
    dlat = (a.lat - b.lat) * METERS_PER_DEG
    dlon = (a.lon - b.lon) * METERS_PER_DEG * math.cos(math.radians(a.lat))
    return math.hypot(dlat, dlon)


def parse_elements(elements: list[dict[str, Any]]) -> list[OsmShelter]:
    """Разбирает ответ Overpass и склеивает отрезки одного подземного перехода в одну точку."""
    items = [s for s in (parse_element(e) for e in elements) if s is not None]
    kept: list[OsmShelter] = []
    for item in sorted(items, key=lambda s: s.osm_id):
        if item.kind == "underpass" and any(
            k.kind == "underpass" and _distance_m(k, item) < UNDERPASS_MERGE_M for k in kept
        ):
            continue
        kept.append(item)
    return kept


async def fetch_shelters(lat: float, lon: float, radius_m: int) -> list[OsmShelter] | None:
    """Укрытия простейшего типа вокруг точки. None, если ни одно зеркало Overpass не ответило.

    overpass_timeout_seconds - общий бюджет на все зеркала: быстрый 504 первого оставляет время второму,
    а медленный первый не удваивает ожидание жителя.
    """
    settings = get_settings()
    deadline = time.monotonic() + settings.overpass_timeout_seconds
    south, west, north, east = bbox_around(lat, lon, radius_m)
    for url in settings.overpass_urls:
        remaining = deadline - time.monotonic()
        if remaining < 1:
            log.warning("overpass.budget_exhausted", url=url)
            break
        query = OVERPASS_QUERY.format(timeout=int(remaining), south=south, west=west, north=north, east=east)
        try:
            async with httpx.AsyncClient(timeout=remaining, headers={"User-Agent": USER_AGENT}) as http:
                resp = await http.post(url, data={"data": query})
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
        except (httpx.HTTPError, ValueError) as exc:
            # у таймаута httpx пустой текст, поэтому пишем и класс ошибки
            log.warning("overpass.failed", url=url, error=f"{type(exc).__name__}: {exc}")
            continue
        items = parse_elements(elements)
        log.info("overpass.fetched", url=url, raw=len(elements), kept=len(items))
        return items
    return None
