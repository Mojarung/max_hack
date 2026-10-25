"""Импорт реестра укрытий региона из CSV: `domovoy import-shelters файл.csv --region RU-ORL --source "Реестр ..."`.

Колонки: name,address,lat,lon,capacity,kind (разделитель запятая или точка с запятой, кодировка UTF-8,
BOM от Excel допустим). Строки без координат геокодируются через Nominatim не чаще раза в секунду.
Повторный импорт того же файла обновляет записи, а не дублирует их: ключ - источник, название и адрес.
"""

import asyncio
import csv
import io
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core.db import get_sessionmaker
from domovoy.modules.misc_models import Shelter
from domovoy.modules.safety.catalog import KIND_TITLES, registry_source

log = structlog.get_logger(__name__)

GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
GEOCODE_PAUSE_S = 1.0
USER_AGENT = "domovoy-kuzya/1.0 (shelter import)"
REGION_RE = re.compile(r"^RU-[A-Z]{2,3}$")
REQUIRED_COLUMNS = ("name", "address")
OPTIONAL_COLUMNS = ("lat", "lon", "capacity", "kind")


class ImportError_(ValueError):
    """Ошибка разбора CSV с номером строки, понятная из консоли."""


@dataclass(frozen=True)
class ShelterRow:
    name: str
    address: str
    lat: float | None
    lon: float | None
    capacity: int | None
    kind: str


@dataclass(frozen=True)
class ImportStats:
    created: int
    updated: int
    geocoded: int
    skipped: int


def _delimiter(header: str) -> str:
    return ";" if header.count(";") > header.count(",") else ","


def _float(value: str, line: int, column: str) -> float | None:
    raw = value.strip().replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise ImportError_(f"строка {line}: {column} = «{value}» не число") from None


def parse_csv(text: str) -> list[ShelterRow]:
    """Разбирает CSV реестра. Пустые lat/lon допустимы (будут геокодированы), kind по умолчанию shelter."""
    text = text.lstrip("﻿")
    first_line = text.split("\n", 1)[0]
    reader = csv.DictReader(io.StringIO(text), delimiter=_delimiter(first_line))
    columns = [c.strip().lower() for c in reader.fieldnames or []]
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise ImportError_(f"в заголовке нет колонок: {', '.join(missing)}. Нужны: name,address,lat,lon,capacity,kind")
    rows: list[ShelterRow] = []
    for line, raw in enumerate(reader, start=2):
        cells = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        name = cells.get("name", "")
        if not name:
            continue
        kind = cells.get("kind", "") or "shelter"
        if kind not in KIND_TITLES:
            raise ImportError_(f"строка {line}: kind = «{kind}», допустимо: {', '.join(KIND_TITLES)}")
        lat = _float(cells.get("lat", ""), line, "lat")
        lon = _float(cells.get("lon", ""), line, "lon")
        if (lat is None) != (lon is None):
            raise ImportError_(f"строка {line}: нужны обе координаты или ни одной")
        if lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ImportError_(f"строка {line}: координаты вне диапазона")
        capacity_raw = cells.get("capacity", "")
        capacity = int(capacity_raw) if capacity_raw.isdigit() else None
        address = cells.get("address", "")
        rows.append(ShelterRow(name=name, address=address, lat=lat, lon=lon, capacity=capacity, kind=kind))
    return rows


async def geocode(http: httpx.AsyncClient, address: str) -> tuple[float, float] | None:
    try:
        resp = await http.get(
            GEOCODER_URL,
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "ru", "accept-language": "ru"},
        )
        resp.raise_for_status()
        found = resp.json()
    except (httpx.HTTPError, ValueError):
        log.warning("shelters.geocode_failed", address=address, exc_info=True)
        return None
    if not found:
        return None
    return float(found[0]["lat"]), float(found[0]["lon"])


async def _fill_coordinates(rows: list[ShelterRow], pause_s: float) -> tuple[list[ShelterRow], int, int]:
    """Геокодирует строки без координат, не чаще одного запроса за pause_s. Возвращает (строки, найдено, пропущено)."""
    if all(r.lat is not None for r in rows):
        return rows, 0, 0
    done: list[ShelterRow] = []
    geocoded = skipped = 0
    last_call = 0.0
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": USER_AGENT}) as http:
        for row in rows:
            if row.lat is not None:
                done.append(row)
                continue
            wait = pause_s - (time.monotonic() - last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            last_call = time.monotonic()
            point = await geocode(http, row.address)
            if point is None:
                log.warning("shelters.not_geocoded", name=row.name, address=row.address)
                skipped += 1
                continue
            geocoded += 1
            done.append(ShelterRow(row.name, row.address, point[0], point[1], row.capacity, row.kind))
    return done, geocoded, skipped


async def _upsert(session: AsyncSession, rows: list[ShelterRow], region: str, source: str) -> tuple[int, int]:
    existing = {
        (s.name, s.address): s
        for s in await session.scalars(select(Shelter).where(Shelter.source == source, Shelter.region == region))
    }
    now = datetime.now(UTC)
    created = updated = 0
    for row in rows:
        if row.lat is None or row.lon is None:
            continue
        current = existing.get((row.name, row.address))
        if current is None:
            session.add(
                Shelter(
                    name=row.name,
                    address=row.address,
                    lat=row.lat,
                    lon=row.lon,
                    capacity=row.capacity,
                    kind=row.kind,
                    source=source,
                    region=region,
                    official=True,
                    fetched_at=now,
                )
            )
            created += 1
            continue
        current.lat, current.lon = row.lat, row.lon
        current.capacity, current.kind, current.fetched_at = row.capacity, row.kind, now
        updated += 1
    await session.commit()
    return created, updated


async def import_shelters(
    path: Path, region: str, source_name: str, *, pause_s: float = GEOCODE_PAUSE_S
) -> ImportStats:
    if not REGION_RE.match(region):
        raise ImportError_(f"регион «{region}» не похож на код ISO 3166-2, пример: RU-ORL")
    if not source_name.strip():
        raise ImportError_('укажите источник: --source "Реестр укрытий ... области"')
    rows = parse_csv(await asyncio.to_thread(path.read_text, encoding="utf-8-sig"))
    rows, geocoded, skipped = await _fill_coordinates(rows, pause_s)
    async with get_sessionmaker()() as session:
        created, updated = await _upsert(session, rows, region, registry_source(source_name))
    return ImportStats(created=created, updated=updated, geocoded=geocoded, skipped=skipped)
