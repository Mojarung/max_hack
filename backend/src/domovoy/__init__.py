"""Домовой Кузя: бот и мини-приложение MAX для жителей многоквартирного дома.

Один пакет, несколько процессов:
    domovoy api     REST API + SSE (uvicorn)
    domovoy bot     бот MAX (long polling) + эмулятор чата
    domovoy worker  обращения, напоминания, эскалации
    domovoy mcp     MCP-сервер «Жилищный навигатор»
    domovoy seed    заполнить демо-данные
    domovoy import-shelters файл.csv --region RU-ORL --source "Реестр укрытий ..."
                    загрузить реестр укрытий региона (формат: backend/data/shelters/README.md)
    domovoy add-alert-source --region RU-ULY --type telegram_web --ref <канал> --title "..."
                    добавить источник официальных оповещений региона (docs/ALERTS.md)
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
    parser.add_argument(
        "command", choices=["api", "bot", "worker", "mcp", "seed", "import-shelters", "add-alert-source"]
    )
    parser.add_argument("file", nargs="?", help="CSV реестра укрытий (только для import-shelters)")
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104  слушаем внутри контейнера
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--region", default=None, help="код региона ISO 3166-2, например RU-ORL")
    parser.add_argument("--source", default=None, help="название реестра, например «Реестр укрытий Орловской области»")
    # add-alert-source: источник официальных оповещений региона (docs/ALERTS.md)
    parser.add_argument("--type", default=None, help="тип источника: max_channel, telegram_web, vk_wall, mchs_rss")
    parser.add_argument("--ref", default=None, help="chat_id канала MAX, имя Telegram-канала, owner_id VK или URL RSS")
    parser.add_argument("--title", default="", help="как называть источник жителям, например «МЧС Ульяновской области»")
    parser.add_argument("--disabled", action="store_true", help="добавить источник выключенным")
    args = parser.parse_args()
    if args.command == "import-shelters" and not (args.file and args.region and args.source):
        parser.error("import-shelters: нужны файл CSV, --region и --source")
    if args.command == "add-alert-source" and not (args.region and args.type and args.ref):
        parser.error("add-alert-source: нужны --region, --type и --ref")
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
    elif args.command == "add-alert-source":
        from domovoy.core import aio
        from domovoy.core.db import init_db
        from domovoy.modules.safety import feeds

        async def _add_source() -> None:
            await init_db()
            src = await feeds.add_source(args.region, args.type, args.ref, args.title, enabled=not args.disabled)
            state = "включён" if src.enabled else "выключен"
            print(f"Источник #{src.id}: {src.region}, {src.type}, {src.ref}, «{src.title}», {state}")

        aio.run(_add_source())
    elif args.command == "seed":
        from domovoy.core.db import init_db
        from domovoy.seed import seed_demo

        async def _seed() -> None:
            await init_db()
            await seed_demo()

        from domovoy.core import aio

        aio.run(_seed())
    elif args.command == "import-shelters":
        from pathlib import Path

        from domovoy.core import aio
        from domovoy.core.db import init_db
        from domovoy.modules.safety.importer import ImportError_, import_shelters

        async def _import() -> None:
            await init_db()
            stats = await import_shelters(Path(args.file), args.region, args.source)
            # итог для оператора в консоли, а не в структурный лог
            print(
                f"Готово: добавлено {stats.created}, обновлено {stats.updated}, "
                f"геокодировано {stats.geocoded}, пропущено без координат {stats.skipped}"
            )

        try:
            aio.run(_import())
        except ImportError_ as exc:
            parser.exit(2, f"Ошибка импорта: {exc}\n")
