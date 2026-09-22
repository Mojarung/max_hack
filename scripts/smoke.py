"""Сквозная проверка основного сценария на запущенном стенде (docker compose up).

Запуск: uv run --project backend python scripts/smoke.py [http://localhost:8000]

Проходит путь жителя: заявка с фото → голоса соседей → порог → обращение от воркера;
плюс модерация комментариев, событие через агента в эмуляторе чата, тревога и укрытия.
"""

import asyncio
import io
import sys
import time

import httpx
from PIL import Image

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000") + "/api/v1"
CHAT_ID = -100
WAIT_SECONDS = 20


def headers(user: int) -> dict[str, str]:
    return {"X-Dev-User": str(user)}


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (200, 120, 60)).save(buf, "JPEG")
    return buf.getvalue()


def check(cond: bool, message: str) -> None:
    print(("OK   " if cond else "FAIL ") + message)
    if not cond:
        raise SystemExit(1)


async def wait_for(predicate, what: str) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if await predicate():
            check(True, what)
            return
        await asyncio.sleep(1)
    check(False, what)


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        me = (await c.get("/me", headers=headers(1001))).json()
        check(me["mock"] and me["house"]["id"] == 1, "профиль и дом в мок-режиме")
        foreign = await c.get("/issues", headers={**headers(1001), "X-House-Id": "999"})
        check(foreign.status_code == 403, "чужой дом через X-House-Id недоступен")

        r = await c.post(
            "/issues",
            headers=headers(1005),
            data={"description": "В подвале прорвало трубу, вода по щиколотку", "location_hint": "подвал, 2 подъезд"},
            files=[("photos", ("pipe.jpg", jpeg(), "image/jpeg"))],
        )
        check(r.status_code == 201, f"заявка с фото создана ({r.status_code})")
        issue = r.json()
        check(issue["category"] == "water" and issue["responsible_org"] is not None, "классификация и ответственный")
        photo = await c.get(issue["photos"][0].removeprefix("/api/v1"))
        check(photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg", "фото отдаётся из MinIO")

        dup = (await c.post("/issues/similar", headers=headers(1006), json={"text": "труба прорвала в подвале"})).json()
        check(any(d["id"] == issue["id"] for d in dup), "поиск дублей находит заявку")

        for user in range(1001, 1009):
            if user == 1005:
                continue
            r = await c.post(f"/issues/{issue['id']}/vote", headers=headers(user))
            if r.json().get("status") == "sent":
                break
        detail = r.json()
        check(detail["status"] == "sent" and detail["deadline_at"], "порог голосов набран, заявка отправлена")

        async def appeal_ready() -> bool:
            d = (await c.get(f"/issues/{issue['id']}", headers=headers(1005))).json()
            return bool(d.get("appeal_text"))

        await wait_for(appeal_ready, "воркер сформировал официальное обращение")

        events = (await c.get("/events", headers=headers(1002))).json()
        bad = await c.post(f"/events/{events[0]['id']}/comments", headers=headers(1002), json={"text": "Ты дурак, блин"})
        check(bad.status_code == 422, "модерация отклонила грубый комментарий")
        ok = await c.post(f"/events/{events[0]['id']}/comments", headers=headers(1002), json={"text": "Приду с граблями"})
        check(ok.status_code == 201, "вежливый комментарий опубликован")

        before = len((await c.get("/events", headers=headers(1003))).json())
        await c.post("/dev/chat/send", json={"chat_id": CHAT_ID, "user_id": 1003, "text": "Кузя, создай субботник в воскресенье в 12 у площадки"})

        async def event_created() -> bool:
            return len((await c.get("/events", headers=headers(1003))).json()) > before

        await wait_for(event_created, "агент в чате создал событие")

        await c.post("/dev/chat/send", json={"chat_id": CHAT_ID, "user_id": 1004, "text": "Заработок от 100000 в день, пиши в личку t.me/xxx"})

        async def spam_deleted() -> bool:
            msgs = (await c.get("/dev/chat/messages", params={"chat_id": CHAT_ID})).json()
            return any(m["deleted"] for m in msgs)

        await wait_for(spam_deleted, "бот удалил спам в чате")

        chat = (await c.post("/assistant/chat", headers=headers(1001), json={"message": "Где ближайшее укрытие?"})).json()
        check("nearest_shelters" in chat["tools_used"], "ассистент вызвал инструмент укрытий")

        alert = (await c.post("/alerts", headers=headers(1001), json={"kind": "drone"})).json()
        active = (await c.get("/alerts/active", headers=headers(1002))).json()
        check(active and active["id"] == alert["id"], "тревога активна")
        shelters = (await c.get("/shelters", headers=headers(1002))).json()
        check(shelters[0]["yandex_url"].startswith("https://yandex.ru/maps/?rtext="), "маршрут до укрытия в Яндекс Картах")
        await c.post(f"/alerts/{alert['id']}/end", headers=headers(1001))
        check((await c.get("/alerts/active", headers=headers(1002))).json() is None, "отбой тревоги")

        ach = (await c.get("/achievements", headers=headers(1005))).json()
        check(any(a["code"] == "first_issue" and a["earned"] for a in ach["items"]), "ачивка «Зоркий глаз» выдана")
    print("\nВсе проверки пройдены")


if __name__ == "__main__":
    asyncio.run(main())
