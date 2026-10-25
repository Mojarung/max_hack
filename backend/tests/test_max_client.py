"""Клиент MAX Bot API: сетевые сбои приходят вызывающему коду как MaxApiError."""

import httpx
import pytest
from fakes import FakeInternet

from domovoy.bot import max_client
from domovoy.bot.max_client import MaxApiError, MaxClient


def make_client(handler: httpx.MockTransport) -> MaxClient:
    client = MaxClient("https://max.test", "token")
    client._http = httpx.AsyncClient(base_url="https://max.test", transport=handler)
    return client


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(max_client.asyncio, "sleep", instant)


async def test_transport_error_becomes_api_error_after_retries() -> None:
    calls = 0

    def fail(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("proxy down", request=request)

    client = make_client(httpx.MockTransport(fail))
    with pytest.raises(MaxApiError) as info:
        await client.me()
    assert info.value.status == 0
    assert calls == max_client.RETRIES


async def test_transient_transport_error_is_retried() -> None:
    calls = 0

    def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"user_id": 1, "username": "kuzya_bot"})

    client = make_client(httpx.MockTransport(flaky))
    assert (await client.me())["username"] == "kuzya_bot"


async def test_non_json_body_becomes_api_error() -> None:
    client = make_client(httpx.MockTransport(lambda _: httpx.Response(200, text="<html>bad gateway</html>")))
    with pytest.raises(MaxApiError):
        await client.me()


class Recorder:
    """MAX API на MockTransport: отвечает по методу и пути, запоминает запросы."""

    def __init__(self, routes: dict[tuple[str, str], list[httpx.Response] | httpx.Response]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.routes.get((request.method, request.url.path), httpx.Response(404, text="not found"))
        if isinstance(answer, list):
            return answer.pop(0) if len(answer) > 1 else answer[0]
        return answer


def recorded_client(routes: dict[tuple[str, str], list[httpx.Response] | httpx.Response]) -> tuple[MaxClient, Recorder]:
    recorder = Recorder(routes)
    return make_client(httpx.MockTransport(recorder)), recorder


async def test_rate_limit_is_retried_then_reported() -> None:
    client, _ = recorded_client({("GET", "/me"): [httpx.Response(429), httpx.Response(200, json={"user_id": 7})]})
    assert (await client.me())["user_id"] == 7
    always, _ = recorded_client({("GET", "/me"): httpx.Response(429, text="slow down")})
    with pytest.raises(MaxApiError) as info:
        await always.me()
    assert info.value.status == 429


async def test_updates_marker_and_types() -> None:
    client, rec = recorded_client({("GET", "/updates"): httpx.Response(200, json={"updates": [{"a": 1}], "marker": 9})})
    updates, marker = await client.get_updates(5)
    assert (updates, marker) == ([{"a": 1}], 9)
    params = rec.requests[0].url.params
    assert params["marker"] == "5" and "message_callback" in params["types"]


async def test_send_message_waits_for_attachment() -> None:
    not_ready = httpx.Response(400, text='{"code": "attachment.not.ready"}')
    sent = httpx.Response(200, json={"message": {"body": {"mid": "mid.1"}}})
    client, rec = recorded_client({("POST", "/messages"): [not_ready, sent]})
    mid = await client.send_message(text="x" * 5000, chat_id=-5, attachments=[{"type": "image"}])
    assert mid == "mid.1"
    body = rec.requests[-1].read().decode()
    assert '"format":"markdown"' in body.replace(" ", "") and len(rec.requests) == 2
    assert rec.requests[-1].url.params["chat_id"] == "-5"

    dm, rec = recorded_client({("POST", "/messages"): httpx.Response(200, content=b"")})
    assert await dm.send_message(text="hi", user_id=42) is None
    assert rec.requests[0].url.params["user_id"] == "42"

    broken, _ = recorded_client({("POST", "/messages"): httpx.Response(403, text="chat.denied")})
    with pytest.raises(MaxApiError):
        await broken.send_message(text="hi", chat_id=-5)


async def test_message_actions_and_chat_info() -> None:
    ok = httpx.Response(200, json={"success": True})
    client, rec = recorded_client(
        {
            ("PUT", "/messages"): ok,
            ("DELETE", "/messages"): ok,
            ("POST", "/answers"): ok,
            ("GET", "/chats/-5"): httpx.Response(200, json={"title": "Дом"}),
            ("GET", "/messages/mid.1"): httpx.Response(200, json={"body": {"text": "t"}}),
            ("GET", "/chats/-5/members/admins"): httpx.Response(200, json={"members": [{"user_id": 1}]}),
            ("GET", "/chats/-5/members/me"): httpx.Response(200, json={"is_admin": True}),
            ("PUT", "/chats/-5/pin"): ok,
        }
    )
    await client.edit_message("mid.1", "новый текст", None)
    await client.delete_message("mid.1")
    await client.answer_callback("cb-1", "Готово")
    assert (await client.get_chat(-5))["title"] == "Дом"
    assert (await client.get_message("mid.1"))["body"]["text"] == "t"
    assert await client.chat_admins(-5) == [{"user_id": 1}]
    assert (await client.my_membership(-5))["is_admin"] is True
    await client.pin_message(-5, "mid.1")
    assert [r.method for r in rec.requests] == ["PUT", "DELETE", "POST", "GET", "GET", "GET", "GET", "PUT"]
    assert rec.requests[2].url.params["callback_id"] == "cb-1"
    await client.close()


async def test_chat_members_by_ids_and_all_pages() -> None:
    pages = [
        httpx.Response(200, json={"members": [{"user_id": 1}], "marker": 2}),
        httpx.Response(200, json={"members": [{"user_id": 2}]}),
    ]
    client, rec = recorded_client({("GET", "/chats/-5/members"): pages})
    assert [m["user_id"] for m in await client.chat_members(-5)] == [1, 2]
    assert rec.requests[1].url.params["marker"] == "2"
    by_id, rec = recorded_client(
        {("GET", "/chats/-5/members"): httpx.Response(200, json={"members": [{"user_id": 3}]})}
    )
    assert await by_id.chat_members(-5, [3, 4]) == [{"user_id": 3}]
    assert rec.requests[0].url.params["user_ids"] == "3,4"


async def test_upload_image_returns_photos_or_token(internet: FakeInternet) -> None:
    uploads: list[httpx.Response] = []
    # файл уходит отдельным клиентом httpx на адрес из слота загрузки: его отвечает «внешняя сеть» тестов
    internet.handler = lambda request: uploads.pop(0)
    slot = httpx.Response(200, json={"url": "https://upload.max.test/u", "token": "slot-token"})
    client, _ = recorded_client({("POST", "/uploads"): slot})

    uploads.append(httpx.Response(200, json={"photos": {"p": {"token": "t1"}}}))
    assert await client.upload_image(b"jpeg") == {"photos": {"p": {"token": "t1"}}}
    uploads.append(httpx.Response(200, content=b""))
    assert await client.upload_image(b"jpeg") == {"token": "slot-token"}
    uploads.append(httpx.Response(413, text="too big"))
    with pytest.raises(MaxApiError):
        await client.upload_image(b"jpeg")

    no_token, _ = recorded_client(
        {("POST", "/uploads"): httpx.Response(200, json={"url": "https://upload.max.test/u"})}
    )
    uploads.append(httpx.Response(200, json={}))
    with pytest.raises(MaxApiError, match="upload without token"):
        await no_token.upload_image(b"jpeg")
