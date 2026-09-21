from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Computed, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domovoy.core.db import Base, TimestampMixin
from domovoy.modules.issues.models import EMBEDDING_DIM
from domovoy.modules.users.models import User


class Event(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_search", "search", postgresql_using="gin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    house_id: Mapped[int] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="other")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    place: Mapped[str] = mapped_column(String(200), default="")
    max_participants: Mapped[int | None] = mapped_column(Integer)
    participants_count: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    search: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('russian', coalesce(title, '') || ' ' || coalesce(description, '')"
            " || ' ' || coalesce(place, ''))",
            persisted=True,
        ),
    )

    author: Mapped[User] = relationship(lazy="joined")


class EventParticipant(TimestampMixin, Base):
    __tablename__ = "event_participants"

    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    user: Mapped[User] = relationship(lazy="joined")


class EventComment(TimestampMixin, Base):
    __tablename__ = "event_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)

    author: Mapped[User] = relationship(lazy="joined")
