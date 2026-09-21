"""Системные эндпоинты: медиа из MinIO, SSE-поток, проверка здоровья."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sse_starlette import EventSourceResponse, ServerSentEvent

from domovoy.api.deps import resolve_ctx
from domovoy.core.db import get_sessionmaker
from domovoy.core.realtime import hub
from domovoy.core.storage import read_object

router = APIRouter()

KEY_RE = re.compile(r"^(issues|listings)/[0-9a-f]{32}\.jpg$")
PING_SECONDS = 15


@router.get("/media/{key:path}", tags=["Медиа"])
async def media(key: str) -> Response:
    if not KEY_RE.match(key):
        raise HTTPException(404, "Файл не найден")
    try:
        data = await read_object(key)
    except Exception as exc:
        raise HTTPException(404, "Файл не найден") from exc
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})


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
