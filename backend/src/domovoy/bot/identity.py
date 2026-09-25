"""Кто такой бот в MAX. Заполняется из GET /me при старте long polling."""

from dataclasses import dataclass

from domovoy.core.config import get_settings


@dataclass(slots=True)
class BotIdentity:
    user_id: int | None = None
    username: str = ""


BOT = BotIdentity(username=get_settings().max_bot_username)
