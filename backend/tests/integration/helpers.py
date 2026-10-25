"""Общие помощники интеграционных тестов: свой дом с жителями, картинки, шлюз бота и апдейты MAX."""

import base64
import io
import itertools
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from domovoy.core.db import get_sessionmaker
from domovoy.modules.users.models import House, Membership, Organization, User
from domovoy.seed import HOUSE_LAT, HOUSE_LON

_ids = itertools.count(1)


def next_id() -> int:
    return next(_ids)


@dataclass
class Home:
    """Свой дом теста: администратор, три жителя и сосед из другого дома (outsider)."""

    house: House
    admin: User
    residents: list[User]
    outsider: User
    uk: Organization
    users: list[User] = field(default_factory=list)

    @property
    def chat_id(self) -> int:
        assert self.house.max_chat_id is not None
        return self.house.max_chat_id

    def h(self, user: User | None = None) -> dict[str, str]:
        """Заголовки мок-входа от имени жителя в этот дом."""
        who = user or self.admin
        return {"X-Dev-User": str(who.max_user_id), "X-House-Id": str(self.house.id)}


async def make_home(
    *,
    members_count: int = 10,
    lat: float = HOUSE_LAT,
    lon: float = HOUSE_LON,
    region: str | None = None,
    with_chat: bool = True,
) -> Home:
    n = next_id()
    async with get_sessionmaker()() as session:
        uk = Organization(kind="uk", name=f"УК «Тест-{n}»", email=f"uk{n}@example.org", phone="+7 (000) 000-00-00")
        house = House(
            max_chat_id=-(100_000 + n) if with_chat else None,
            title=f"Тестовый дом {n}",
            address=f"г. Тестовск, ул. Проверочная, д. {n}",
            lat=lat,
            lon=lon,
            members_count=members_count,
            vote_threshold_pct=15,
            uk_org=uk,
            region=region,
        )
        other = House(max_chat_id=-(500_000 + n), title=f"Соседний дом {n}", address="ул. Другая, 1", uk_org=uk)
        session.add_all([house, other])
        names = [("Админ", "Тестов", "1"), ("Олег", "Первый", "2"), ("Мария", "Вторая", "3"), ("Ильдар", "Третий", "4")]
        users = [
            User(max_user_id=7_000_000 + n * 10 + i, first_name=f, last_name=last, apartment=apt)
            for i, (f, last, apt) in enumerate(names)
        ]
        outsider = User(max_user_id=7_000_000 + n * 10 + 9, first_name="Чужой", last_name="Сосед")
        session.add_all([*users, outsider])
        await session.flush()
        session.add_all(
            Membership(user_id=u.id, house_id=house.id, role="admin" if i == 0 else "resident")
            for i, u in enumerate(users)
        )
        session.add(Membership(user_id=outsider.id, house_id=other.id, role="resident"))
        await session.commit()
    return Home(house=house, admin=users[0], residents=users[1:], outsider=outsider, uk=uk, users=users)


def png_bytes(color: str = "red", size: tuple[int, int] = (32, 24)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def png_data_url(color: str = "red") -> str:
    """Фото так, как его шлёт эмулятор чата: data:-ссылка."""
    return "data:image/png;base64," + base64.b64encode(png_bytes(color)).decode()


# ---------- бот: шлюз-заглушка и апдейты в формате MAX ----------


@dataclass
class FakeGateway:
    """Шлюз бота, который ничего не отправляет, а запоминает: что, куда и с какими кнопками."""

    members: int | None = None
    title: str | None = None
    can_delete: bool = True
    can_pin: bool = True
    sent: list[dict[str, Any]] = field(default_factory=list)
    edits: list[dict[str, Any]] = field(default_factory=list)
    pins: list[tuple[int, str]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)

    async def send(
        self,
        *,
        text: str,
        chat_id: int | None = None,
        user_id: int | None = None,
        buttons: list[list[dict[str, str]]] | None = None,
        photos: list[str] | None = None,
    ) -> str | None:
        mid = f"fake-{len(self.sent) + 1}"
        self.sent.append(
            {"text": text, "chat_id": chat_id, "user_id": user_id, "buttons": buttons, "photos": photos, "mid": mid}
        )
        return mid

    async def edit(self, *, mid: str, text: str | None, buttons: list[list[dict[str, str]]], media: Any = None) -> None:
        self.edits.append({"mid": mid, "text": text, "buttons": buttons, "media": media})

    async def pin(self, *, chat_id: int, mid: str) -> bool:
        self.pins.append((chat_id, mid))
        return self.can_pin

    async def delete(self, *, mid: str) -> bool:
        self.deleted.append(mid)
        return self.can_delete

    async def answer_callback(self, *, callback_id: str, notification: str) -> None:
        self.answers.append(notification)

    async def members_count(self, chat_id: int) -> int | None:
        return self.members

    async def chat_title(self, chat_id: int) -> str | None:
        return self.title

    @property
    def last(self) -> dict[str, Any]:
        assert self.sent, "бот ничего не отправил"
        return self.sent[-1]

    def texts(self) -> list[str]:
        return [m["text"] for m in self.sent]


def payloads(buttons: list[list[dict[str, str]]] | None) -> list[str]:
    """Что делают кнопки: payload у колбэков и приложения, url у ссылок."""
    return [b.get("payload") or b.get("url", "") for row in buttons or [] for b in row]


def max_user(user: User) -> dict[str, Any]:
    return {"user_id": user.max_user_id, "first_name": user.first_name, "last_name": user.last_name}


def message_update(
    user: User,
    chat_id: int,
    text: str = "",
    *,
    group: bool = True,
    photos: list[str] | None = None,
    mid: str = "mid.1",
    link: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "update_type": "message_created",
        "message": {
            "sender": max_user(user),
            "recipient": {"chat_id": chat_id, "chat_type": "chat" if group else "dialog"},
            "body": {
                "mid": mid,
                "text": text,
                "attachments": [{"type": "image", "payload": {"url": url}} for url in photos or []],
            },
            "link": link,
        },
    }


def callback_update(
    user: User, chat_id: int | None, payload: str, *, group: bool = True, mid: str = "mid.btn", text: str = "текст"
) -> dict[str, Any]:
    recipient = {} if chat_id is None else {"chat_id": chat_id, "chat_type": "chat" if group else "dialog"}
    return {
        "update_type": "message_callback",
        "callback": {"callback_id": "cb-1", "payload": payload, "user": max_user(user)},
        "message": {"recipient": recipient, "body": {"mid": mid, "text": text}},
    }


REPLY_TO_BOT = {"type": "reply", "sender": {"user_id": 1, "is_bot": True}, "message": {}}
