"""Кадры бота в чате: настоящий бот на Docker-стенде через эмулятор в стиле MAX."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DECK = Path(__file__).resolve().parents[1]
OUT = str(DECK / "shots")
PHOTO = str(DECK.parents[1] / "frontend" / "public" / "demo" / "stairs-dark.jpg")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8180"


def settle(pg, ms=3500):
    pg.wait_for_timeout(ms)
    pg.evaluate("document.querySelectorAll('[data-sonner-toast]').forEach(e => e.remove())")
    pg.evaluate("(() => { const c = document.querySelector('.max-chat'); if (c) c.scrollTop = c.scrollHeight })()")
    pg.wait_for_timeout(600)


def send(pg, text):
    pg.get_by_placeholder("Сообщение").fill(text)
    pg.keyboard.press("Enter")


def pick_chat(pg, subtitle):
    pg.get_by_role("button", name="Меню эмулятора: выбрать чат и жителя").click()
    pg.wait_for_timeout(500)
    pg.get_by_text(subtitle).first.click()
    pg.wait_for_timeout(1500)
    pg.keyboard.press("Escape")
    # кольцо фокуса на «⋮» после закрытия меню на снимке не нужно
    pg.evaluate("document.activeElement && document.activeElement.blur()")
    pg.wait_for_timeout(300)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True)
    pg.goto(f"{BASE}/dev/chat", wait_until="networkidle"); pg.wait_for_timeout(1500)
    pick_chat(pg, "личные сообщения с ботом")
    send(pg, "/меню"); settle(pg); pg.screenshot(path=f"{OUT}/bot_menu.png"); print("bot_menu")
    pg.get_by_role("button", name="Сообщить о проблеме").last.click(); settle(pg, 2500)
    pg.locator("input[type=file]").last.set_input_files(PHOTO); pg.wait_for_timeout(1500)
    send(pg, "На 5 этаже третьего подъезда не горит свет, вечером на лестнице темно"); settle(pg, 6000)
    pg.screenshot(path=f"{OUT}/bot_confirm.png"); print("bot_confirm")
    pg.get_by_role("button", name="Отправить соседям").last.click(); settle(pg, 5000)
    pg.screenshot(path=f"{OUT}/bot_sent.png"); print("bot_sent")
    send(pg, "/проблемы"); settle(pg)
    pg.screenshot(path=f"{OUT}/bot_list.png"); print("bot_list")
    send(pg, "/укрытия"); settle(pg, 6000)
    pg.screenshot(path=f"{OUT}/bot_shelters.png"); print("bot_shelters")
    pick_chat(pg, "Чат: Дом 7 на Демонстрационной"); settle(pg, 2500)
    pg.screenshot(path=f"{OUT}/bot_group.png"); print("bot_group")
    b.close()
