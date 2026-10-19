"""Режет лист готовых аватарок 3×3 (art/avatars-sheet.jpg) на public/avatars/1..9.webp.

Белый фон вокруг каждого шарика убирается заливкой от краёв ячейки: пушистая кромка остаётся,
а углы становятся прозрачными. Нумерация слева направо, сверху вниз.

    uv run --with pillow scripts/avatars.py [путь к листу]
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SHEET = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "art" / "avatars-sheet.jpg"
OUT = ROOT / "public" / "avatars"
GRID = 3
SIZE = 256  # px: в интерфейсе аватар не больше 96px, с запасом на экраны @3x
WHITE = 236  # всё светлее по всем каналам считаем фоном
PAD = 1.06  # поле вокруг шарика внутри квадрата
# Насколько пиксель должен отличаться от белого, чтобы считаться полностью непрозрачным
EDGE_SOFTNESS = 70


def background_mask(cell: Image.Image) -> Image.Image:
    """Маска фона: светлые пиксели, связанные с краем ячейки."""
    rgb = cell.convert("RGB")
    r, g, b = rgb.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    light = darkest.point(lambda v: 255 if v >= WHITE else 0)
    # заливка от краёв: светлое внутри шарика (блик, белый глаз) фоном не становится
    marked = light.copy()
    w, h = marked.size
    for x in range(0, w, 8):
        for y in (0, h - 1):
            if marked.getpixel((x, y)) == 255:
                ImageDraw.floodfill(marked, (x, y), 128)
    for y in range(0, h, 8):
        for x in (0, w - 1):
            if marked.getpixel((x, y)) == 255:
                ImageDraw.floodfill(marked, (x, y), 128)
    return marked.point(lambda v: 255 if v == 128 else 0)


def cut(cell: Image.Image) -> Image.Image:
    bg = background_mask(cell)
    fg = ImageChops.invert(bg)
    box = fg.getbbox() or (0, 0, *cell.size)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    half = max(box[2] - box[0], box[3] - box[1]) * PAD / 2
    square = (round(cx - half), round(cy - half), round(cx + half), round(cy + half))
    rgb = cell.convert("RGB").crop(square)
    # область шарика с запасом в пару пикселей: пушистая кромка лежит как раз на границе заливки
    region = fg.crop(square).filter(ImageFilter.MaxFilter(5))
    return unmix_white(rgb, region).resize((SIZE, SIZE), Image.LANCZOS)


def unmix_white(rgb: Image.Image, region: Image.Image) -> Image.Image:
    """Отделяет шерсть от белого фона: прозрачность по «белизне» пикселя и чистый цвет без примеси белого.

    Пиксель кромки = a * цвет + (1 - a) * белый. Насколько он светлее самого тёмного канала, настолько в нём
    белого; цвет восстанавливаем обратно, поэтому на тёмной теме нет светлого ореола.
    """
    out = Image.new("RGBA", rgb.size)
    src, reg, dst = rgb.load(), region.load(), out.load()
    assert src is not None and reg is not None and dst is not None
    w, h = rgb.size
    for y in range(h):
        for x in range(w):
            if not reg[x, y]:
                continue
            r, g, b = src[x, y]
            a = min(1.0, (255 - min(r, g, b)) / EDGE_SOFTNESS)
            if a <= 0.02:
                continue
            un = [max(0, min(255, round((c - (1 - a) * 255) / a))) for c in (r, g, b)]
            dst[x, y] = (un[0], un[1], un[2], round(a * 255))
    return out


def main() -> None:
    sheet = Image.open(SHEET)
    w, h = sheet.size
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for row in range(GRID):
        for col in range(GRID):
            n += 1
            cell = sheet.crop((col * w // GRID, row * h // GRID, (col + 1) * w // GRID, (row + 1) * h // GRID))
            cut(cell).save(OUT / f"{n}.webp", "WEBP", quality=88, method=6)
    print(f"{n} аватарок -> {OUT}")


if __name__ == "__main__":
    main()
