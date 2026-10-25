"""Скриншоты нового интерфейса для презентации v2 (мок-режим, 390x844 @2x)."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5174"
DECK = Path(__file__).resolve().parents[1]
OUT = str(DECK / "shots")
PHOTO = str(DECK.parents[1] / "frontend" / "public" / "demo" / "seedlings-2.jpg")
only = set(sys.argv[1:])


def page(b, theme="light"):
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=theme, has_touch=True, is_mobile=True)
    return pg


def go(pg, path, extra="", theme="light", wait=1300):
    sep = "&" if "?" in path else "?"
    pg.goto(f"{BASE}{path}{sep}reset=1&motion=0&theme={theme}{extra}", wait_until="networkidle")
    pg.wait_for_timeout(wait)


def snap(pg, name):
    pg.screenshot(path=f"{OUT}/{name}.png")
    print("ok", name)


def want(name):
    return not only or name in only


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = page(b)
    if want("home"):
        go(pg, "/"); snap(pg, "home")
    if want("issues"):
        go(pg, "/issues"); snap(pg, "issues")
    if want("new_issue"):
        go(pg, "/issues/new")
        pg.locator("textarea").first.fill("На 9 этаже во втором подъезде течёт крыша, вода капает на лестницу")
        pg.wait_for_timeout(2500); snap(pg, "new_issue")
    if want("issue_vote"):
        go(pg, "/issues/101"); snap(pg, "issue_vote")
    if want("issue_sla"):
        go(pg, "/issues/103")
        pg.locator(".sla").evaluate("e => window.scrollTo(0, e.getBoundingClientRect().top + scrollY - 330)")
        pg.wait_for_timeout(600); snap(pg, "issue_sla")
    if want("market"):
        go(pg, "/market"); snap(pg, "market")
    if want("listing"):
        go(pg, "/market/202"); snap(pg, "listing")
    if want("events"):
        go(pg, "/events"); snap(pg, "events")
    if want("event"):
        go(pg, "/events/new")
        pg.get_by_label("Название").fill("Высадим рассаду у подъезда")
        pg.get_by_label("Место").fill("Клумба у 2 подъезда")
        pg.get_by_label("Подробности").fill("Рассаду томатов и бархатцев принесёт Мария из 23 кв. Возьмите перчатки, лейки даёт УК.")
        pg.locator("input[type=file]").last.set_input_files(PHOTO); pg.wait_for_timeout(1200)
        pg.get_by_role("button", name="Создать событие").click(); pg.wait_for_timeout(2500)
        pg.evaluate("document.querySelectorAll('[data-sonner-toast]').forEach(e => e.remove())"); pg.evaluate("window.scrollTo(0,0)"); pg.wait_for_timeout(300); snap(pg, "event")
    if want("achievements"):
        go(pg, "/more/achievements"); snap(pg, "achievements")
    if want("people"):
        go(pg, "/people"); snap(pg, "people")
    if want("avatars"):
        go(pg, "/more")
        me = pg.locator("a[href^='/people/']").first.get_attribute("href")
        go(pg, me); pg.get_by_text("Сменить аватарку").first.click(); pg.wait_for_timeout(1200); snap(pg, "avatars")
    if want("safety"):
        go(pg, "/more/safety?shelter=1", wait=3500); snap(pg, "safety")
    if want("assistant"):
        go(pg, "/more/assistant"); snap(pg, "assistant")
    if want("more"):
        go(pg, "/more"); snap(pg, "more")
    if want("alert"):
        go(pg, "/", extra="&scenario=alert", wait=2000); snap(pg, "alert")
    pg.close()
    d = page(b, "dark")
    if want("home_dark"):
        go(d, "/", theme="dark"); snap(d, "home_dark")
    if want("market_dark"):
        go(d, "/market", theme="dark"); snap(d, "market_dark")
    b.close()
