"""MCP-сервер «Жилищный навигатор» (FastMCP, транспорт streamable HTTP).

Даёт агенту Кузи и любым внешним MCP-клиентам данные о доме: паспорт, тарифы,
план капремонта, открытые заявки и поиск. Паспорт, тарифы и капремонт здесь МОДЕЛЬНЫЕ
(подготовленные для демо): в пилоте источник заменяется на ГИС ЖКХ и региональный
фонд капремонта без изменения интерфейса инструментов.
"""

from typing import Any

from fastmcp import FastMCP
from sqlalchemy import select

from domovoy.core.db import get_sessionmaker
from domovoy.modules.issues.catalog import OPEN_STATUSES, STATUS_TITLES
from domovoy.modules.issues.models import Issue
from domovoy.modules.search.hybrid import hybrid_search
from domovoy.modules.users.models import House

mcp = FastMCP(
    name="gis-zhkh-navigator",
    instructions="Справочные данные о многоквартирном доме: паспорт, тарифы, капремонт, заявки жителей.",
)

DATA_NOTE = "Модельные данные для демонстрации MVP, не выгрузка ГИС ЖКХ."

PASSPORT: dict[str, Any] = {
    "year_built": 1987,
    "floors": 9,
    "entrances": 4,
    "apartments": 144,
    "wall_material": "панель",
    "management": "управляющая организация по договору управления",
    "energy_class": "C",
}
TARIFFS_2026: list[dict[str, Any]] = [
    {"service": "Холодная вода", "unit": "м³", "price_rub": 38.9},
    {"service": "Горячая вода", "unit": "м³", "price_rub": 231.4},
    {"service": "Водоотведение", "unit": "м³", "price_rub": 33.6},
    {"service": "Отопление", "unit": "Гкал", "price_rub": 2615.0},
    {"service": "Электроэнергия (день)", "unit": "кВт·ч", "price_rub": 6.1},
    {"service": "Содержание жилого помещения", "unit": "м²", "price_rub": 29.8},
    {"service": "Взнос на капремонт", "unit": "м²", "price_rub": 14.6},
]
CAPITAL_REPAIR: list[dict[str, Any]] = [
    {"work": "Ремонт крыши", "planned_years": "2027-2029", "status": "запланировано"},
    {"work": "Замена лифтового оборудования", "planned_years": "2030-2032", "status": "запланировано"},
    {"work": "Ремонт фасада", "planned_years": "2021-2023", "status": "выполнено"},
]


async def _house(house_id: int | None) -> House | None:
    async with get_sessionmaker()() as session:
        if house_id:
            return await session.get(House, house_id)
        return await session.scalar(select(House).order_by(House.id).limit(1))


@mcp.tool
async def house_passport(house_id: int | None = None) -> dict[str, Any]:
    """Паспорт дома: год постройки, этажность, подъезды, материал стен, управляющая организация."""
    house = await _house(house_id)
    return {
        "address": house.address if house else None,
        "title": house.title if house else None,
        "uk": house.uk_org.name if house and house.uk_org else None,
        **PASSPORT,
        "source": DATA_NOTE,
    }


@mcp.tool
async def utility_tariffs() -> dict[str, Any]:
    """Тарифы на коммунальные услуги и взнос на капремонт (Казань, 2-е полугодие 2026)."""
    return {"region": "Республика Татарстан, г. Казань", "tariffs": TARIFFS_2026, "source": DATA_NOTE}


@mcp.tool
async def capital_repair_plan() -> dict[str, Any]:
    """Региональная программа капремонта для дома: виды работ, плановые годы, статус."""
    return {"works": CAPITAL_REPAIR, "source": DATA_NOTE}


@mcp.tool
async def open_issues(house_id: int | None = None) -> list[dict[str, Any]]:
    """Открытые заявки жителей дома со статусом и числом голосов."""
    house = await _house(house_id)
    if house is None:
        return []
    async with get_sessionmaker()() as session:
        rows = await session.scalars(
            select(Issue).where(Issue.house_id == house.id, Issue.status.in_(OPEN_STATUSES)).order_by(Issue.id.desc())
        )
        return [
            {
                "id": i.id,
                "title": i.title,
                "status": STATUS_TITLES[i.status],
                "votes": f"{i.votes_count}/{i.votes_needed}",
            }
            for i in rows
        ]


@mcp.tool
async def search_issues(query: str, house_id: int | None = None) -> list[dict[str, Any]]:
    """Гибридный поиск (вектор + полнотекст) по заявкам жителей дома."""
    house = await _house(house_id)
    if house is None:
        return []
    async with get_sessionmaker()() as session:
        found = await hybrid_search(session, Issue, query, where=[Issue.house_id == house.id], limit=5)
        return [{"id": i.id, "title": i.title, "status": STATUS_TITLES[i.status], "score": s} for i, s in found]


def run(host: str = "0.0.0.0", port: int = 8765) -> None:  # noqa: S104  сервер внутри docker-сети
    mcp.run(transport="http", host=host, port=port, show_banner=False)
