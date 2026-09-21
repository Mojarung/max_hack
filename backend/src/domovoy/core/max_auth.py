"""Проверка подписи initData мини-приложения MAX.

Алгоритм из документации https://dev.max.ru/docs/webapps/validation:
1. разбить строку на пары key=value, `hash` обязателен и встречается один раз;
2. убрать `hash`, декодировать значения, отсортировать по ключу;
3. склеить пары `key=value` через перевод строки;
4. secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN);
5. сравнить hex(HMAC_SHA256(key=secret_key, msg=launch_params)) с `hash`.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote


class InitDataError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InitData:
    user: dict[str, Any]
    chat: dict[str, Any] | None
    start_param: str | None
    auth_date: int


def _parse_pairs(raw: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for chunk in raw.split("&"):
        if not chunk:
            continue
        key, sep, value = chunk.partition("=")
        if not sep:
            raise InitDataError("Некорректная пара в initData")
        if key in pairs:
            raise InitDataError(f"Ключ {key} повторяется")
        pairs[key] = unquote(value)
    return pairs


def sign(pairs: dict[str, str], bot_token: str) -> str:
    launch_params = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, launch_params.encode(), hashlib.sha256).hexdigest()


def validate_init_data(raw: str, bot_token: str, ttl_seconds: int, now: float | None = None) -> InitData:
    if not bot_token:
        raise InitDataError("Токен бота не настроен")
    pairs = _parse_pairs(raw)
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataError("В initData нет подписи")
    if not hmac.compare_digest(sign(pairs, bot_token), received):
        raise InitDataError("Подпись initData не совпала")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("Некорректный auth_date") from exc
    current = now if now is not None else time.time()
    if current - auth_date > ttl_seconds:
        raise InitDataError("Сессия устарела, откройте мини-приложение заново")
    try:
        user = json.loads(pairs["user"])
        chat = json.loads(pairs["chat"]) if pairs.get("chat") else None
    except (KeyError, json.JSONDecodeError) as exc:
        raise InitDataError("В initData нет данных пользователя") from exc
    return InitData(user=user, chat=chat, start_param=pairs.get("start_param"), auth_date=auth_date)
