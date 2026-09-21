from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domovoy.core.config import get_settings
from domovoy.core.db import Base, TimestampMixin
from domovoy.modules.users.models import House, Organization, User

EMBEDDING_DIM = get_settings().embedding_dim


class Issue(TimestampMixin, Base):
    __tablename__ = "issues"
    __table_args__ = (Index("ix_issues_search", "search", postgresql_using="gin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    house_id: Mapped[int] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    location_hint: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), index=True)
    classifier_source: Mapped[str] = mapped_column(String(16), default="rules")
    classifier_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="voting", index=True)
    photos: Mapped[list[str]] = mapped_column(JSONB, default=list)
    votes_count: Mapped[int] = mapped_column(Integer, default=0)
    votes_needed: Mapped[int] = mapped_column(Integer, default=3)
    responsible_org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    legal_basis: Mapped[str] = mapped_column(Text, default="")
    deadline_hours: Mapped[int] = mapped_column(Integer, default=240)
    appeal_text: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chat_message_id: Mapped[str | None] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    search: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('russian', coalesce(title, '') || ' ' || coalesce(description, '')"
            " || ' ' || coalesce(location_hint, ''))",
            persisted=True,
        ),
    )

    author: Mapped[User] = relationship(lazy="joined")
    house: Mapped[House] = relationship(lazy="joined")
    responsible_org: Mapped[Organization | None] = relationship(lazy="joined")


class IssueVote(TimestampMixin, Base):
    __tablename__ = "issue_votes"

    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class IssueUpdate(TimestampMixin, Base):
    """Лента статусов заявки, её видит житель в карточке."""

    __tablename__ = "issue_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")
