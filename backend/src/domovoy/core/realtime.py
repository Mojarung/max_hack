"""Хаб SSE-подписчиков внутри одного процесса API.

События приходят из RabbitMQ (ключ `rt.*`), хаб раскладывает их по очередям клиентов
нужного дома. Так все экземпляры API получают одинаковый поток и масштабируются горизонтально.
"""

import asyncio
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

QUEUE_SIZE = 100


class RealtimeHub:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    @contextmanager
    def subscribe(self, house_id: int) -> Iterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(QUEUE_SIZE)
        self._subs[house_id].add(queue)
        try:
            yield queue
        finally:
            self._subs[house_id].discard(queue)

    def dispatch(self, message: dict[str, Any]) -> None:
        house_id = message.get("house_id")
        targets = (
            [q for subs in self._subs.values() for q in subs]
            if house_id is None
            else list(self._subs.get(house_id, ()))
        )
        for queue in targets:
            if queue.full():
                # медленный клиент: выбрасываем самое старое событие, свежие важнее
                queue.get_nowait()
            queue.put_nowait(message)


hub = RealtimeHub()
