"""Шлюзы бота (эмулятор и MAX), эмулятор чата в API и процесс бота с очередями RabbitMQ."""

import asyncio
from typing import Any

import httpx
import pytest
from fakes import FakeBroker
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.bot import main as bot_main
from domovoy.bot.gateway import MaxGateway, MockGateway, deep_link, to_max_keyboard
from domovoy.bot.identity import BOT
from domovoy.bot.max_client import MaxApiError
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.core.storage import save_bytes
from domovoy.modules.devchat import service as devchat
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.models import Issue
from domovoy.modules.users.models import House, User
from domovoy.seed import DEMO_CHAT_ID
from integration.helpers import FakeGateway, Home, png_bytes, png_data_url

pytestmark = pytest.mark.integration

APP_BUTTONS = [[{"type": "callback", "text": "👍", "payload": "vote:1"}], [issues.app_button("Подробнее", "issue_1")]]


async def history(chat_id: int) -> list[dict[str, Any]]:
    async with get_sessionmaker()() as s:
        return [m.dump() for m in await devchat.history(s, chat_id)]


class TestMockGateway:
    async def test_send_edit_pin_delete(self, home: Home, broker: FakeBroker) -> None:
        gw = MockGateway()
        key = await save_bytes("issues", png_bytes())
        mid = await gw.send(chat_id=home.chat_id, text="Привет, дом!", buttons=APP_BUTTONS, photos=[key] * 4)
        assert mid is not None and mid.startswith("mock-")
        (msg,) = await history(home.chat_id)
        assert (msg["text"], msg["from"], msg["deleted"]) == ("Привет, дом!", None, False)
        assert msg["photos"] == [f"/api/v1/media/{key}"] * 3
        assert broker.events("chat.message")[0]["id"] == mid

        await gw.edit(mid=mid, text="Обновлено", buttons=[])
        await gw.edit(mid=mid, text=None, buttons=APP_BUTTONS)
        assert await gw.pin(chat_id=home.chat_id, mid=mid) is True
        (msg,) = await history(home.chat_id)
        assert (msg["text"], msg["notice"], msg["buttons"]) == ("Обновлено", "📌 Закреплено Кузей", APP_BUTTONS)
        assert await gw.delete(mid=mid) is True
        assert (await history(home.chat_id))[0]["deleted"] is True

        assert await gw.pin(chat_id=home.chat_id, mid="fake-1") is False
        assert await gw.delete(mid="mock-abc") is False
        assert await gw.send(text="никому") is None
        assert await gw.members_count(home.chat_id) is None and await gw.chat_title(home.chat_id) is None

    async def test_dm_is_chat_with_user_id_and_callback_notice(self, home: Home, broker: FakeBroker) -> None:
        gw = MockGateway()
        user = home.residents[0]
        await gw.send(user_id=user.max_user_id, text="Личное сообщение")
        assert [m["text"] for m in await history(user.max_user_id)] == ["Личное сообщение"]
        await gw.answer_callback(callback_id="cb-9", notification="Голос учтён")
        assert broker.events("chat.notice") == [{"callback_id": "cb-9", "text": "Голос учтён"}]


class FakeMaxClient:
    """Клиент MAX Bot API без сети: запоминает вызовы, по желанию отказывает кнопкам open_app."""

    def __init__(self, *, reject_open_app: bool = False, broken: bool = False) -> None:
        self.reject_open_app = reject_open_app
        self.broken = broken
        self.calls: list[tuple[str, Any]] = []

    def _check(self, attachments: list[dict[str, Any]] | None) -> None:
        rows = [a for a in attachments or [] if a.get("type") == "inline_keyboard"]
        buttons = [b for a in rows for row in a["payload"]["buttons"] for b in row]
        if self.reject_open_app and any(b["type"] == "open_app" for b in buttons):
            raise MaxApiError(400, "button.open_app is not allowed")

    async def upload_image(self, data: bytes) -> dict[str, Any]:
        self.calls.append(("upload", len(data)))
        return {"token": f"tok-{len(self.calls)}"}

    async def send_message(self, **kwargs: Any) -> str:
        self.calls.append(("send", kwargs))
        self._check(kwargs.get("attachments"))
        return "mid.max.1"

    async def get_message(self, mid: str) -> dict[str, Any]:
        if self.broken:
            raise MaxApiError(500, "down")
        return {"body": {"text": "Исходный текст", "attachments": [{"type": "image", "payload": {"token": "t0"}}]}}

    async def edit_message(self, mid: str, text: str, attachments: list[dict[str, Any]]) -> None:
        self.calls.append(("edit", (mid, text, attachments)))
        self._check(attachments)

    async def pin_message(self, chat_id: int, mid: str) -> None:
        if self.broken:
            raise MaxApiError(403, "no rights")

    async def delete_message(self, mid: str) -> None:
        if self.broken:
            raise MaxApiError(403, "no rights")

    async def answer_callback(self, callback_id: str, notification: str) -> None:
        self.calls.append(("answer", (callback_id, notification)))

    async def get_chat(self, chat_id: int) -> dict[str, Any]:
        if self.broken:
            raise MaxApiError(404, "chat.not.found")
        return {"participants_count": 12, "title": "  Чат дома 5  "}


@pytest.fixture
def bot_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BOT, "user_id", 4242)
    monkeypatch.setattr(BOT, "username", "kuzya_test_bot")


@pytest.mark.usefixtures("bot_identity")
class TestMaxGateway:
    def test_keyboard_native_and_deep_link(self) -> None:
        buttons = [*APP_BUTTONS, [{"type": "link", "text": "Карта", "url": "https://yandex.ru/maps"}], []]
        native = to_max_keyboard(buttons)
        assert native is not None
        rows = native[0]["payload"]["buttons"]
        assert rows[1][0] == {
            "type": "open_app",
            "text": "Подробнее",
            "web_app": "kuzya_test_bot",
            "contact_id": 4242,
            "payload": "issue_1",
        }
        assert rows[2][0]["url"] == "https://yandex.ru/maps" and len(rows) == 3
        linked = to_max_keyboard(buttons, native_app=False)
        assert linked is not None and linked[0]["payload"]["buttons"][1][0]["url"] == deep_link("issue_1")
        assert to_max_keyboard(None) is None

    async def test_send_uploads_photos_and_falls_back_to_link(self) -> None:
        client = FakeMaxClient(reject_open_app=True)
        gw = MaxGateway(client)  # type: ignore[arg-type]
        key = await save_bytes("issues", png_bytes())
        mid = await gw.send(chat_id=-5, text="Заявка", buttons=APP_BUTTONS, photos=[key, "issues/missing.jpg"])
        assert mid == "mid.max.1"
        sends = [c[1] for c in client.calls if c[0] == "send"]
        assert len(sends) == 2  # первая попытка с open_app отклонена, вторая с диплинком
        attachments = sends[1]["attachments"]
        assert attachments[0] == {"type": "image", "payload": {"token": "tok-1"}}
        assert attachments[1]["payload"]["buttons"][1][0]["type"] == "link"

    async def test_send_without_app_button_reraises(self) -> None:
        gw = MaxGateway(FakeMaxClient(reject_open_app=True))  # type: ignore[arg-type]
        assert await gw.send(user_id=7, text="Без кнопок") == "mid.max.1"

        class Rejecting(FakeMaxClient):
            async def send_message(self, **kwargs: Any) -> str:
                raise MaxApiError(400, "text too long")

        with pytest.raises(MaxApiError):
            await MaxGateway(Rejecting()).send(
                chat_id=-5, text="x", buttons=[[{"type": "callback", "text": "a", "payload": "b"}]]
            )  # type: ignore[arg-type]

    async def test_edit_keeps_photos_and_text(self) -> None:
        client = FakeMaxClient(reject_open_app=True)
        gw = MaxGateway(client)  # type: ignore[arg-type]
        await gw.edit(mid="mid.5", text=None, buttons=APP_BUTTONS)
        edits = [c[1] for c in client.calls if c[0] == "edit"]
        assert len(edits) == 2
        mid, text, attachments = edits[-1]
        assert (mid, text) == ("mid.5", "Исходный текст")
        assert attachments[0] == {"type": "image", "payload": {"token": "t0"}}

        broken = MaxGateway(FakeMaxClient(broken=True))  # type: ignore[arg-type]
        await broken.edit(mid="mid.6", text=None, buttons=[])  # текста не узнали: править нечего

    async def test_pin_delete_answer_and_chat_info(self) -> None:
        ok = MaxGateway(FakeMaxClient())  # type: ignore[arg-type]
        assert await ok.pin(chat_id=-5, mid="m") is True and await ok.delete(mid="m") is True
        assert (await ok.members_count(-5), await ok.chat_title(-5)) == (12, "Чат дома 5")
        await ok.answer_callback(callback_id="cb", notification="Готово")
        broken = MaxGateway(FakeMaxClient(broken=True))  # type: ignore[arg-type]
        assert await broken.pin(chat_id=-5, mid="m") is False and await broken.delete(mid="m") is False
        assert (await broken.members_count(-5), await broken.chat_title(-5)) == (None, None)


class TestEmulatorApi:
    async def test_chats_and_history(self, api: httpx.AsyncClient) -> None:
        chats = (await api.get("/api/v1/dev/chats", params={"user_id": 1001})).json()
        assert {"chat_id": DEMO_CHAT_ID, "title": "Чат: Дом 7 на Демонстрационной", "type": "chat"} in chats
        assert chats[-1] == {"chat_id": 1001, "title": "Личка с Кузей", "type": "dialog"}
        messages = (await api.get("/api/v1/dev/chat/messages", params={"chat_id": DEMO_CHAT_ID})).json()
        assert messages[0]["text"].startswith("Всем привет! Я Домовой Кузя")

    async def test_send_and_callback_become_max_updates(
        self, api: httpx.AsyncClient, home: Home, broker: FakeBroker
    ) -> None:
        user = home.residents[0]
        body = {
            "chat_id": home.chat_id,
            "user_id": user.max_user_id,
            "text": "Кузя, течёт кран",
            "photos": [png_data_url(), "javascript:alert(1)"],
        }
        assert (await api.post("/api/v1/dev/chat/send", json=body)).json() == {"ok": True}
        (inbound,) = broker.payloads("bot.inbound")
        message = inbound["message"]
        assert inbound["update_type"] == "message_created"
        assert message["recipient"] == {"chat_id": home.chat_id, "chat_type": "chat"}
        assert len(message["body"]["attachments"]) == 1
        (shown,) = await history(home.chat_id)
        assert shown["text"] == "Кузя, течёт кран\n📷 Фото: 1"
        assert shown["from"] == {"user_id": user.max_user_id, "name": "Олег Первый"}

        cb = {
            "chat_id": user.max_user_id,
            "user_id": user.max_user_id,
            "message_id": "mock-1",
            "payload": "menu:issues",
        }
        assert (await api.post("/api/v1/dev/chat/callback", json=cb)).status_code == 200
        callback = broker.payloads("bot.inbound")[-1]
        assert callback["callback"]["payload"] == "menu:issues"
        assert callback["message"]["recipient"]["chat_type"] == "dialog"

    async def test_send_rules(self, api: httpx.AsyncClient, home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
        user = home.residents[0]
        foreign = {"chat_id": home.residents[1].max_user_id, "user_id": user.max_user_id, "text": "Привет"}
        assert (await api.post("/api/v1/dev/chat/send", json=foreign)).status_code == 403
        empty = {"chat_id": home.chat_id, "user_id": user.max_user_id, "text": "  "}
        assert (await api.post("/api/v1/dev/chat/send", json=empty)).status_code == 422
        unknown = {"chat_id": home.chat_id, "user_id": 1, "text": "Привет"}
        assert (await api.post("/api/v1/dev/chat/send", json=unknown)).status_code == 404
        monkeypatch.setattr(get_settings(), "mock_max", False)
        assert (await api.get("/api/v1/dev/chats")).status_code == 404
        assert (await api.get("/api/v1/dev/chat/messages", params={"chat_id": 1})).status_code == 404
        assert (await api.post("/api/v1/dev/chat/send", json=empty)).status_code == 404
        cb = {"chat_id": 1, "user_id": 1, "message_id": "m", "payload": "x"}
        assert (await api.post("/api/v1/dev/chat/callback", json=cb)).status_code == 404


async def wait_for(condition: Any, limit_s: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + limit_s
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "не дождались"
        await asyncio.sleep(0.01)


class TestBotProcess:
    async def test_target_gateway(self, home: Home) -> None:
        runtime = bot_main.BotRuntime()
        assert runtime.client is None and runtime.max is None
        assert await runtime.target_gateway(home.chat_id, None) is runtime.mock
        runtime.max = FakeGateway()
        assert await runtime.target_gateway(home.chat_id, None) is runtime.max
        assert await runtime.target_gateway(DEMO_CHAT_ID, None) is runtime.mock
        assert await runtime.target_gateway(1001, None) is runtime.mock  # личка демо-жителя
        assert await runtime.target_gateway(None, 1001) is runtime.mock
        assert await runtime.target_gateway(None, home.admin.max_user_id) is runtime.max

    async def test_queues_send_refresh_and_inbound(
        self, home: Home, broker: FakeBroker, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
    ) -> None:
        inbound: list[dict[str, Any]] = []

        async def fake_handle(update_: dict[str, Any], gw: Any) -> None:
            inbound.append(update_)

        monkeypatch.setattr(bot_main, "handle_update", fake_handle)
        broker.handlers.clear()
        task = asyncio.create_task(bot_main.main())
        await wait_for(lambda: "bot.inbound" in broker.handlers and broker.started > 0)

        async with get_sessionmaker()() as s:
            author = await s.get(User, home.residents[0].id)
            house = await s.get(House, home.house.id)
            assert author and house
            issue = await issues.create_issue(s, user=author, house=house, description="Сломаны качели во дворе")
        cmd = {"chat_id": home.chat_id, "text": "Заявка", "buttons": [], "pin": True, "ref": {"issue_id": issue.id}}
        await broker.handlers["bot.send"](cmd)
        saved = await session.get(Issue, issue.id)
        assert saved is not None and saved.chat_message_id and saved.chat_message_id.startswith("mock-")
        (msg,) = await history(home.chat_id)
        assert msg["notice"] == "📌 Закреплено Кузей"

        # голос из приложения: бот переписывает сообщение заявки со свежим счётчиком
        await session.execute(update(Issue).where(Issue.id == issue.id).values(votes_count=2))
        await session.commit()
        await broker.handlers["bot.issue_refresh"]({"issue_id": issue.id})
        (msg,) = await history(home.chat_id)
        assert "Поддержали 2 из 3" in msg["text"]
        await broker.handlers["bot.issue_refresh"]({"issue_id": 10**8})

        await broker.handlers["bot.inbound"]({"update_type": "message_created", "message": {}})
        await wait_for(lambda: bool(inbound))

        async def refuse(self: MockGateway, **kwargs: Any) -> str:
            raise MaxApiError(403, "chat.denied")

        monkeypatch.setattr(MockGateway, "send", refuse)
        await broker.handlers["bot.send"]({"user_id": home.admin.max_user_id, "text": "Не дойдёт"})

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert broker.started == 0

    async def test_poll_waits_for_max_and_spawns_updates(
        self, monkeypatch: pytest.MonkeyPatch, bot_identity: None
    ) -> None:
        handled: list[dict[str, Any]] = []

        async def fake_handle(update_: dict[str, Any], gw: Any) -> None:
            handled.append(update_)

        class PollClient:
            def __init__(self) -> None:
                self.me_calls = 0
                self.update_calls = 0

            async def me(self) -> dict[str, Any]:
                self.me_calls += 1
                if self.me_calls == 1:
                    raise OSError("network is unreachable")
                return {"user_id": 777, "username": "other_name_bot"}

            async def get_updates(self, marker: int | None) -> tuple[list[dict[str, Any]], int | None]:
                self.update_calls += 1
                if self.update_calls == 1:
                    raise MaxApiError(502, "bad gateway")
                if self.update_calls == 2:
                    return [{"update_type": "bot_started"}], 5
                raise asyncio.CancelledError

        monkeypatch.setattr(bot_main, "handle_update", fake_handle)
        monkeypatch.setattr(bot_main, "POLL_ERROR_BACKOFF", 0)
        runtime = bot_main.BotRuntime()
        runtime.client = PollClient()  # type: ignore[assignment]
        runtime.max = FakeGateway()
        with pytest.raises(asyncio.CancelledError):
            await runtime.poll()
        await wait_for(lambda: bool(handled))
        assert handled == [{"update_type": "bot_started"}]
        assert (BOT.user_id, BOT.username) == (777, "other_name_bot")
