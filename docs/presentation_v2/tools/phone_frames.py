"""Рамка телефона вокруг скриншотов в slides.html.

Каждый <img class="shot"> оборачивается в <figure class="phone">: корпус, строка статуса
с «9:41» и Dynamic Island. Цвет строки статуса берётся из верхнего края самого скриншота,
поэтому после пересъёмки экранов скрипт запускают ещё раз: он обновит цвета, не трогая разметку.

Запуск: uv run --with pillow python docs/presentation_v2/tools/phone_frames.py
"""

import re
from pathlib import Path

from PIL import Image

DECK = Path(__file__).resolve().parents[1]
HTML = DECK / "slides.html"
SHOTS = DECK / "shots"

STATUS_ICONS = (
    '<svg class="phone__status" viewBox="0 0 72 14" width="72" height="14" fill="currentColor" aria-hidden="true">'
    '<rect x="0" y="9" width="3" height="5" rx="1"/><rect x="5" y="6.5" width="3" height="7.5" rx="1"/>'
    '<rect x="10" y="4" width="3" height="10" rx="1"/><rect x="15" y="1.5" width="3" height="12.5" rx="1"/>'
    '<path d="M24 5.2a9 9 0 0 1 12 0l-1.5 1.6a6.8 6.8 0 0 0-9 0zM26.6 8a5.3 5.3 0 0 1 6.8 0l-1.5 1.6a3.2 3.2 0 0 0-3.8 0z'
    'M29.3 10.8a1.6 1.6 0 0 1 1.4 0L30 12.4z"/>'
    '<rect x="43" y="1.5" width="24" height="11" rx="3.5" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".5"/>'
    '<rect x="45" y="3.5" width="18" height="7" rx="2"/><rect x="68.3" y="5" width="2" height="4" rx="1" opacity=".5"/></svg>'
)

IMG_RE = re.compile(r'<img class="shot" src="shots/([^"]+)" alt="([^"]*)" style="([^"]*)">')
FIG_RE = re.compile(r'(<figure class="phone" data-shot="([^"]+)" style=")([^"]*)(")')


def bar_colors(name: str) -> tuple[str, str]:
    """Цвет верхнего края скриншота и цвет текста строки статуса под него."""
    path = SHOTS / name
    if not path.exists():
        return "#F5F7FB", "#1B2533"
    r, g, b = Image.open(path).convert("RGB").getpixel((6, 6))
    light = 0.2126 * r + 0.7152 * g + 0.0722 * b >= 128
    return f"#{r:02X}{g:02X}{b:02X}", "#1B2533" if light else "#FFFFFF"


def strip_bar_vars(style: str) -> str:
    parts = [p.strip() for p in style.split(";") if p.strip() and not p.strip().startswith(("--bar", "--ink"))]
    return ";".join(parts)


def figure(name: str, alt: str, style: str) -> str:
    bar, ink = bar_colors(name)
    style = strip_bar_vars(style)
    style = f"{style};--bar:{bar};--ink:{ink}" if style else f"--bar:{bar};--ink:{ink}"
    return (
        f'<figure class="phone" data-shot="{name}" style="{style}"><span class="phone__body">'
        f'<span class="phone__bar"><b>9:41</b><i class="phone__island"></i>{STATUS_ICONS}</span>'
        f'<img src="shots/{name}" alt="{alt}"></span></figure>'
    )


# старая разметка без .phone__body: корпус переносим во внутренний элемент
OLD_FIG_RE = re.compile(r'(<figure class="phone"[^>]*>)(<span class="phone__bar">.*?<img [^>]*>)</figure>')


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    html, wrapped = IMG_RE.subn(lambda m: figure(m.group(1), m.group(2), m.group(3)), html)
    html = OLD_FIG_RE.sub(lambda m: f'{m.group(1)}<span class="phone__body">{m.group(2)}</span></figure>', html)

    def refresh(m: re.Match[str]) -> str:
        bar, ink = bar_colors(m.group(2))
        return f"{m.group(1)}{strip_bar_vars(m.group(3))};--bar:{bar};--ink:{ink}{m.group(4)}"

    html, refreshed = FIG_RE.subn(refresh, html)
    HTML.write_text(html, encoding="utf-8")
    print(f"обёрнуто: {wrapped}, обновлено цветов: {refreshed}")


if __name__ == "__main__":
    main()
