"""Сквозная проверка Кузи в чате через эмулятор MAX: всё основное без мини-приложения.

Запуск на поднятом стенде (docker compose up): uv run --project backend python scripts/smoke_bot.py [http://localhost:8000]

Проходит меню, заявку с фото из лички и из чата дома, голос, порог и обращение, смену статуса,
списки заявок, событий и вещей, выбор дома. Как и smoke.py, оставляет в демо-базе созданные записи.
"""

import base64
import io
import json
import sys
import time

import httpx
from PIL import Image

API = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000") + "/api/v1/dev"
DM = 1001  # Анна, администратор демо-дома, личка
GROUP = -100  # чат «Дом 7 на Демонстрационной»
# в консоли Windows ответы бота с эмодзи иначе роняют печать
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
c = httpx.Client(timeout=30)
failures: list[str] = []


def msgs(chat: int) -> list[dict]:
    return c.get(f"{API}/chat/messages", params={"chat_id": chat}).json()


def last_bot(chat: int, after: int) -> list[dict]:
    return [
        m for m in msgs(chat)[after:] if m.get("from_bot") or m.get("is_bot") or m.get("from_name") in ("Кузя", None)
    ]


def wait_new(chat: int, before: int, timeout: float = 15, seen: list[dict] | None = None) -> list[dict]:
    """Новые ответы бота, а если передан seen, то и сообщения, которые бот изменил на месте."""
    old = {m["id"]: (m.get("text"), m.get("buttons")) for m in seen or []}

    def fresh(ms: list[dict]) -> list[dict]:
        edited = [
            m
            for m in ms[:before]
            if is_bot(m)
            and not m.get("deleted")
            and m["id"] in old
            and old[m["id"]] != (m.get("text"), m.get("buttons"))
        ]
        return edited + [m for m in ms[before:] if is_bot(m)]

    end = time.time() + timeout
    while time.time() < end:
        if fresh(msgs(chat)):
            time.sleep(0.6)
            return fresh(msgs(chat))
        time.sleep(0.4)
    return []


def is_bot(m: dict) -> bool:
    return m.get("from") is None


def buttons(m: dict) -> list[dict]:
    rows = m.get("buttons") or []
    return [b for row in rows for b in row]


def show(title: str, ms: list[dict]) -> None:
    print(f"\n=== {title} ===")
    for m in ms:
        print((m.get("text") or "")[:600])
        for b in buttons(m):
            print("   [", b.get("text"), "->", b.get("payload") or b.get("url"), "]")


def send(chat: int, user: int, text: str = "", photos: list[str] | None = None) -> list[dict]:
    before = len(msgs(chat))
    r = c.post(
        f"{API}/chat/send",
        json={"chat_id": chat, "user_id": user, "text": text, "photos": photos or []},
    )
    r.raise_for_status()
    return wait_new(chat, before)


def press(chat: int, user: int, message: dict, payload: str, expect_new: bool = True) -> list[dict]:
    seen = msgs(chat)
    before = len(seen)
    r = c.post(
        f"{API}/chat/callback",
        json={
            "chat_id": chat,
            "user_id": user,
            "message_id": message["id"],
            "payload": payload,
        },
    )
    r.raise_for_status()
    if expect_new:
        # меню, списки и карточки бот меняет на месте, остальное приходит новым сообщением
        return wait_new(chat, before, seen=seen)
    time.sleep(2)
    return [m for m in msgs(chat) if m.get("id") == message["id"]]


def find(ms: list[dict], payload_prefix: str) -> tuple[dict, str] | None:
    for m in ms:
        for b in buttons(m):
            if str(b.get("payload") or "").startswith(payload_prefix):
                return m, b["payload"]
    return None


def check(cond: bool, what: str) -> None:
    print(("OK   " if cond else "FAIL ") + what)
    if not cond:
        failures.append(what)


def photo_data_url() -> str:
    img = Image.new("RGB", (320, 240), (90, 120, 160))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def reset_active_house() -> None:
    """Анна в первом демо-доме: smoke_features.py пишет от её имени в чат второго дома,
    а бот после этого считает её «живущей» там, и заявка ушла бы не в тот чат."""
    base = API.removesuffix("/dev")
    houses = c.get(f"{base}/houses", headers={"X-Dev-User": str(DM)}).json()
    first_house = next(h["id"] for h in houses if h["title"].startswith("Дом 7"))
    c.get(f"{base}/me", headers={"X-Dev-User": str(DM), "X-House-Id": str(first_house)})


reset_active_house()
first = msgs(DM)
print("message keys:", list(first[-1].keys()) if first else "none")

ms = send(DM, DM, "/меню")
show("/меню", ms)
check(bool(find(ms, "menu:report")), "меню в личке на кнопках")

menu_msg = ms[-1]
ms = press(DM, DM, menu_msg, "menu:report")
show("Сообщить о проблеме", ms)
check(
    any("что случилось" in (m.get("text") or "").lower() for m in ms),
    "бот просит описание",
)

ms = send(DM, DM, "В подвале второго подъезда течёт кран, вода на полу", [photo_data_url()])
show("Описание + фото", ms)
check(
    any("Проверьте заявку" in (m.get("text") or "") for m in ms),
    "карточка подтверждения",
)
check(any("Фото: 1" in (m.get("text") or "") for m in ms), "фото принято")
hit = find(ms, "report:send")
check(hit is not None, "кнопка отправки")
ms = press(DM, DM, hit[0], "report:send")
show("Отправить", ms)
card_btn = find(ms, "issue:")
check(card_btn is not None, "заявка создана, есть карточка")
issue_id = int(card_btn[1].split(":")[1])

ms = press(DM, DM, card_btn[0], card_btn[1])
show("Карточка заявки", ms)
check(any(f"№{issue_id}" in (m.get("text") or "") for m in ms), "карточка открылась")

group = msgs(GROUP)
post = next(
    (m for m in reversed(group) if f"vote:{issue_id}" in json.dumps(m.get("buttons"), ensure_ascii=False)),
    None,
)
check(post is not None, "заявка опубликована в чате дома с голосованием")
for voter in (1002, 1003, 1004, 1005, 1006, 1007):
    if post is None:
        break
    c.post(
        f"{API}/chat/callback",
        json={
            "chat_id": GROUP,
            "user_id": voter,
            "message_id": post["id"],
            "payload": f"vote:{issue_id}",
        },
    )
    time.sleep(0.8)
time.sleep(4)
ms = press(DM, DM, card_btn[0], card_btn[1])
show("Карточка после голосования", ms)
check(
    any("Отправлено" in (m.get("text") or "") or "📨" in (m.get("text") or "") for m in ms),
    "порог набран, обращение отправлено",
)
appeal = find(ms, "appeal:")
check(appeal is not None, "кнопка текста обращения")
if appeal:
    ms2 = press(DM, DM, appeal[0], appeal[1])
    show("Текст обращения", ms2)
    check(
        any("обращени" in (m.get("text") or "").lower() for m in ms2),
        "текст обращения пришёл",
    )
status = find(ms, "status:")
check(status is not None, "кнопки смены статуса у автора")
if status:
    edited = press(DM, DM, status[0], f"status:{issue_id}:resolved", expect_new=False)
    show("Решено", edited)
    check(
        any("Решено" in (m.get("text") or "") for m in edited),
        "статус «Решено» в карточке",
    )

ms = send(DM, DM, "Кузя, создай субботник в субботу в 11 у площадки")
show("Создать событие текстом", ms)

for payload, title, marker in (
    ("menu:issues", "Заявки дома", "Заявки дома"),
    ("menu:mine", "Мои заявки", "Мои заявки"),
    ("menu:events", "События", "события"),
    ("menu:market", "Вещи", "Вещи соседей"),
    ("menu:shelters", "Укрытия", "укрытия"),
    ("menu:profile", "Профиль", "Уровень"),
    ("menu:houses", "Дома", "дом"),
):
    ms = press(DM, DM, menu_msg, payload)
    show(title, ms)
    check(
        any(marker.lower() in (m.get("text") or "").lower() for m in ms),
        f"{title}: ответ в чате",
    )
    if payload == "menu:events":
        j = find(ms, "join:") or find(ms, "leave:")
        if j:
            edited = press(DM, DM, j[0], j[1], expect_new=False)
            show("Иду / отменить", edited)
            check(bool(edited), "запись на событие из списка")
    if payload == "menu:market":
        lst = find(ms, "listing:")
        if lst:
            ms3 = press(DM, DM, lst[0], lst[1])
            show("Объявление", ms3)
            ct = find(ms3, "contact:")
            if ct:
                press(DM, DM, ct[0], ct[1], expect_new=False)
                check(True, "написать продавцу")
        check(
            any("Показано:" in (m.get("text") or "") for m in ms),
            "в списке видно, сколько из скольких",
        )
        sell = find(ms, "sell:start")
        check(sell is not None, "вещь размещается прямо в боте")
        if sell:
            press(DM, DM, sell[0], sell[1])
            card = send(DM, DM, "Детская коляска, почти новая, 3000 ₽", [photo_data_url()])
            show("Карточка объявления", card)
            hit = find(card, "sell:send")
            check(hit is not None, "карточка объявления с кнопкой «Разместить»")
            if hit:
                done = press(DM, DM, hit[0], "sell:send")
                show("Объявление размещено", done)
                check(
                    any("размещено" in (m.get("text") or "") for m in done),
                    "объявление размещено из чата",
                )
    if payload == "menu:houses":
        h = find(ms, "house:")
        if h:
            ms4 = press(DM, DM, h[0], h[1])
            show("Выбор дома", ms4)
            check(
                any("ваш дом" in (m.get("text") or "").lower() for m in ms4),
                "выбор дома в личке",
            )
            # возвращаем первый демо-дом: smoke.py ждёт, что Анна живёт в нём
            press(DM, DM, h[0], "house:1", expect_new=False)

ms = send(DM, DM, "поддерживаю заявку 999999")
show("Голос текстом (несуществующая)", ms)

# заявка в общем чате дома: меню чата, кнопка, описание с обращением к Кузе
ms = send(GROUP, 1003, "/меню")
show("Меню в чате дома", ms)
check(
    bool(find(ms, "menu:report")) and not find(ms, "menu:houses"),
    "короткое меню в чате дома",
)
ms = press(GROUP, 1003, ms[-1], "menu:report")
show("Сообщить в чате дома", ms)
ms = send(GROUP, 1003, "Кузя, на 5 этаже третьего подъезда не горит свет")
show("Описание в чате дома", ms)
check(
    any("Проверьте заявку" in (m.get("text") or "") for m in ms),
    "карточка подтверждения в чате дома",
)
check(
    any("Электричество" in (m.get("text") or "") for m in ms),
    "категория: электричество, а не подъезд",
)
hit = find(ms, "report:send")
if hit:
    ms = press(GROUP, 1003, hit[0], "report:send")
    show("Отправить из чата дома", ms)
    check(
        any("опубликована" in (m.get("text") or "") for m in ms),
        "заявка из чата дома создана",
    )

print("\nFAILURES:", failures or "none")
sys.exit(1 if failures else 0)
