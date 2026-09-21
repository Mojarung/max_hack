"""Шина сообщений на RabbitMQ (FastStream).

Одна topic-точка обмена `domovoy`. Ключи маршрутизации:
- `rt.<тип>`: события реального времени, их получает каждый экземпляр API и отдаёт в SSE;
- `bot.send`: команда боту отправить сообщение (из API и воркера);
- `bot.inbound`: входящие апдейты эмулятора чата (мок-режим);
- `issue.dispatch`: заявка набрала порог голосов, воркер формирует обращение.
"""

from functools import lru_cache
from typing import Any

import structlog
from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from domovoy.core.config import get_settings

log = structlog.get_logger(__name__)

EXCHANGE = RabbitExchange("domovoy", type=ExchangeType.TOPIC, durable=True)

Q_BOT_SEND = RabbitQueue("bot.send", durable=True, routing_key="bot.send")
Q_BOT_INBOUND = RabbitQueue("bot.inbound", durable=True, routing_key="bot.inbound")
Q_ISSUE_DISPATCH = RabbitQueue("issue.dispatch", durable=True, routing_key="issue.dispatch")


@lru_cache
def get_broker() -> RabbitBroker:
    return RabbitBroker(get_settings().rabbit_url, graceful_timeout=10.0)


async def publish(routing_key: str, payload: dict[str, Any]) -> None:
    """Публикует сообщение. Ошибка шины не должна ронять пользовательский запрос."""
    try:
        await get_broker().publish(payload, exchange=EXCHANGE, routing_key=routing_key)
    except Exception:
        log.exception("bus.publish_failed", routing_key=routing_key)


async def emit(house_id: int | None, event: str, data: dict[str, Any]) -> None:
    """Событие реального времени для мини-приложения."""
    await publish(f"rt.{event}", {"house_id": house_id, "event": event, "data": data})


async def bot_send(
    *,
    text: str,
    chat_id: int | None = None,
    user_id: int | None = None,
    buttons: list[list[dict[str, str]]] | None = None,
) -> None:
    """Просит процесс бота отправить сообщение в чат или в личку."""
    await publish(
        "bot.send",
        {"chat_id": chat_id, "user_id": user_id, "text": text, "buttons": buttons or []},
    )
