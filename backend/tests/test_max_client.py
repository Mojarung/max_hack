"""Клиент MAX Bot API: сетевые сбои приходят вызывающему коду как MaxApiError."""

import httpx
import pytest

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
