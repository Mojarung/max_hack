"""Общий клиент MAX Bot API для процессов, которым нужно спросить MAX, но не держать long polling.

API сверяет участников и администраторов чатов, воркер и бот используют свой экземпляр.
Без токена (мок-режим, проверка без MAX) возвращает None, и вызывающий код работает по данным БД.
"""

from functools import lru_cache

from domovoy.bot.max_client import MaxClient
from domovoy.core.config import get_settings


@lru_cache
def get_max_client() -> MaxClient | None:
    s = get_settings()
    return MaxClient(s.max_api_url, s.bot_token, s.max_poll_timeout) if s.has_max_token else None
