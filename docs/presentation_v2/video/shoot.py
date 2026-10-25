"""Экраны для ролика: одна заявка «течёт крыша» проходит весь путь на поднятом стенде (docker compose up).

Бот в эмуляторе принимает фото и текст, соседи 1002-1007 голосуют, обращение уходит, экран срока
снимается с той же заявки в мини-приложении. Кадры кладутся в video/assets/shots.
Стенд после съёмки возвращают из дампа: создаются заявка и сообщения чата.

Запуск из корня репозитория:
    uv run --with playwright --with httpx python docs/presentation_v2/video/shoot.py
"""

import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "shots"
PHOTO = HERE.parents[2] / "frontend" / "public" / "demo" / "roof-drip.jpg"
APP = "http://localhost:8180"
API = "http://localhost:8000/api/v1"
GROUP = -100
TEXT = "Течёт крыша над 9 этажом во втором подъезде, вода капает на лестницу"


def settle(pg, ms=3500):
    pg.wait_for_timeout(ms)
    pg.evaluate("document.querySelectorAll('[data-sonner-toast]').forEach(e => e.remove())")
    pg.evaluate("(() => { const c = document.querySelector('.max-chat'); if (c) c.scrollTop = c.scrollHeight })()")
    pg.wait_for_timeout(600)


def pick_chat(pg, subtitle):
    pg.get_by_role("button", name="Меню эмулятора: выбрать чат и жителя").click()
    pg.wait_for_timeout(500)
    pg.get_by_text(subtitle).first.click()
    pg.wait_for_timeout(1500)
    pg.keyboard.press("Escape")
    pg.evaluate("document.activeElement && document.activeElement.blur()")
    pg.wait_for_timeout(300)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True)
        pg.goto(f"{APP}/dev/chat", wait_until="networkidle")
        pg.wait_for_timeout(1500)
        pick_chat(pg, "личные сообщения с ботом")
        pg.get_by_placeholder("Сообщение").fill("/меню"); pg.keyboard.press("Enter"); settle(pg)
        pg.get_by_role("button", name="Сообщить о проблеме").last.click(); settle(pg, 2500)
        pg.locator("input[type=file]").last.set_input_files(str(PHOTO)); pg.wait_for_timeout(1500)
        pg.get_by_placeholder("Сообщение").fill(TEXT); pg.keyboard.press("Enter"); settle(pg, 6000)
        pg.screenshot(path=str(OUT / "bot_confirm.png")); print("bot_confirm")
        pg.get_by_role("button", name="Отправить соседям").last.click(); settle(pg, 5000)
        pick_chat(pg, "Чат: Дом 7 на Демонстрационной"); settle(pg, 2500)
        pg.screenshot(path=str(OUT / "bot_group.png")); print("bot_group")

        with httpx.Client(timeout=30) as c:
            msgs = c.get(f"{API}/dev/chat/messages", params={"chat_id": GROUP}).json()
            post = next(m for m in reversed(msgs) if "vote:" in json.dumps(m.get("buttons"), ensure_ascii=False))
            payload = next(b["payload"] for row in post["buttons"] for b in row if str(b.get("payload", "")).startswith("vote:"))
            issue_id = int(payload.split(":")[1])
            for voter in range(1002, 1008):
                c.post(f"{API}/dev/chat/callback", json={"chat_id": GROUP, "user_id": voter, "message_id": post["id"], "payload": payload})
                time.sleep(0.8)
        time.sleep(5)
        app = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True)
        app.goto(f"{APP}/issues/{issue_id}", wait_until="networkidle")
        app.wait_for_timeout(2500)
        app.evaluate("document.querySelectorAll('[data-sonner-toast]').forEach(e => e.remove())")
        # переключатель демо-жителя есть только вне MAX: житель его не видит
        app.evaluate("document.querySelectorAll('.demo-switch').forEach(e => e.remove())")
        app.locator(".sla").evaluate("e => window.scrollTo(0, e.getBoundingClientRect().top + scrollY - 330)")
        app.wait_for_timeout(800)
        app.screenshot(path=str(OUT / "issue_sla.png")); print("issue_sla", issue_id)
        b.close()


if __name__ == "__main__":
    main()
