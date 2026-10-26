"""Фото из сообщений MAX: ссылки из вложений, безопасная загрузка и сохранение в хранилище."""

import base64
import ipaddress
from typing import Any

import httpx
import structlog

from domovoy.core.config import get_settings
from domovoy.core.storage import save_bytes

log = structlog.get_logger(__name__)

MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_DRAFT_PHOTOS = 5


def image_urls(body: dict[str, Any]) -> list[str]:
    """Ссылки на фото из вложений сообщения MAX (в эмуляторе - data:-ссылки)."""
    out = []
    for att in body.get("attachments") or []:
        if att.get("type") == "image":
            url = (att.get("payload") or {}).get("url")
            if url:
                out.append(str(url))
    return out


def _allowed_url(url: str) -> bool:
    """Фото качаем только по https с публичного хоста: никаких localhost и адресов внутренней сети."""
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return False
    host = (parsed.host or "").lower()
    if parsed.scheme != "https" or not host or host == "localhost" or host.endswith((".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host  # доменное имя, не голый адрес


async def _download(url: str) -> bytes | None:
    try:
        if url.startswith("data:image/"):
            # data:-ссылки шлёт только эмулятор чата; от настоящего MAX их не принимаем
            if not get_settings().mock_max or len(url) > MAX_PHOTO_BYTES * 4 // 3 + 100:
                return None
            return base64.b64decode(url.split(",", 1)[1])
        if not _allowed_url(url):
            return None
        async with (
            httpx.AsyncClient(timeout=20, follow_redirects=False) as client,
            client.stream("GET", url) as resp,
        ):
            resp.raise_for_status()
            chunks, size = [], 0
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > MAX_PHOTO_BYTES:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
    except Exception:
        log.warning("chat.photo_download_failed", exc_info=True)
        return None


async def store_photos(urls: list[str], prefix: str) -> list[str]:
    keys = []
    for url in urls[:MAX_DRAFT_PHOTOS]:
        raw = await _download(url)
        if raw is None:
            continue
        try:
            keys.append(await save_bytes(prefix, raw))
        except Exception:
            # нечитаемое фото или недоступно хранилище: заявку всё равно можно подать без него
            log.warning("chat.photo_store_failed", exc_info=True)
    return keys
