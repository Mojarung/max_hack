from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domovoy.core.db import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    max_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(128))
    photo_url: Mapped[str | None] = mapped_column(String(1024))
    apartment: Mapped[str | None] = mapped_column(String(16))
    points: Mapped[int] = mapped_column(Integer, default=0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or "Сосед"


class Organization(TimestampMixin, Base):
    """Справочник исполнителей: УК, РСО, муниципалитет, аварийные службы, ГЖИ."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(256))
    phone: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(128), default="Республика Татарстан")


class House(TimestampMixin, Base):
    __tablename__ = "houses"

    id: Mapped[int] = mapped_column(primary_key=True)
    max_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    address: Mapped[str] = mapped_column(String(512), default="")
    lat: Mapped[float] = mapped_column(Float, default=55.7963)
    lon: Mapped[float] = mapped_column(Float, default=49.1088)
    members_count: Mapped[int] = mapped_column(Integer, default=10)
    vote_threshold_pct: Mapped[int] = mapped_column(Integer, default=15)
    uk_org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    uk_org: Mapped[Organization | None] = relationship(lazy="joined")


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "house_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    house_id: Mapped[int] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="resident")
    strikes: Mapped[int] = mapped_column(Integer, default=0)


class PointsLog(TimestampMixin, Base):
    __tablename__ = "points_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    house_id: Mapped[int | None] = mapped_column(ForeignKey("houses.id", ondelete="SET NULL"))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64))
