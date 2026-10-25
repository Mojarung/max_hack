"""Заглушки внешних сервисов для тестов: RabbitMQ, MinIO и внешняя сеть httpx."""

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class FakeBroker:
    """RabbitMQ в памяти: запоминает публикации и подписчиков, ничего никуда не отправляет."""

    published: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    handlers: dict[str, Callable[..., Any]] = field(default_factory=dict)
    started: int = 0

    async def publish(self, payload: dict[str, Any], *, exchange: Any = None, routing_key: str = "") -> None:
        self.published.append((routing_key, payload))

    def subscriber(self, queue: Any, exchange: Any = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.handlers[queue.routing_key or queue.name] = fn
            return fn

        return register

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.started -= 1

    # ---- удобные выборки для проверок ----

    def keys(self) -> list[str]:
        return [key for key, _ in self.published]

    def payloads(self, routing_key: str) -> list[dict[str, Any]]:
        return [p for key, p in self.published if key == routing_key]

    def sent(self, *, chat_id: int | None = None, user_id: int | None = None) -> list[dict[str, Any]]:
        """Команды боту «отправь сообщение», по желанию только в этот чат или этому жителю."""
        out = self.payloads("bot.send")
        if chat_id is not None:
            out = [p for p in out if p["chat_id"] == chat_id]
        if user_id is not None:
            out = [p for p in out if p["user_id"] == user_id]
        return out

    def events(self, name: str, house_id: int | None = None) -> list[dict[str, Any]]:
        out = self.payloads(f"rt.{name}")
        if house_id is not None:
            out = [p for p in out if p["house_id"] == house_id]
        return [p["data"] for p in out]


class _FakeObject:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        return None


@dataclass
class FakeMinio:
    """MinIO в памяти с тем же набором методов, что использует core/storage.py."""

    objects: dict[str, bytes] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)
    buckets: set[str] = field(default_factory=set)

    async def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    async def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    async def put_object(
        self, bucket: str, key: str, data: io.BytesIO, length: int, content_type: str = "application/octet-stream"
    ) -> None:
        raw = data.read()
        assert len(raw) == length
        self.objects[key] = raw
        self.types[key] = content_type

    async def get_object(self, bucket: str, key: str) -> _FakeObject:
        if key not in self.objects:
            raise KeyError(f"NoSuchKey: {key}")
        return _FakeObject(self.objects[key])

    async def remove_object(self, bucket: str, key: str) -> None:
        self.objects.pop(key, None)


HttpHandler = Callable[[httpx.Request], httpx.Response]


@dataclass
class FakeInternet:
    """Внешняя сеть для httpx: по умолчанию её нет, тест может подставить свой обработчик запросов."""

    handler: HttpHandler | None = None
    requests: list[httpx.Request] = field(default_factory=list)

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.handler is None:
            raise httpx.ConnectError("внешняя сеть в тестах выключена", request=request)
        return self.handler(request)
