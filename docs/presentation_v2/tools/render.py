"""Рендер презентации v2: PNG каждого слайда для проверки и PDF для сдачи.

Запуск: uv run --with playwright --with pymupdf python docs/presentation_v2/tools/render.py [номера слайдов для PNG]
"""
import sys
import tempfile
from pathlib import Path

import pymupdf
from playwright.sync_api import sync_playwright

TOOLS = Path(__file__).resolve().parent
SRC = TOOLS.parent / "slides.html"
PDF = TOOLS.parents[2] / "Презентация_Домовой_Кузя_v2.pdf"
# PNG каждого слайда для проверки глазами; папка в .gitignore
OUT = TOOLS / "out"
OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.goto(SRC.as_uri(), wait_until="networkidle"); pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(800)
    slides = pg.locator("section.slide")
    n = slides.count()
    # переполнение: содержимое ячейки или слайда вылезло за край
    over = pg.evaluate("""() => [...document.querySelectorAll('section.slide')].map((s, i) => {
      const bad = [...s.querySelectorAll('.c, .bento, h2, table, p, ul')].filter(e => !e.closest('.c[style*=\"padding: 0\"]') && (e.scrollHeight > e.clientHeight + 2 || e.scrollWidth > e.clientWidth + 2) && getComputedStyle(e).overflow !== 'visible');
      const sr = s.getBoundingClientRect();
      const out = [...s.querySelectorAll('h2, p, li, td, svg, .num')].filter(e => { const r = e.getBoundingClientRect(); return r.bottom > sr.bottom - 8 || r.right > sr.right - 8; });
      return { i: i + 1, clipped: bad.length, out: out.slice(0, 3).map(e => e.tagName + ':' + (e.textContent || '').trim().slice(0, 40)) };
    }).filter(x => x.clipped || x.out.length)""")
    print("slides:", n); print("overflow:", over)
    for i in range(n):
        if len(sys.argv) > 1 and str(i + 1) not in sys.argv[1:]:
            continue
        slides.nth(i).screenshot(path=str(OUT / f"s{i + 1:02d}.png"))
    # Печатаем каждый слайд отдельно и склеиваем страницы. Весь документ разом Chrome печатает
    # с ошибкой: из 19 скриншотов 390x844 @2x часть выходит чёрными прямоугольниками.
    merged = pymupdf.open()
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            pg.evaluate("""(k) => { document.querySelectorAll('section.slide').forEach((s, j) => { s.style.display = j === k ? '' : 'none' }); document.body.style.counterReset = 'slide ' + k }""", i)
            pg.evaluate("""async () => { await Promise.all([...document.images].filter(i => i.offsetParent).map(i => i.decode().catch(() => {}))) }""")
            part = Path(tmp) / f"{i:02d}.pdf"
            pg.pdf(path=str(part), width="1280px", height="720px", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            with pymupdf.open(str(part)) as one:
                merged.insert_pdf(one, from_page=0, to_page=0)
    merged.save(str(PDF), garbage=4, deflate=True)
    print("pdf", PDF.stat().st_size // 1024, "KB")
    b.close()
