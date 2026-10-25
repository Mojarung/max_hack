"""Источники официальных оповещений (ленты), из которых Кузя забирает тревоги по регионам."""

from datetime import datetime
from typing import Literal

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from domovoy.core.db import Base, TimestampMixin

SourceType = Literal["max_channel", "telegram_web", "vk_wall", "mchs_rss"]
SOURCE_TYPES: tuple[SourceType, ...] = ("max_channel", "telegram_web", "vk_wall", "mchs_rss")


class AlertSource(TimestampMixin, Base):
    """Откуда берём оповещения региона.

    ``ref`` зависит от типа: chat_id канала MAX, имя Telegram-канала, owner_id сообщества ВКонтакте
    (отрицательный для групп) или URL RSS-ленты сайта МЧС.
    """

    __tablename__ = "alert_sources"
    __table_args__ = (UniqueConstraint("type", "ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(8), index=True)
    type: Mapped[str] = mapped_column(String(16))
    ref: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(256), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # id последнего обработанного поста: у RSS это ссылка, у Telegram номер, у VK и MAX id сообщения
    last_post_id: Mapped[str | None] = mapped_column(String(512))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
