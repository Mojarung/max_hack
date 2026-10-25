"""Членство в доме по чату MAX: сверка участников и администраторов, поиск домов жителя, вход по initData."""

import json
import time
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.bot.max_client import MaxApiError
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.core.max_auth import sign
from domovoy.modules.users import membership
from domovoy.modules.users.models import House, Membership, User
from integration.helpers import Home, make_home, next_id

pytestmark = pytest.mark.integration


class ChatClient:
    """MAX глазами бота: кто есть в каком чате, кто администратор, есть ли у бота права."""

    def __init__(self, chats: dict[int, list[dict[str, Any]]], *, bot_admin: bool = True, fail: bool = False) -> None:
        self.chats = chats
        self.bot_admin = bot_admin
        self.fail = fail
        self.calls = 0

    async def chat_members(self, chat_id: int, user_ids: list[int] | None = None) -> list[dict[str, Any]]:
        self.calls += 1
        if self.fail:
            raise MaxApiError(403, "chat.denied")
        members = self.chats.get(chat_id, [])
        return [m for m in members if not user_ids or m["user_id"] in user_ids]

    async def my_membership(self, chat_id: int) -> dict[str, Any]:
        if self.fail:
            raise OSError("network")
        return {"is_admin": self.bot_admin}


@pytest.fixture
def max_api(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(client: ChatClient) -> ChatClient:
        monkeypatch.setattr(membership, "get_max_client", lambda: client)
        return client

    return install


def member(user: User, **flags: bool) -> dict[str, Any]:
    return {"user_id": user.max_user_id, "first_name": user.first_name, "last_name": user.last_name, **flags}


async def role_in(user_id: int, house_id: int) -> str | None:
    async with get_sessionmaker()() as s:
        return await s.scalar(
            select(Membership.role).where(Membership.user_id == user_id, Membership.house_id == house_id)
        )


async def check(user: User, house: House, *, force: bool = False) -> str | None:
    async with get_sessionmaker()() as s:
        db_user = await s.get(User, user.id)
        db_house = await s.get(House, house.id)
        assert db_user and db_house
        role = await membership.check_access(s, db_user, db_house, force=force)
        await s.commit()
        return role


class TestCheckAccess:
    async def test_roles_follow_chat_admins(self, home: Home, max_api: Any) -> None:
        olga = home.residents[0]
        client = max_api(ChatClient({home.chat_id: [member(olga, is_admin=True)]}))
        assert await check(olga, home.house) == "admin"
        assert await role_in(olga.id, home.house.id) == "admin"
        # результат кэшируется на 10 минут: MAX второй раз не спрашиваем
        calls = client.calls
        assert await check(olga, home.house) == "admin"
        assert client.calls == calls
        client.chats[home.chat_id] = [member(olga)]
        assert await check(olga, home.house, force=True) == "resident"

    async def test_new_chat_member_gets_access(self, home: Home, max_api: Any) -> None:
        newcomer = User(max_user_id=8_700_000 + next_id(), first_name="Новый", last_name="")
        async with get_sessionmaker()() as s:
            s.add(newcomer)
            await s.commit()
        max_api(ChatClient({home.chat_id: [member(newcomer, is_owner=True)]}))
        assert await check(newcomer, home.house) == "admin"

    async def test_left_chat_loses_access_when_bot_is_admin(
        self, home: Home, max_api: Any, session: AsyncSession
    ) -> None:
        leaver = home.residents[1]
        async with get_sessionmaker()() as s:
            house = await s.get(House, home.house.id)
            user = await s.get(User, leaver.id)
            assert house and user
            house.bot_is_admin = True
            user.active_house_id = house.id
            await s.commit()
        max_api(ChatClient({home.chat_id: []}))
        assert await check(leaver, home.house) is None
        assert await role_in(leaver.id, home.house.id) is None
        assert (await session.get(User, leaver.id)).active_house_id is None  # type: ignore[union-attr]

    async def test_bot_without_rights_trusts_database(self, home: Home, max_api: Any) -> None:
        olga = home.residents[0]
        max_api(ChatClient({}, fail=True))
        assert await check(olga, home.house) == "resident"
        # без прав администратора бот не видит участников: житель из базы остаётся жителем
        max_api(ChatClient({home.chat_id: []}))
        assert await check(olga, home.house, force=True) == "resident"
        assert await check(home.outsider, home.house) is None

    async def test_demo_house_is_not_checked(self, max_api: Any, session: AsyncSession) -> None:
        client = max_api(ChatClient({}))
        anna = await session.scalar(select(User).where(User.max_user_id == 1001))
        demo = await session.scalar(select(House).where(House.max_chat_id == -100))
        assert anna and demo
        assert await membership.check_access(session, anna, demo) == "admin"
        assert client.calls == 0


class TestDiscoveryAndSync:
    async def test_discover_houses_where_user_is_in_chat(self, max_api: Any, session: AsyncSession) -> None:
        home, other = await make_home(), await make_home()
        traveller = home.residents[0]
        max_api(ChatClient({other.chat_id: [member(traveller, is_admin=True)]}))
        async with get_sessionmaker()() as s:
            user = await s.get(User, traveller.id)
            assert user is not None
            assert await membership.discover_houses(s, user) == 1
            # повторный поиск в течение 10 минут ничего не спрашивает
            assert await membership.discover_houses(s, user) == 0
            await s.commit()
            houses = [(h.id, r) for h, r in await membership.my_houses(s, user)]
        assert (home.house.id, "resident") in houses and (other.house.id, "admin") in houses

    async def test_discover_skips_unreachable_chats(self, home: Home, max_api: Any) -> None:
        max_api(ChatClient({}, fail=True))
        async with get_sessionmaker()() as s:
            user = await s.get(User, home.admin.id)
            assert user is not None
            assert await membership.discover_houses(s, user, force=True) == 0

    async def test_sync_chat_adds_members_and_removes_leavers(self, home: Home, max_api: Any) -> None:
        fresh = {"user_id": 8_800_000 + next_id(), "first_name": "Пётр", "avatar_url": "https://i.max.ru/p.jpg"}
        bot = {"user_id": 1, "is_bot": True}
        members = [member(home.admin, is_owner=True), member(home.residents[0], is_admin=True), fresh, bot, {}]
        max_api(ChatClient({home.chat_id: members}))
        async with get_sessionmaker()() as s:
            house = await s.get(House, home.house.id)
            assert house is not None
            assert await membership.sync_chat(s, house) == 3
            await s.commit()
            assert (house.members_count, house.bot_is_admin) == (3, True)
            peter = await s.scalar(select(User).where(User.max_user_id == fresh["user_id"]))
            assert peter is not None and peter.photo_url == "https://i.max.ru/p.jpg"
        assert await role_in(home.residents[0].id, home.house.id) == "admin"
        # ушедшие из чата жители теряют дом, раз бот видит полный список
        assert await role_in(home.residents[1].id, home.house.id) is None

    async def test_sync_without_rights_changes_nothing(self, home: Home, max_api: Any) -> None:
        max_api(ChatClient({}, fail=True))
        async with get_sessionmaker()() as s:
            house = await s.get(House, home.house.id)
            assert house is not None
            assert await membership.sync_chat(s, house) == 0
        assert await role_in(home.residents[1].id, home.house.id) == "resident"

    async def test_sync_endpoint_reports_members(self, api: httpx.AsyncClient, home: Home, max_api: Any) -> None:
        max_api(ChatClient({home.chat_id: [member(u, is_admin=u is home.admin) for u in home.users]}, bot_admin=False))
        resp = await api.post("/api/v1/house/sync", headers=home.h())
        assert resp.json() == {"members": 4, "bot_is_admin": False}

    async def test_current_house_prefers_active(self, home: Home) -> None:
        async with get_sessionmaker()() as s:
            user = await s.get(User, home.admin.id)
            assert user is not None
            user.active_house_id = None
            assert (await membership.current_house(s, user)).id == home.house.id  # type: ignore[union-attr]
            user.active_house_id = home.house.id
            assert (await membership.current_house(s, user)).id == home.house.id  # type: ignore[union-attr]
            stranger = User(max_user_id=8_900_000 + next_id())
            s.add(stranger)
            await s.flush()
            assert await membership.current_house(s, stranger) is None


TOKEN = "integration-bot-token"


def init_data(user: dict[str, Any], chat: dict[str, Any] | None = None) -> str:
    pairs = {"auth_date": str(int(time.time())), "query_id": "q", "user": json.dumps(user, ensure_ascii=False)}
    if chat:
        pairs["chat"] = json.dumps(chat)
    pairs["hash"] = sign(pairs, TOKEN)
    return "&".join(f"{k}={quote(v)}" for k, v in pairs.items())


class TestInitData:
    @pytest.fixture(autouse=True)
    def bot_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(get_settings(), "max_bot_token", type(get_settings().max_bot_token)(TOKEN))
        # клиент MAX в этих тестах не нужен: членство по подписанному чату
        monkeypatch.setattr(membership, "get_max_client", lambda: None)

    async def test_opened_from_house_chat_joins_house(self, api: httpx.AsyncClient, home: Home) -> None:
        newcomer = {"id": 9_100_000 + next_id(), "first_name": "Зоя", "username": "zoya"}
        raw = init_data(newcomer, {"id": home.chat_id, "type": "CHAT"})
        me = (await api.get("/api/v1/me", headers={"X-Max-Init-Data": raw})).json()
        assert me["house"]["id"] == home.house.id and me["role"] == "resident"
        assert me["user"]["first_name"] == "Зоя" and me["user"]["username"] == "zoya"

    async def test_bad_signature_is_401(self, api: httpx.AsyncClient) -> None:
        raw = init_data({"id": 1, "first_name": "X"}).replace("hash=", "hash=00")
        resp = await api.get("/api/v1/me", headers={"X-Max-Init-Data": raw})
        assert resp.status_code == 401

    async def test_from_dm_without_house_gets_pilot_house(
        self, api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stranger = {"id": 9_200_000 + next_id(), "first_name": "Гость"}
        me = (await api.get("/api/v1/me", headers={"X-Max-Init-Data": init_data(stranger)})).json()
        assert me["role"] == "resident" and me["house"]["is_demo"] is True
        monkeypatch.setattr(get_settings(), "pilot_house_fallback", False)
        other = {"id": 9_200_000 + next_id(), "first_name": "Гость"}
        resp = await api.get("/api/v1/me", headers={"X-Max-Init-Data": init_data(other)})
        assert resp.status_code == 404
