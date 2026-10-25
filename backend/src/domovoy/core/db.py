"""Подключение к Postgres, базовый класс моделей и инициализация схемы."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, MetaData, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from domovoy.core.config import get_settings

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def lock_row(session: AsyncSession, model: type[Any], row_id: int) -> None:
    """SELECT id ... FOR UPDATE без join-ов: у моделей eager-связи, а Postgres не блокирует внешний join."""
    await session.execute(select(model.id).where(model.id == row_id).with_for_update())


# create_all не добавляет колонки в существующие таблицы. Пока нет Alembic, новые колонки
# дописываются сюда идемпотентно, чтобы уже развёрнутая база обновлялась без потери данных.
ADD_COLUMNS = (
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_house_id INTEGER REFERENCES houses(id) ON DELETE SET NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarded BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS chats_checked_at TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar VARCHAR(300)",
    "ALTER TABLE houses ADD COLUMN IF NOT EXISTS info TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE houses ADD COLUMN IF NOT EXISTS setup_done BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE houses ADD COLUMN IF NOT EXISTS bot_is_admin BOOLEAN",
    "ALTER TABLE memberships ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ",
    "ALTER TABLE issues ADD COLUMN IF NOT EXISTS appeal_channel VARCHAR(256)",
    "ALTER TABLE mock_chat_messages ADD COLUMN IF NOT EXISTS photos JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS photos JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE shelters ADD COLUMN IF NOT EXISTS region VARCHAR(8)",
    "ALTER TABLE shelters ADD COLUMN IF NOT EXISTS osm_id BIGINT",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_shelters_osm_id ON shelters (osm_id)",
    "ALTER TABLE shelters ADD COLUMN IF NOT EXISTS official BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE shelters ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ",
    "ALTER TABLE houses ADD COLUMN IF NOT EXISTS region VARCHAR(8)",
    "CREATE INDEX IF NOT EXISTS ix_houses_region ON houses (region)",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS region VARCHAR(8)",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS source VARCHAR(256)",
)


async def init_db() -> None:
    """Создаёт расширение pgvector, таблицы и недостающие колонки. Вместо миграций MVP использует create_all."""
    import domovoy.modules.models  # noqa: F401  регистрирует все модели в metadata

    async with get_engine().begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))
        await conn.run_sync(Base.metadata.create_all)
        for ddl in ADD_COLUMNS:
            await conn.execute(text(ddl))
