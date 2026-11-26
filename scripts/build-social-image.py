#!/usr/bin/env python3
"""Build the default social and search preview image (site/assets/social/terento-app-og.png).

The image is composed only from published site assets: the Install maps window
with a selected map (site/assets/app/masters/map-selected.png) and the Home hero
watch drawing with the OpenTopoMap screen (site/assets/home/). It has no text,
because search engines prefer a representative picture without text.

Usage: python3 scripts/build-social-image.py [output.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "site" / "assets" / "social" / "terento-app-og.png"
WIDTH, HEIGHT = 1200, 630

# brand/DESIGN_TOKENS.json: color.light.backgroundSecondary and color.brand.graphite.
BACKGROUND = "#F1EEE7"
SHADOW = (0x22, 0x2A, 0x2B)

APP_WIDTH = 760
APP_LEFT, APP_TOP = 56, 70
WATCH_SIZE = 580
WATCH_CENTER_X = 890

# site/styles.css .home-watch: the transparent screen inside watch-front.webp.
SCREEN = (0.262, 0.219, 0.472, 0.481)


def soft_shadow(alpha: Image.Image, offset: tuple[int, int], blur: int, opacity: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (*SHADOW, 0))
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    mask.paste(alpha, offset)
    mask = mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda value: int(value * opacity))
    layer.putalpha(mask)
    return layer


def strap_fade(size: int) -> Image.Image:
    """Vertical fade of the straps, as the .home-watch-body CSS mask does on Home."""
    stops = [(0.02, 0), (0.16, 255), (0.84, 255), (0.98, 0)]
    column = Image.new("L", (1, size))
    for y in range(size):
        t = (y + 0.5) / size
        if t <= stops[0][0] or t >= stops[-1][0]:
            value = 0
        elif t < stops[1][0]:
            value = 255 * (t - stops[0][0]) / (stops[1][0] - stops[0][0])
        elif t > stops[2][0]:
            value = 255 * (stops[3][0] - t) / (stops[3][0] - stops[2][0])
        else:
            value = 255
        column.putpixel((0, y), int(round(value)))
    return column.resize((size, size))


def watch_with_map(size: int) -> Image.Image:
    body = Image.open(ROOT / "site/assets/home/watch-front.webp").convert("RGBA").resize((size, size), Image.LANCZOS)
    x, y, w, h = (round(value * size) for value in SCREEN)
    screen = Image.open(ROOT / "site/assets/home/hero-opentopomap.webp").convert("RGBA").resize((w, h), Image.LANCZOS)
    round_mask = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(round_mask).ellipse((0, 0, w * 4 - 1, h * 4 - 1), fill=255)
    screen.putalpha(round_mask.resize((w, h), Image.LANCZOS))
    watch = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    watch.alpha_composite(screen, (x, y))
    watch.alpha_composite(body)
    watch.putalpha(ImageChops.multiply(watch.getchannel("A"), strap_fade(size)))
    return watch


def build(output: Path) -> None:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), BACKGROUND)

    app = Image.open(ROOT / "site/assets/app/masters/map-selected.png").convert("RGBA")
    app = app.resize((APP_WIDTH, round(app.height * APP_WIDTH / app.width)), Image.LANCZOS)
    canvas.alpha_composite(soft_shadow(app.getchannel("A"), (APP_LEFT, APP_TOP + 14), 22, 0.16))
    canvas.alpha_composite(app, (APP_LEFT, APP_TOP))

    watch = watch_with_map(WATCH_SIZE)
    left = WATCH_CENTER_X - WATCH_SIZE // 2
    top = (HEIGHT - WATCH_SIZE) // 2
    canvas.alpha_composite(soft_shadow(watch.getchannel("A"), (left, top + 18), 26, 0.22))
    canvas.alpha_composite(watch, (left, top))

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, "PNG", optimize=True)


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT)
