# /// script
# requires-python = ">=3.12"
# dependencies = ["rembg[cpu]", "pillow", "numpy", "opencv-python-headless"]
# ///
"""Режет лист art/kuzya-sheet.png (3x2 позы Кузи) на слои для KuzyaMascot.

Для каждой позы: фон убирает нейросеть (rembg, модель bria-rmbg), затем тень на полу
и соседние обрезки отбрасываются, позы выравниваются по земле и центру валенок на общем
холсте. Слои: body (всё, кроме головы), head (копна и лицо, мягкий шов на вороте, крутится
вокруг шеи) и lids (закрытые веки для моргания, только позы с открытыми глазами).

Запуск из frontend/: uv run scripts/kuzya_sprites.py [--cache DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "art" / "kuzya-sheet.png"
OUT = ROOT / "src" / "components" / "kuzya" / "sprites"
META = ROOT / "src" / "components" / "kuzya" / "sprites.ts"
PUBLIC = ROOT / "public"

# Порядок поз на листе: слева направо, сверху вниз.
MOODS = ["ok", "happy", "proud", "sad", "alarm", "worried"]
# Моргают только позы, где оба глаза открыты и не перекрыты бровями.
BLINKING = {"ok", "sad", "worried"}
CELL = 512
PAD = 6
FEATHER = 22  # высота мягкого шва между головой и телом, px
LASH = (43, 26, 18)


def hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, s, v = cv2.split(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV))
    return h.astype(np.int32) * 2, s.astype(np.int32), v.astype(np.int32)


def cut_cells(cache: Path | None) -> list[np.ndarray]:
    sheet = Image.open(SHEET).convert("RGB")
    boxes = [(c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL) for r in range(2) for c in range(3)]
    cells: list[np.ndarray] = []
    session = None
    for mood, box in zip(MOODS, boxes, strict=True):
        cached = cache / f"{mood}.png" if cache else None
        if cached and cached.exists():
            cells.append(np.array(Image.open(cached).convert("RGBA")))
            continue
        from rembg import new_session, remove

        session = session or new_session("bria-rmbg")
        cut = remove(sheet.crop(box), session=session).convert("RGBA")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cut.save(cached)
        cells.append(np.array(cut))
    return cells


def red_mask(rgba: np.ndarray) -> np.ndarray:
    h, s, v = hsv(rgba[..., :3])
    return ((h < 15) | (h > 340)) & (s > 120) & (v > 120) & (rgba[..., 3] > 200)


def keep_main_blob(alpha: np.ndarray) -> np.ndarray:
    """Оставляет самый большой силуэт: обрезки соседних поз и искры уходят."""
    solid = cv2.dilate((alpha > 24).astype(np.uint8), np.ones((7, 7), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(solid)
    main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == main, alpha, 0).astype(np.uint8)


def fill_holes(mask: np.ndarray) -> np.ndarray:
    flood = mask.copy()
    ff = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), np.uint8)
    cv2.floodFill(flood, ff, (0, 0), 1)
    return mask | (1 - flood)


def drop_floor_shadow(rgba: np.ndarray, hem: int) -> np.ndarray:
    """Ниже подола оставляет только валенки: светлая тень на полу не нужна, её рисует CSS."""
    _, _, v = hsv(rgba[..., :3])
    core = ((v < 175) & (rgba[..., 3] > 128)).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # размыкание срезает тонкий контур тени на полу, сплошные валенки остаются
    core = cv2.morphologyEx(fill_holes(core), cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    core = cv2.dilate(core, np.ones((3, 3), np.uint8))
    out = rgba.copy()
    below = np.zeros_like(core, dtype=bool)
    below[hem + 3 :] = True
    out[..., 3] = np.where(below & (core == 0), 0, out[..., 3])
    return out


def clean(rgba: np.ndarray) -> tuple[np.ndarray, int]:
    rgba = rgba.copy()
    rgba[..., 3] = keep_main_blob(rgba[..., 3])
    red_rows = np.nonzero(red_mask(rgba).any(axis=1))[0]
    hem = int(red_rows.max())
    return drop_floor_shadow(rgba, hem), hem


def anchor(rgba: np.ndarray) -> tuple[int, int]:
    """Точка опоры позы: центр валенок по X и низ подошв по Y."""
    solid = rgba[..., 3] > 128
    bottom = int(np.nonzero(solid.any(axis=1))[0].max())
    ys, xs = np.nonzero(solid[bottom - 60 : bottom + 1])
    return int(round(xs.mean())), bottom


def collar_y(rgba: np.ndarray, cx: int) -> int:
    band = red_mask(rgba)[:, cx - 25 : cx + 26]
    return int(np.nonzero(band.any(axis=1))[0].min())


def eyes(rgba: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Радужки ищем по зелёному цвету: (cx, cy, w, h) двух самых крупных пятен."""
    h, s, v = hsv(rgba[..., :3])
    green = ((h > 90) & (h < 170) & (s > 90) & (v > 50) & (rgba[..., 3] > 200)).astype(np.uint8)
    n, _, stats, cent = cv2.connectedComponentsWithStats(green)
    found = sorted(
        (k for k in range(1, n) if stats[k, cv2.CC_STAT_AREA] > 300),
        key=lambda k: -stats[k, cv2.CC_STAT_AREA],
    )[:2]
    return sorted(
        (float(cent[k][0]), float(cent[k][1]), float(stats[k, 2]), float(stats[k, 3])) for k in found
    )


def skin_mask(rgba: np.ndarray) -> np.ndarray:
    h, s, v = hsv(rgba[..., :3])
    return (h > 8) & (h < 45) & (s > 45) & (s < 175) & (v > 130) & (rgba[..., 3] > 250)


def eye_mask(skin: np.ndarray, cx: float, cy: float, w: float, h: float) -> np.ndarray:
    """Весь глаз целиком (белок, радужка, обводка, ресницы): всё не-кожа, связанное с радужкой."""
    yy, xx = np.mgrid[: skin.shape[0], : skin.shape[1]]
    near = ((xx - cx) / (w * 1.15)) ** 2 + ((yy - cy) / (h * 0.95)) ** 2 <= 1
    _, labels = cv2.connectedComponents((near & ~skin).astype(np.uint8))
    eye = (labels == labels[int(cy), int(cx)]).astype(np.uint8)
    return cv2.dilate(fill_holes(eye), np.ones((5, 5), np.uint8))


def tapered_arc(draw: ImageDraw.ImageDraw, pts: np.ndarray, w_max: float, k: int) -> None:
    """Штрих кистью: толще в середине, сходит на нет к концам."""
    for i, (x, y) in enumerate(pts):
        r = (0.25 + 0.75 * np.sin(np.pi * i / (len(pts) - 1))) * w_max / 2 * k
        draw.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=(*LASH, 255))


def bezier(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float]) -> np.ndarray:
    t = np.linspace(0, 1, 80)[:, None]
    return (1 - t) ** 2 * np.array(p0) + 2 * (1 - t) * t * np.array(p1) + t**2 * np.array(p2)


def lids_layer(rgba: np.ndarray, found: list[tuple[float, float, float, float]]) -> np.ndarray:
    """Закрытые веки: глаз замазывается кожей по окружению (inpaint), сверху ресничная дуга ◡."""
    skin = skin_mask(rgba)
    tone = np.median(rgba[..., :3][skin], axis=0).astype(np.uint8)
    mask = np.zeros(skin.shape, np.uint8)
    for cx, cy, w, h in found:
        mask |= eye_mask(skin, cx, cy, w, h)
    # брови и пряди у края маски не должны затекать в заливку
    src = rgba[..., :3].copy()
    ring = (cv2.dilate(mask, np.ones((11, 11), np.uint8)) > 0) & (mask == 0) & ~skin
    src[ring] = tone
    filled = cv2.inpaint(src, mask, 6, cv2.INPAINT_TELEA)

    k = 4
    hgt, wid = mask.shape
    lashes = Image.new("RGBA", (wid * k, hgt * k), (0, 0, 0, 0))
    draw = ImageDraw.Draw(lashes)
    left_x = min(e[0] for e in found)
    for cx, cy, w, h in found:
        outer = -1 if cx == left_x else 1
        x0, x1 = cx - w * 0.72 + outer * w * 0.06, cx + w * 0.72 + outer * w * 0.06
        y0 = cy + h * 0.12
        tapered_arc(draw, bezier((x0, y0), (cx, cy + h * 0.62), (x1, y0)), h * 0.1, k)
        ex = x0 if outer < 0 else x1
        for dx, dy in ((0.3, -0.2), (0.16, -0.32)):
            tip = (ex + outer * w * dx, y0 + h * dy)
            tapered_arc(draw, bezier((ex, y0), ((ex + tip[0]) / 2, y0), tip), h * 0.07, k)

    alpha = cv2.GaussianBlur(mask * 255, (0, 0), 1.2)
    lids = Image.fromarray(np.dstack([filled, alpha]).astype(np.uint8))
    lids.alpha_composite(lashes.resize((wid, hgt), Image.LANCZOS))
    return np.array(lids)


def split_head(rgba: np.ndarray, collar: int) -> tuple[np.ndarray, np.ndarray]:
    """Голова поверх тела, в покое слои складываются ровно в исходник.

    Внутри силуэта тело остаётся непрозрачным и под головой: когда голова качается,
    из-под неё видна та же картинка, а не щель. На краях силуэта альфы дополняют друг
    друга, чтобы контур не становился толще.
    """
    ys = np.arange(rgba.shape[0], dtype=np.float32)
    w = np.clip((collar + 4 - ys) / FEATHER, 0, 1)[:, None]
    a = rgba[..., 3].astype(np.float32) / 255
    head_a = a * w
    inner = cv2.erode((rgba[..., 3] > 250).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    edge_a = np.where(head_a < 0.999, a * (1 - w) / np.maximum(1 - head_a, 1e-3), 0)
    body_a = np.where(inner, a, edge_a)
    head, body = rgba.copy(), rgba.copy()
    head[..., 3] = np.round(head_a * 255).astype(np.uint8)
    body[..., 3] = np.round(np.clip(body_a, 0, 1) * 255).astype(np.uint8)
    return head, body


def place(pose: dict, size: tuple[int, int], at: tuple[int, int]) -> np.ndarray:
    """Переносит позу на общий холст так, чтобы её опора попала в точку `at`."""
    x0, y0, x1, y1 = pose["box"]
    crop = pose["rgba"][y0 : y1 + 1, x0 : x1 + 1]
    canvas = np.zeros((size[1], size[0], 4), np.uint8)
    dx, dy = at[0] - (pose["ax"] - x0), at[1] - (pose["ay"] - y0)
    canvas[dy : dy + crop.shape[0], dx : dx + crop.shape[1]] = crop
    return canvas


def save_webp(arr: np.ndarray, path: Path) -> None:
    Image.fromarray(arr).save(path, "WEBP", quality=86, alpha_quality=92, method=6)


def export_public(ok_full: np.ndarray, ok_head_box: tuple[int, int, int, int]) -> None:
    """Логотип (кузя.png во весь рост), голова для favicon и шапки, круглый аватар бота."""
    Image.fromarray(ok_full).save(PUBLIC / "kuzya.png", optimize=True)
    x0, y0, x1, y1 = ok_head_box
    side = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    head = Image.fromarray(ok_full).crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2))
    head.resize((192, 192), Image.LANCZOS).save(PUBLIC / "kuzya-head.png", optimize=True)

    avatar = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(avatar).ellipse([0, 0, 511, 511], fill=(228, 237, 248, 255))
    bust = head.resize((560, 560), Image.LANCZOS)
    avatar.alpha_composite(bust, (-24, 10))
    circle = Image.new("L", (512 * 4, 512 * 4), 0)
    ImageDraw.Draw(circle).ellipse([0, 0, 512 * 4 - 1, 512 * 4 - 1], fill=255)
    avatar.putalpha(Image.fromarray(np.minimum(np.array(avatar)[..., 3], np.array(circle.resize((512, 512), Image.LANCZOS)))))
    avatar.resize((256, 256), Image.LANCZOS).save(PUBLIC / "kuzya-avatar.png", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, help="папка для вырезанных поз, чтобы не гонять нейросеть заново")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    poses = []
    for mood, raw in zip(MOODS, cut_cells(args.cache), strict=True):
        rgba, _ = clean(raw)
        ax, ay = anchor(rgba)
        ys, xs = np.nonzero(rgba[..., 3] > 8)
        poses.append({"mood": mood, "rgba": rgba, "ax": ax, "ay": ay, "box": (xs.min(), ys.min(), xs.max(), ys.max())})

    half = max(max(p["ax"] - p["box"][0], p["box"][2] - p["ax"]) for p in poses) + PAD
    above = max(p["ay"] - p["box"][1] for p in poses) + PAD
    size = (2 * half, above + PAD)
    ground = (half, above)

    OUT.mkdir(parents=True, exist_ok=True)
    meta: dict[str, dict] = {}
    for p in poses:
        full = place(p, size, ground)
        collar = collar_y(full, half)
        head, body = split_head(full, collar)
        save_webp(body, OUT / f"{p['mood']}-body.webp")
        save_webp(head, OUT / f"{p['mood']}-head.webp")
        found = eyes(full)
        blink = p["mood"] in BLINKING and len(found) == 2
        if blink:
            save_webp(lids_layer(full, found), OUT / f"{p['mood']}-lids.webp")
        meta[p["mood"]] = {"neck": [int(half), int(collar)], "blink": blink}
        if p["mood"] == "ok":
            hy = np.nonzero((head[..., 3] > 128).any(axis=1))[0]
            hx = np.nonzero((head[..., 3] > 128).any(axis=0))[0]
            export_public(full, (int(hx.min()), int(hy.min()), int(hx.max()), int(collar + 30)))

    write_meta(size, ground[1], meta)
    print(f"холст {size[0]}x{size[1]}, земля {ground[1]}; слои в {OUT.relative_to(ROOT)}")


def write_meta(size: tuple[int, int], ground: int, meta: dict[str, dict]) -> None:
    rows = "\n".join(
        f"  {mood}: {{ neck: [{m['neck'][0]}, {m['neck'][1]}], blink: {str(m['blink']).lower()} }},"
        for mood, m in meta.items()
    )
    META.write_text(
        "// Сгенерировано scripts/kuzya_sprites.py из art/kuzya-sheet.png, руками не править.\n"
        "import type { KuzyaMood } from './mood'\n\n"
        f"export const CANVAS = {{ width: {size[0]}, height: {size[1]}, ground: {ground} }} as const\n\n"
        "export interface PoseMeta {\n"
        "  /** Точка шеи на холсте: вокруг неё качается голова. */\n"
        "  neck: [number, number]\n"
        "  /** Есть слой закрытых век. */\n"
        "  blink: boolean\n"
        "}\n\n"
        f"export const POSES: Record<KuzyaMood, PoseMeta> = {{\n{rows}\n}}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
