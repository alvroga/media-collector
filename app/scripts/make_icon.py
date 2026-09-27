#!/usr/bin/env python3
"""Builds the app icon files from the designed artwork, app/Branding/AppIcon.svg.

    python3 app/scripts/make_icon.py

Writes Branding/AppIcon.png (1024px, used for the Dock icon in dev builds) and
Packaging/AppIcon.icns (for the packaged app). Needs Pillow, numpy and macOS (`qlmanage`, `iconutil`).

The SVG uses blur and drop-shadow filters, which macOS QuickLook renders faithfully but always on an opaque
white background. To get real transparency the artwork is rendered twice, on white and on black, and the
alpha is recovered from the difference (alpha = 1 - (white - black)); the colour is then un-premultiplied.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
SVG = HERE / "Branding" / "AppIcon.svg"


def render_on(svg_text: str, colour: str, workdir: Path) -> np.ndarray:
    """Render the SVG on an opaque background colour with QuickLook; returns float RGB in 0..255."""
    bg = f'<rect x="0" y="0" width="100%" height="100%" fill="{colour}"/>'
    text = re.sub(r"(<svg\b[^>]*>)", lambda m: m.group(1) + bg, svg_text, count=1)
    src = workdir / f"icon_{colour.strip('#')}.svg"
    src.write_text(text)
    subprocess.run(["qlmanage", "-t", "-s", "1024", "-o", str(workdir), str(src)],
                   check=True, capture_output=True)
    img = Image.open(workdir / f"{src.name}.png").convert("RGB")
    if img.size != (1024, 1024):
        img = img.resize((1024, 1024), Image.LANCZOS)
    return np.asarray(img, dtype=np.float64)


def build() -> Image.Image:
    text = SVG.read_text()
    with tempfile.TemporaryDirectory() as t:
        w = render_on(text, "#ffffff", Path(t))
        b = render_on(text, "#000000", Path(t))
    alpha = np.clip(1.0 - (w - b).mean(axis=2) / 255.0, 0.0, 1.0)           # per-pixel coverage
    safe = np.maximum(alpha, 1e-6)[..., None]
    rgb = np.clip(b / safe, 0, 255)                                          # un-premultiply
    rgb[alpha < 1e-3] = 0
    out = np.dstack([rgb, alpha * 255.0]).round().astype(np.uint8)
    return Image.fromarray(out)  # (H, W, 4) uint8 -> RGBA


def main() -> None:
    icon = build()
    res = HERE / "Branding"
    res.mkdir(parents=True, exist_ok=True)
    icon.save(res / "AppIcon.png")
    with tempfile.TemporaryDirectory() as t:
        iconset = Path(t) / "AppIcon.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            icon.resize((base, base), Image.LANCZOS).save(iconset / f"icon_{base}x{base}.png")
            icon.resize((base * 2, base * 2), Image.LANCZOS).save(iconset / f"icon_{base}x{base}@2x.png")
        (HERE / "Packaging").mkdir(exist_ok=True)
        if shutil.which("iconutil"):
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "Packaging/AppIcon.icns")],
                           check=True)
    print("wrote", res / "AppIcon.png")


if __name__ == "__main__":
    main()
