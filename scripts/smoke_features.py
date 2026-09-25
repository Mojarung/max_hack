"""Сквозная проверка новых функций: дома, объявления, чат, обращение на тестовый e-mail, документы, профили.

Стенд в мок-режиме должен быть запущен (docker compose up -d). Запуск:
    uv run --project backend python scripts/smoke_features.py [http://localhost:8000] [http://localhost:8025]
Второй адрес - Mailpit, куда приходят тестовые письма с обращениями.
"""

import asyncio
import io
import sys
import uuid

import httpx
from PIL import Image

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000") + "/api/v1"
MAILPIT = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8025"
fails = 0
RUN = uuid.uuid4().hex[:6]  # метка прогона: скрипт можно запускать повторно


def check(name, ok, extra=""):
    global fails
    print(("OK  " if ok else "FAIL"), name, extra if not ok else "")
    fails += 0 if ok else 1


def H(u, house=None):
    h = {"X-Dev-User": str(u)}
    if house:
        h["X-House-Id"] = str(house)
    return h


def jpeg():
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 50, 50)).save(b, "JPEG")
    return b.getvalue()


async def wait_chat(c, chat_id, pred, timeout=20):
    for _ in range(timeout * 2):
        msgs = (await c.get("/dev/chat/messages", params={"chat_id": chat_id})).json()
        hit = [m for m in msgs if pred(m)]
        if hit:
            return hit[-1]
        await asyncio.sleep(0.5)
    return None


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        # 1. дома и переключение
        houses = (await c.get("/houses", headers=H(1001))).json()
        check("у Анны два дома", len(houses) == 2, houses)
        first = next(h for h in houses if h["title"].startswith("Дом 7"))["id"]
        second = next(h for h in houses if h["title"].startswith("Дом 9"))["id"]
        me = (await c.get("/me", headers=H(1001, second))).json()
        check("переключение на второй дом", me["house"]["id"] == second)
        me2 = (await c.get("/me", headers=H(1001))).json()
        check("активный дом запомнился без заголовка", me2["house"]["id"] == second, me2["house"]["title"])
        r = await c.get("/me", headers=H(1003, second))
        check("чужой дом недоступен (403)", r.status_code == 403)
        # личка с ботом видит тот же активный дом
        await c.post("/dev/chat/send", json={"chat_id": 1001, "user_id": 1001, "text": "Как дела у дома?"})
        m = await wait_chat(c, 1001, lambda m: m["from"] is None and "Здоровье дома" in m["text"])
        check("бот в личке ответил", m is not None)
        await c.get("/me", headers=H(1001, first))  # вернуть Анну в первый дом

        # 2. объявление упоминанием бота в чате
        me = (await c.get("/me", headers=H(1002))).json()
        bot = me["bot_username"]
        await c.post(
            "/dev/chat/send",
            json={
                "chat_id": -100,
                "user_id": 1001,
                "text": f"@{bot} сделай объявление о субботнике в субботу в 11 у площадки",
            },
        )
        m = await wait_chat(c, -100, lambda m: m["from"] is None and "Объявление «Субботник" in m["text"])
        check("Кузя ответил на @упоминание и сделал объявление", m is not None)
        ann = (await c.get("/announcements", headers=H(1002))).json()
        sub = [a for a in ann if a["title"] == "Субботник во дворе"]
        check("объявление на доске, связано с событием", bool(sub) and sub[0]["event_id"], ann[:1])
        await c.post(
            "/dev/chat/send",
            json={
                "chat_id": -100,
                "user_id": 1002,
                "text": f"@{bot} напиши всем объявление что завтра отключат свет в 1 подъезде",
            },
        )
        m = await wait_chat(
            c, -100, lambda m: m["from"] is None and m["text"].startswith("📢 **Объявление: Завтра отключат свет")
        )
        check("свободное объявление опубликовано в чате", m is not None)
        ann = (
            await c.post(
                "/announcements",
                headers=H(1002),
                json={"title": "Потерялся кот", "text": "Рыжий, отзывается на Барсик"},
            )
        ).json()
        check("объявление из приложения", ann.get("id") and ann["pinned"] is False, ann)
        r = await c.patch(f"/announcements/{ann['id']}", headers=H(1002), json={"pinned": True})
        check("житель не может закрепить (403)", r.status_code == 403)

        # 3. подсказка на жалобу без обращения к Кузе
        await c.post(
            "/dev/chat/send",
            json={"chat_id": -100, "user_id": 1004, "text": "у нас опять не работает лифт в 3 подъезде"},
        )
        m = await wait_chat(c, -100, lambda m: m["from"] is None and "Похоже" in m["text"])
        check("Кузя сам откликнулся на жалобу", m is not None)

        # 4. заявка с фото -> чат с фото -> голоса из приложения обновляют сообщение -> e-mail
        files = [("photos", ("p.jpg", jpeg(), "image/jpeg"))]
        issue = (
            await c.post(
                "/issues",
                headers=H(1005),
                data={"description": f"Сломан домофон в подъезде {RUN}, дверь не закрывается"},
                files=files,
            )
        ).json()
        iid = issue["id"]
        m = await wait_chat(c, -100, lambda m: m["from"] is None and issue["title"] in m["text"] and m.get("photos"))
        check("сообщение заявки в чате с фото", m is not None)
        mid = m["id"] if m else None
        voters = [1001, 1002, 1003, 1004, 1006, 1007, 1008]
        for u in voters[: issue["votes_needed"] - 2]:
            r = await c.post(f"/issues/{iid}/vote", headers=H(u))
        await asyncio.sleep(2)
        m = await wait_chat(c, -100, lambda m: m["id"] == mid)
        need = issue["votes_needed"]
        check(
            "счётчик в чате обновился после голосов из приложения",
            m and f"{need - 1} из {need}" in m["text"] and m.get("photos"),
            m and m["text"][-120:],
        )
        # последний голос - кнопкой в чате
        await c.post(
            "/dev/chat/callback",
            json={"chat_id": -100, "user_id": voters[need - 2], "message_id": mid, "payload": f"vote:{iid}"},
        )
        m = await wait_chat(c, -100, lambda m: m["id"] == mid and "Голоса собраны" in m["text"])
        check("голос из чата: порог набран, сообщение обновлено, фото на месте", m is not None and m.get("photos"))
        for _ in range(30):
            d = (await c.get(f"/issues/{iid}", headers=H(1005))).json()
            if d.get("appeal_channel"):
                break
            await asyncio.sleep(0.5)
        check(
            "обращение ушло на тестовый e-mail",
            (d.get("appeal_channel") or "").startswith("test_email:"),
            d.get("appeal_channel"),
        )
        async with httpx.AsyncClient() as mp:
            mails = (await mp.get(f"{MAILPIT}/api/v1/messages")).json()
        hit = [x for x in mails.get("messages", []) if f"№ {iid}" in x["Subject"]]
        check(
            "письмо в Mailpit с пометкой [ТЕСТ] и фото",
            bool(hit) and hit[0]["Subject"].startswith("[ТЕСТ]") and hit[0]["Attachments"] >= 1,
            hit[:1],
        )
        m = await wait_chat(
            c, -100, lambda m: m["from"] is None and "модельная интеграция" in m["text"] and issue["title"] in m["text"]
        )
        check("в чате сказано про модельную интеграцию", m is not None)

        # 5. барахолка: закрытые не пропадают
        mine = (
            await c.post(
                "/listings", headers=H(1003), data={"title": f"Табуретка {RUN}", "price": "0", "category": "furniture"}
            )
        ).json()
        await c.patch(f"/listings/{mine['id']}", headers=H(1003), json={"status": "closed"})
        active = [x["id"] for x in (await c.get("/listings", headers=H(1003))).json()]
        mine_all = [x["id"] for x in (await c.get("/listings", headers=H(1003), params={"scope": "mine"})).json()]
        closed = [x["id"] for x in (await c.get("/listings", headers=H(1002), params={"scope": "closed"})).json()]
        check(
            "закрытое ушло из активных, но есть в «Мои» и «Завершённые»",
            mine["id"] not in active and mine["id"] in mine_all and mine["id"] in closed,
        )

        # 6. документы
        r = await c.post(
            "/documents",
            headers=H(1003),
            data={"title": "Паспорт квартиры", "scope": "personal"},
            files={"file": ("pass.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        pdoc = r.json()
        check("личный документ загружен", r.status_code == 201, r.text)
        docs2 = (await c.get("/documents", headers=H(1002))).json()
        check("чужой личный документ не виден", all(d["id"] != pdoc["id"] for d in docs2))
        r = await c.get(f"/documents/{pdoc['id']}/link", headers=H(1002))
        check("чужой документ: ссылку не дают (404)", r.status_code == 404)
        link = (await c.get(f"/documents/{pdoc['id']}/link", headers=H(1003))).json()
        async with httpx.AsyncClient(base_url=BASE.removesuffix("/api/v1")) as raw:
            f = await raw.get(link["url"])
            bad = await raw.get(link["url"].replace("sig=", "sig=0"))
        check(
            "скачивание по подписанной ссылке",
            f.status_code == 200 and f.content.startswith(b"%PDF") and bad.status_code == 403,
        )
        r = await c.post(
            "/documents",
            headers=H(1002),
            data={"title": "Протокол", "scope": "house"},
            files={"file": ("p.pdf", b"%PDF-1.4 x", "application/pdf")},
        )
        check("житель не загружает документы дома (403)", r.status_code == 403)
        r = await c.post(
            "/documents",
            headers=H(1001),
            data={"title": "Протокол собрания", "scope": "house"},
            files={"file": ("p.pdf", b"%PDF-1.4 x", "application/pdf")},
        )
        docs2 = (await c.get("/documents", headers=H(1002), params={"scope": "house"})).json()
        check(
            "документ дома виден всем", r.status_code == 201 and any(d["title"] == "Протокол собрания" for d in docs2)
        )

        # 7. профили
        people = (await c.get("/people", headers=H(1002))).json()
        check("список соседей", len(people) >= 8)
        prof = (await c.get(f"/people/{people[0]['id']}", headers=H(1002))).json()
        check("профиль соседа со статистикой", "stats" in prof and prof["user"]["id"] == people[0]["id"], prof)

        # 8. редактор дома
        r = await c.patch("/house", headers=H(1002), json={"info": "взлом"})
        check("житель не меняет дом (403)", r.status_code == 403)
        r = await c.patch(
            "/house",
            headers=H(1001),
            json={"uk_name": "УК «Новый дом»", "uk_email": "uk@example.org", "info": "Диспетчер 24/7"},
        )
        h = r.json()["house"]
        check(
            "админ задал УК и информацию",
            h["uk_name"] == "УК «Новый дом»" and h["uk_email"] == "uk@example.org" and h["info"] == "Диспетчер 24/7",
            h,
        )
        h2 = (await c.get("/me", headers=H(1001, second))).json()["house"]
        check("общая демо-УК второго дома не изменилась", h2["uk_name"] != "УК «Новый дом»", h2["uk_name"])

        # 9. обучалка
        me = (await c.post("/me/onboarded", headers=H(1008))).json()
        check("обучалка пройдена", me["user"]["onboarded"] is True)
    print("\nВсе проверки пройдены" if not fails else f"\nПровалено проверок: {fails}")
    sys.exit(1 if fails else 0)


asyncio.run(main())
