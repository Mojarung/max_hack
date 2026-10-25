"""Интеграционные тесты: настоящий Postgres с pgvector в отдельной базе domovoy_test.

База пересоздаётся один раз на сессию, схема и демо-сид те же, что у стенда. Каждый тест, который
что-то меняет, заводит свой дом с жителями (фикстура home), поэтому тесты не мешают друг другу
и не зависят от порядка. Без Postgres все тесты этой папки пропускаются.
"""

from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.api.app import create_app
from domovoy.core.config import get_settings
from domovoy.core.db import get_engine, get_sessionmaker, init_db
from domovoy.seed import seed_demo
from integration.helpers import Home, make_home

CONNECT_TIMEOUT_S = 3


async def _admin_connection() -> asyncpg.Connection:
    url = make_url(get_settings().database_url)
    return await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host or "localhost",
        port=url.port or 5432,
        database="postgres",
        timeout=CONNECT_TIMEOUT_S,
    )


@pytest_asyncio.fixture(scope="session")
async def database() -> AsyncIterator[str]:
    """Пустая база domovoy_test со схемой и демо-сидом. Нет Postgres - тесты пропускаются."""
    name = make_url(get_settings().database_url).database or ""
    assert name.endswith("_test"), "интеграционные тесты работают только с базой *_test"
    try:
        admin = await _admin_connection()
    except (OSError, TimeoutError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres недоступен ({type(exc).__name__}): интеграционные тесты пропущены")
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    await init_db()
    await seed_demo()
    yield name
    await get_engine().dispose()
    admin = await _admin_connection()
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.fixture(autouse=True)
def _needs_database(database: str) -> None:
    """Каждый тест папки integration ждёт готовую базу (или пропускается вместе с ней)."""


@pytest_asyncio.fixture
async def home() -> Home:
    return await make_home()


@pytest.fixture(scope="session")
def app() -> FastAPI:
    return create_app()


@pytest_asyncio.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as s:
        yield s
