from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domovoy.core.db import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    max_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(128))
    # Фото из профиля MAX: обновляется при каждом входе
    photo_url: Mapped[str | None] = mapped_column(String(1024))
    # Выбор жителя поверх фото из MAX: «preset:N» (готовая картинка) или «upload:<ключ MinIO>»
    avatar: Mapped[str | None] = mapped_column(String(300))
    apartment: Mapped[str | None] = mapped_column(String(16))
    points: Mapped[int] = mapped_column(Integer, default=0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Дом, который житель выбрал последним: его видят и мини-приложение, и личка с ботом
    active_house_id: Mapped[int | None] = mapped_column(ForeignKey("houses.id", ondelete="SET NULL"))
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Когда последний раз сверяли, в каких чатах с Кузей состоит житель
    chats_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    region: Mapped[str] = mapped_column(String(128), default="Ульяновская область")


class House(TimestampMixin, Base):
    __tablename__ = "houses"

    id: Mapped[int] = mapped_column(primary_key=True)
    max_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    address: Mapped[str] = mapped_column(String(512), default="")
    lat: Mapped[float] = mapped_column(Float, default=54.3142)
    lon: Mapped[float] = mapped_column(Float, default=48.4031)
    members_count: Mapped[int] = mapped_column(Integer, default=10)
    vote_threshold_pct: Mapped[int] = mapped_column(Integer, default=15)
    uk_org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Свободная информация о доме от администратора: диспетчерская, председатель, коды, правила
    info: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Администратор ещё не прошёл первичную настройку (дом создан из чата с пустым адресом)
    setup_done: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Кузя администратор чата: может удалять сообщения и видеть участников
    bot_is_admin: Mapped[bool | None] = mapped_column(Boolean)
    # Субъект РФ по ISO 3166-2 (RU-ULY): по нему дом получает официальные оповещения своего региона.
    # Заполняется из Nominatim при выборе адреса (поле ISO3166-2-lvl4) или вручную
    region: Mapped[str | None] = mapped_column(String(8), index=True)

    uk_org: Mapped[Organization | None] = relationship(lazy="joined")


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "house_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    house_id: Mapped[int] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="resident")
    strikes: Mapped[int] = mapped_column(Integer, default=0)
    # Когда роль последний раз сверяли с участниками и администраторами чата MAX
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PointsLog(TimestampMixin, Base):
    __tablename__ = "points_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    house_id: Mapped[int | None] = mapped_column(ForeignKey("houses.id", ondelete="SET NULL"))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64))
