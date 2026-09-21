"""FastAPI-приложение: REST API мини-приложения, SSE и эмулятор чата."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from faststream.rabbit import RabbitQueue

from domovoy.agent.runtime import close_runtime
from domovoy.api.system import router as system_router
from domovoy.core.bus import EXCHANGE, get_broker
from domovoy.core.config import get_settings
from domovoy.core.db import init_db
from domovoy.core.realtime import hub
from domovoy.core.storage import ensure_bucket
from domovoy.modules.achievements.router import router as achievements_router
from domovoy.modules.assistant.router import router as assistant_router
from domovoy.modules.devchat.router import router as devchat_router
from domovoy.modules.events.router import router as events_router
from domovoy.modules.issues.router import router as issues_router
from domovoy.modules.market.router import router as market_router
from domovoy.modules.safety.router import router as safety_router
from domovoy.modules.search.router import router as search_router
from domovoy.modules.users.router import router as users_router
from domovoy.seed import seed_demo

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await init_db()
    await ensure_bucket()
    if settings.seed_demo:
        await seed_demo()

    broker = get_broker()
    # у каждого экземпляра API своя временная очередь: все экземпляры получают все rt-события
    rt_queue = RabbitQueue(f"rt.api.{uuid.uuid4().hex[:8]}", auto_delete=True, exclusive=True, routing_key="rt.#")

    @broker.subscriber(rt_queue, EXCHANGE)
    async def on_realtime(msg: dict[str, Any]) -> None:
        hub.dispatch(msg)

    await broker.start()
    log.info("api.started", mock=settings.mock_max, llm=settings.llm_provider)
    try:
        yield
    finally:
        await broker.stop()
        await close_runtime()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Домовой Кузя API",
        version="1.0.0",
        description=(
            "REST API мини-приложения MAX «Домовой Кузя»: проблемы дома, барахолка, события, ачивки, безопасность."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api = APIRouter(prefix="/api/v1")
    for router in (
        users_router,
        issues_router,
        market_router,
        events_router,
        achievements_router,
        safety_router,
        search_router,
        assistant_router,
        devchat_router,
        system_router,
    ):
        api.include_router(router)

    @api.get("/health", tags=["Служебное"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api)
    return app
