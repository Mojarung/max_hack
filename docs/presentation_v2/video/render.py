"""Сборка ролика «Домовой Кузя»: 2560x1440, 60 кадров в секунду, звук по меткам из index.html.

Каждый кадр снимается отдельно (таймлайн GSAP перематывается на время кадра), поэтому движение ровное
и не зависит от скорости компьютера. Нужны Chrome и ffmpeg в PATH.

Запуск из корня репозитория:
    uv run --with playwright python docs/presentation_v2/video/render.py [--seconds N]
"""

import argparse
import contextlib
import functools
import http.server
import json
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = HERE.parents[2] / "Ролик_Домовой_Кузя.mp4"
SILENT = HERE / "build" / "video_silent.mp4"
FPS = 60
SCALE = 2  # 1280x720 -> 2560x1440
MUSIC_VOL = 0.5
REPO = HERE.parents[2]
# Chrome с видеокартой: 3D-модель телефона рисует WebGL
CHROME_ARGS = ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"]


@contextlib.contextmanager
def serve_repo() -> Iterator[str]:
    """Локальный HTTP-сервер: со страницы file:// скриншоты нельзя отдать в WebGL как текстуры."""
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(REPO))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/docs/presentation_v2/video/index.html"
    finally:
        server.shutdown()


def open_page(p, url: str):
    browser = p.chromium.launch(channel="chrome", args=CHROME_ARGS)
    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=SCALE)
    page.goto(url, wait_until="networkidle")
    page.wait_for_function("window.READY === true", timeout=120_000)
    return browser, page


def render_video(seconds: float | None) -> tuple[float, list[dict]]:
    SILENT.parent.mkdir(exist_ok=True)
    with serve_repo() as url, sync_playwright() as p:
        browser, page = open_page(p, url)
        duration = seconds or page.evaluate("window.DUR")
        cues = page.evaluate("window.CUES")
        frames = round(duration * FPS)
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
             "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", "-profile:v", "high",
             "-r", str(FPS), "-movflags", "+faststart", str(SILENT)],
            stdin=subprocess.PIPE,
        )
        assert ffmpeg.stdin is not None
        started = time.time()
        for i in range(frames):
            page.evaluate(f"window.__frame({i / FPS})")
            ffmpeg.stdin.write(page.screenshot(type="jpeg", quality=96))
            if i % 120 == 0:
                print(f"кадр {i}/{frames}, {time.time() - started:.0f} с", flush=True)
        ffmpeg.stdin.close()
        if ffmpeg.wait() != 0:
            raise SystemExit("ffmpeg не собрал видео")
        browser.close()
    return duration, cues


def mux_audio(duration: float, cues: list[dict]) -> None:
    cues = [c for c in cues if c["t"] < duration]
    inputs = ["-i", str(SILENT), "-i", str(ASSETS / "music_positive_weekend.mp3")]
    parts = [
        f"[1:a]atrim=0:{duration},asetpts=N/SR/TB,afade=t=in:d=0.05,"
        f"afade=t=out:st={max(0, duration - 1.6):.2f}:d=1.6,volume={MUSIC_VOL}[m]"
    ]
    labels = ["[m]"]
    for k, cue in enumerate(cues):
        inputs += ["-i", str(ASSETS / f"{cue['name']}.mp3")]
        ms = int(cue["t"] * 1000)
        parts.append(f"[{k + 2}:a]adelay={ms}|{ms},volume={cue['vol']}[s{k}]")
        labels.append(f"[s{k}]")
    parts.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=first,"
        "alimiter=limit=0.89,aresample=48000[a]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(parts),
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
         "-t", f"{duration}", "-movflags", "+faststart", str(OUT)],
        check=True,
    )


def preview(times: list[float]) -> None:
    """Отдельные кадры в build/ для проверки глазами: --preview 1.5 9.6 ..."""
    with serve_repo() as url, sync_playwright() as p:
        browser, page = open_page(p, url)
        for t in times:
            page.evaluate(f"window.__frame({t})")
            page.screenshot(path=str(HERE / "build" / f"frame_{t:05.2f}.png"))
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, help="собрать только начало ролика, для проверки")
    parser.add_argument("--preview", type=float, nargs="+", help="снять только эти кадры в build/")
    args = parser.parse_args()
    (HERE / "build").mkdir(exist_ok=True)
    if args.preview:
        preview(args.preview)
        return
    duration, cues = render_video(args.seconds)
    (HERE / "build" / "cues.json").write_text(json.dumps(cues, ensure_ascii=False, indent=1), encoding="utf-8")
    mux_audio(duration, cues)
    print("готово:", OUT, OUT.stat().st_size // 1024 // 1024, "МБ")


if __name__ == "__main__":
    main()
