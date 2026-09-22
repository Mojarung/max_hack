"""Домовой Кузя: бот и мини-приложение MAX для жителей многоквартирного дома.

Один пакет, несколько процессов:
    domovoy api     REST API + SSE (uvicorn)
    domovoy bot     бот MAX (long polling) + эмулятор чата
    domovoy worker  обращения, напоминания, эскалации
    domovoy mcp     MCP-сервер «Жилищный навигатор»
    domovoy seed    заполнить демо-данные
"""

import argparse
import logging

import structlog


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )


def main() -> None:
    from domovoy.core.config import get_settings

    parser = argparse.ArgumentParser(prog="domovoy", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", choices=["api", "bot", "worker", "mcp", "seed"])
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104  слушаем внутри контейнера
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    _setup_logging(get_settings().log_level)

    if args.command == "api":
        import uvicorn

        from domovoy.core.aio import UVICORN_LOOP

        uvicorn.run(
            "domovoy.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port or 8000,
            proxy_headers=True,
            loop=UVICORN_LOOP,
        )
    elif args.command == "bot":
        from domovoy.bot.main import run

        run()
    elif args.command == "worker":
        from domovoy.worker.main import run as run_worker

        run_worker()
    elif args.command == "mcp":
        from domovoy.mcp_server.server import run as run_mcp

        run_mcp(args.host, args.port or 8765)
    elif args.command == "seed":
        from domovoy.core.db import init_db
        from domovoy.seed import seed_demo

        async def _seed() -> None:
            await init_db()
            await seed_demo()

        from domovoy.core import aio

        aio.run(_seed())
