"""Небольшие модели модулей ачивок, безопасности, модерации, MCP и эмулятора чата."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from domovoy.core.db import Base, TimestampMixin


class UserAchievement(TimestampMixin, Base):
    __tablename__ = "user_achievements"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)


class Shelter(TimestampMixin, Base):
    __tablename__ = "shelters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    address: Mapped[str] = mapped_column(String(512))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    capacity: Mapped[int | None] = mapped_column(Integer)
    # shelter | basement | parking | underpass | metro | bunker (подписи в safety/catalog.py)
    kind: Mapped[str] = mapped_column(String(32), default="shelter")
    # demo | osm | registry:<имя реестра>
    source: Mapped[str] = mapped_column(String(64), default="demo")
    # Регион по ISO 3166-2, например RU-ULY; у точек из OSM пусто
    region: Mapped[str | None] = mapped_column(String(8))
    # Объект OSM: id * 10 + код типа (1 узел, 2 линия, 3 отношение), см. safety/osm.py
    osm_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    # Из официального реестра региона (True) или заглублённое место из OSM / демо (False)
    official: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShelterFetch(Base):
    """Когда ячейку карты (0,02° × 0,02°) последний раз спрашивали у Overpass: не чаще раза в неделю."""

    __tablename__ = "shelter_fetches"

    cell: Mapped[str] = mapped_column(String(32), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    house_id: Mapped[int | None] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="drone")
    message: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Регион, по которому тревога пришла из официальной ленты (ISO 3166-2); у ручных тревог пусто
    region: Mapped[str | None] = mapped_column(String(8))
    # Откуда тревога: None - запустил администратор дома, «feed:<тип>:<источник>:<id поста>» - из ленты
    source: Mapped[str | None] = mapped_column(String(256))


class ModerationLog(TimestampMixin, Base):
    __tablename__ = "moderation_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    user_max_id: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)


class McpServer(TimestampMixin, Base):
    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    transport: Mapped[str] = mapped_column(String(32), default="streamable_http")
    url: Mapped[str] = mapped_column(String(1024))
    headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class MockChatMessage(TimestampMixin, Base):
    """Сообщения эмулятора чата MAX (мок-режим)."""

    __tablename__ = "mock_chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    from_user_max_id: Mapped[int | None] = mapped_column(BigInteger)
    from_name: Mapped[str | None] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text, default="")
    buttons: Mapped[list[list[dict[str, str]]]] = mapped_column(JSONB, default=list)
    photos: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    notice: Mapped[str | None] = mapped_column(String(256))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class Announcement(TimestampMixin, Base):
    """Объявление дома: доска в приложении + сообщение Кузи в чате (субботник, отключение воды, собрание)."""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    house_id: Mapped[int] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text, default="")
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)


class Document(TimestampMixin, Base):
    """Документ дома (виден всем жителям) или личный документ жителя (виден только ему)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    house_id: Mapped[int] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    # None: документ дома; иначе личный документ этого жителя
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(256))
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(256))
