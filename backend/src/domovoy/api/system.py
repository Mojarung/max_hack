"""Системные эндпоинты: медиа из MinIO, SSE-поток, проверка здоровья."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent

from domovoy.api.deps import resolve_ctx
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.core.realtime import hub
from domovoy.core.storage import read_object

router = APIRouter()

# Ключи, которые кладёт save_bytes: папка, у фото из чата и аватарок ещё номер дома или жителя
KEY_RE = re.compile(r"^(issues|listings|events|avatars|demo)(/\d{1,10})?/[0-9a-f]{32}\.jpg$")
PING_SECONDS = 15


class AppMeta(BaseModel):
    bot_username: str
    mock: bool


@router.get("/meta", response_model=AppMeta, tags=["Служебное"])
async def meta() -> AppMeta:
    """Без авторизации: по нему мини-приложение вне MAX решает, дать демо-жителей или позвать в MAX."""
    s = get_settings()
    return AppMeta(bot_username=s.max_bot_username, mock=s.mock_max)


@router.get("/media/{key:path}", tags=["Медиа"])
async def media(key: str) -> Response:
    if not KEY_RE.match(key):
        raise HTTPException(404, "Файл не найден")
    try:
        data = await read_object(key)
    except Exception as exc:
        raise HTTPException(404, "Файл не найден") from exc
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/realtime/stream", tags=["Реалтайм"])
async def stream(
    request: Request,
    init_data: Annotated[str | None, Query()] = None,
    dev_user: Annotated[int | None, Query()] = None,
    house_id: Annotated[int | None, Query()] = None,
) -> EventSourceResponse:
    # Сессию БД закрываем сразу после авторизации: SSE-поток живёт долго и не должен держать соединение.
    async with get_sessionmaker()() as session:
        ctx = await resolve_ctx(session, init_data, dev_user, house_id)
    house = ctx.house.id

    async def events() -> AsyncIterator[ServerSentEvent]:
        with hub.subscribe(house) as queue:
            yield ServerSentEvent(event="ready", data=json.dumps({"house_id": house}))
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=PING_SECONDS)
                except TimeoutError:
                    yield ServerSentEvent(event="ping", data="{}")
                    continue
                yield ServerSentEvent(event=msg["event"], data=json.dumps(msg["data"], ensure_ascii=False))

    return EventSourceResponse(events(), headers={"X-Accel-Buffering": "no"})
