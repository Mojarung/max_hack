"""Минимальный асинхронный клиент MAX Bot API (https://dev.max.ru/docs-api).

Токен передаётся только заголовком `Authorization: <token>` (query-параметр больше не поддерживается).
"""

import asyncio
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

RETRIES = 3
MEMBER_PAGES_LIMIT = 50
ATTACHMENT_RETRIES = 5
UPDATE_TYPES = [
    "message_created",
    "message_callback",
    "bot_started",
    "bot_added",
    "bot_removed",
    "user_added",
    "user_removed",
]


class MaxApiError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"MAX API {status}: {body[:300]}")
        self.status = status


class MaxClient:
    def __init__(self, base_url: str, token: str, poll_timeout: int = 30) -> None:
        self._poll_timeout = poll_timeout
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": token},
            timeout=httpx.Timeout(10.0, read=poll_timeout + 15),
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(RETRIES):
            try:
                resp = await self._http.request(method, path, **kwargs)
            except httpx.TransportError:
                if attempt == RETRIES - 1:
                    raise
                await asyncio.sleep(1 + attempt)
                continue
            if resp.status_code == 429 and attempt < RETRIES - 1:
                # лимит MAX: 2 сообщения в секунду на чат
                await asyncio.sleep(1 + attempt)
                continue
            if resp.status_code >= 400:
                raise MaxApiError(resp.status_code, resp.text)
            return resp.json() if resp.content else {}
        raise MaxApiError(429, "rate limited")

    async def me(self) -> dict[str, Any]:
        return await self._request("GET", "/me")

    async def get_updates(self, marker: int | None) -> tuple[list[dict[str, Any]], int | None]:
        params: dict[str, Any] = {"timeout": self._poll_timeout, "limit": 100, "types": ",".join(UPDATE_TYPES)}
        if marker is not None:
            params["marker"] = marker
        data = await self._request("GET", "/updates", params=params)
        return data.get("updates", []), data.get("marker", marker)

    async def send_message(
        self,
        *,
        text: str,
        chat_id: int | None = None,
        user_id: int | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> str | None:
        params = {"chat_id": chat_id} if chat_id is not None else {"user_id": user_id}
        body: dict[str, Any] = {"text": text[:4000], "format": "markdown"}
        if attachments:
            body["attachments"] = attachments
        for attempt in range(ATTACHMENT_RETRIES):
            try:
                data = await self._request("POST", "/messages", params=params, json=body)
                break
            except MaxApiError as exc:
                # только что загруженное фото MAX ещё обрабатывает: ждём и повторяем
                if "attachment.not.ready" not in str(exc) or attempt == ATTACHMENT_RETRIES - 1:
                    raise
                await asyncio.sleep(1 + attempt)
        return (data.get("message") or {}).get("body", {}).get("mid")

    async def edit_message(self, mid: str, text: str, attachments: list[dict[str, Any]] | None) -> None:
        body: dict[str, Any] = {"text": text[:4000], "format": "markdown", "attachments": attachments or []}
        await self._request("PUT", "/messages", params={"message_id": mid}, json=body)

    async def delete_message(self, mid: str) -> None:
        await self._request("DELETE", "/messages", params={"message_id": mid})

    async def answer_callback(self, callback_id: str, notification: str) -> None:
        await self._request(
            "POST", "/answers", params={"callback_id": callback_id}, json={"notification": notification}
        )

    async def get_chat(self, chat_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/chats/{chat_id}")

    async def get_message(self, mid: str) -> dict[str, Any]:
        return await self._request("GET", f"/messages/{mid}")

    async def chat_members(self, chat_id: int, user_ids: list[int] | None = None) -> list[dict[str, Any]]:
        """Участники чата. С user_ids MAX возвращает только этих людей (пусто, если их нет в чате).

        Без user_ids листаем все страницы. Боту нужны права администратора чата.
        """
        if user_ids:
            data = await self._request(
                "GET", f"/chats/{chat_id}/members", params={"user_ids": ",".join(map(str, user_ids))}
            )
            return list(data.get("members") or [])
        members: list[dict[str, Any]] = []
        marker: int | None = None
        for _ in range(MEMBER_PAGES_LIMIT):
            params: dict[str, Any] = {"count": 100}
            if marker is not None:
                params["marker"] = marker
            data = await self._request("GET", f"/chats/{chat_id}/members", params=params)
            members.extend(data.get("members") or [])
            marker = data.get("marker")
            if not marker:
                break
        return members

    async def chat_admins(self, chat_id: int) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/chats/{chat_id}/members/admins")
        return list(data.get("members") or [])

    async def my_membership(self, chat_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/chats/{chat_id}/members/me")

    async def pin_message(self, chat_id: int, mid: str) -> None:
        await self._request("PUT", f"/chats/{chat_id}/pin", json={"message_id": mid, "notify": True})

    async def upload_image(self, data: bytes, filename: str = "photo.jpg") -> dict[str, Any]:
        """Загружает фото и возвращает payload вложения `image` ({"photos": ...} или {"token": ...})."""
        slot = await self._request("POST", "/uploads", params={"type": "image"})
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
            resp = await http.post(slot["url"], files={"data": (filename, data, "image/jpeg")})
        if resp.status_code >= 400:
            raise MaxApiError(resp.status_code, resp.text)
        body = resp.json() if resp.content else {}
        if body.get("photos"):
            return {"photos": body["photos"]}
        token = body.get("token") or slot.get("token")
        if not token:
            raise MaxApiError(500, f"upload without token: {str(body)[:200]}")
        return {"token": token}
