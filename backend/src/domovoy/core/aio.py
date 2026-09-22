"""Запуск asyncio с учётом Windows: psycopg (память агента) не работает на ProactorEventLoop."""

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any

WINDOWS = sys.platform == "win32"
UVICORN_LOOP = "asyncio:SelectorEventLoop" if WINDOWS else "auto"


def run(coro: Coroutine[Any, Any, None]) -> None:
    asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop if WINDOWS else None)
