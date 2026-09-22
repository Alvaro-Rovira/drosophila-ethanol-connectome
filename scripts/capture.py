"""Playwright captures (BRIEF 4.3/4.4): screenshots at 390 and 1280 px and per-stage GIFs.

Needs a running server: MOSCA_DEBUG=1 ./scripts/serve_local.sh   (GIFs need debug mode)
  uv run python scripts/capture.py screens [--base URL] [--prefix local]
  uv run python scripts/capture.py gifs
"""
from __future__ import annotations

import argparse
import base64
import io
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENS = ROOT / "artifacts" / "screens"
GIFS = ROOT / "artifacts" / "gifs"
FRAMES = ROOT / "artifacts" / "frames"
STAGES = [  # name, query, action. The level is frozen; everything else comes from the neurons.
    ("basal", "debug_a=0&seed=11&debug_puddles=1", None),
    ("estimulacion", "debug_a=0.45&seed=12&debug_puddles=1", None),
    ("hipotonia", "debug_a=0.66&seed=13&debug_puddles=1", None),
    ("caida", "debug_a=0.72&seed=22&debug_puddles=1", None),
    ("lorr", "debug_a=0.9&seed=15", None),
    ("estimulo-mecanico", "debug_a=0&seed=16", "tap"),
    # 3D view of the bar (same simulation, drawn in WebGL)
    ("barra-3d", "debug_a=0&seed=11&debug_puddles=1", "3d"),
    ("barra-3d-caida", "debug_a=0.72&seed=22&debug_puddles=1", "3d"),
]


def local_token():
    line = (ROOT / "tmp" / "local-secrets" / "tokens.yaml").read_text().splitlines()[0]
    return line.split(":", 1)[1].strip()


def login(page, base, token):
    page.goto(f"{base}/?k={token}")
    page.wait_for_function("window.__mosca && window.__mosca.frames() > 20", timeout=20000)


def launch(p, base):
    """Pin DNS for trycloudflare hosts through 1.1.1.1 (a fresh tunnel may be cached as NXDOMAIN locally)."""
    import subprocess
    host = base.split("//", 1)[1].split("/")[0]
    args = []
    if host.endswith("trycloudflare.com"):
        ips = [l for l in subprocess.run(["dig", "+short", "@1.1.1.1", host], capture_output=True, text=True).stdout.split() if l[:1].isdigit()]
        if ips:
            args = [f"--host-resolver-rules=MAP {host} {ips[0]}"]
    return p.chromium.launch(args=args)


def screens(base, token, prefix, wait_s=6.0):
    SCREENS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = launch(p, base)
        for w, h, dpr in ((390, 844, 2), (1280, 900, 1)):
            ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, is_mobile=w < 700, bypass_csp=True)
            page = ctx.new_page()
            login(page, base, token)
            time.sleep(wait_s)
            page.screenshot(path=str(SCREENS / f"{prefix}-{w}.png"), full_page=True)
            ctx.close()
        b.close()
    print("screens ->", SCREENS)


def console(base, token, wait_s=150.0):
    """The whole console at 1440 px while the automatic protocol runs (README image)."""
    SCREENS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 1010}, device_scale_factor=1, bypass_csp=True)
        page = ctx.new_page()
        login(page, base, token)
        page.goto(f"{base}/?seed=7")             # a fresh, naive subject (debug mode)
        page.wait_for_function("window.__mosca && window.__mosca.frames() > 45", timeout=20000)
        page.click("#demo")
        time.sleep(wait_s)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)
        page.screenshot(path=str(SCREENS / "consola.png"))
        page.click("#demo")
        ctx.close()
        b.close()
    print("consola ->", SCREENS / "consola.png")


def grab(page, sel="#table"):
    url = page.evaluate(f"document.querySelector('{sel}').toDataURL('image/png')")
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")


def save_gif(frames, path, fps, colors=96):
    """Global adaptive palette, no dithering: much smaller files with the noisy wood texture."""
    sample = Image.new("RGB", (frames[0].width, frames[0].height * 4))
    for i, k in enumerate(np.linspace(0, len(frames) - 1, 4).astype(int)):
        sample.paste(frames[k], (0, i * frames[0].height))
    pal = sample.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=int(1000 / fps), loop=0, optimize=True, disposal=1)


def gifs(base, token, fps=12, seconds=10, only=None):
    GIFS.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        # narrow viewport: the client enlarges the fly and the text on small canvases (more legible GIFs)
        ctx = b.new_context(viewport={"width": 520, "height": 900}, device_scale_factor=1.25, bypass_csp=True)
        page = ctx.new_page()
        login(page, base, token)
        for name, q, action in STAGES:
            if only and name not in only:
                continue
            page.goto(f"{base}/?{q}")
            page.wait_for_function("window.__mosca && window.__mosca.frames() > 45", timeout=20000)
            sel = "#scene" if action == "3d" else "#table"
            page.evaluate(f"window.__mosca.setView('{'3d' if action == '3d' else '2d'}')")
            if action == "3d":
                page.evaluate("Object.assign(window.__mosca.scene.cam, {dist: 150, pitch: 0.5, yaw: 0.4})")
            time.sleep(1.0)
            frames = []
            t0 = time.time()
            for k in range(fps * seconds):
                target = t0 + k / fps
                d = target - time.time()
                if d > 0:
                    time.sleep(d)
                if action == "tap" and k == fps * 3:
                    page.click("#tap")
                if action == "3d":
                    page.evaluate(f"window.__mosca.scene.cam.yaw = {0.4 + 0.02 * k}")   # slow orbit
                im = grab(page, sel).resize((400, 300) if action == "3d" else (480, 360), Image.LANCZOS)
                frames.append(im)
                if k % 20 == 0:
                    im.save(FRAMES / f"{name}-{k:03d}.png")
            save_gif(frames[::2] if action == "3d" else frames, GIFS / f"{name}.gif", fps // 2 if action == "3d" else fps,
                     colors=64 if action == "3d" else 96)
            print(name, "->", GIFS / f"{name}.gif", flush=True)
        ctx.close()
        b.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["screens", "gifs", "console"])
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--prefix", default="local")
    ap.add_argument("--token", default=None)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    tok = a.token or local_token()
    if a.what == "screens":
        screens(a.base, tok, a.prefix)
    elif a.what == "console":
        console(a.base, tok)
    else:
        gifs(a.base, tok, only=a.only)
