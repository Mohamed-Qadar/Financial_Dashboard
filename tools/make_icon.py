"""Generate assets/icon.ico (and icon.png) for the desktop application.

The icon is drawn with Pillow so the repository does not depend on a binary
design tool: a navy rounded square with a white dollar sign and two transfer
arrows. Run:  python tools/make_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
NAVY = (31, 58, 95, 255)
NAVY_DARK = (22, 41, 68, 255)
WHITE = (255, 255, 255, 255)
GREEN = (27, 175, 122, 255)
ORANGE = (235, 104, 52, 255)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_icon(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * 0.22)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=NAVY)
    # subtle inner shade at the bottom
    draw.rounded_rectangle((int(size * 0.04), int(size * 0.56), size - 1 - int(size * 0.04), size - 1 - int(size * 0.04)),
                           radius=int(radius * 0.8), fill=NAVY_DARK)
    draw.rounded_rectangle((int(size * 0.04), int(size * 0.04), size - 1 - int(size * 0.04), int(size * 0.62)),
                           radius=int(radius * 0.8), fill=NAVY)

    # dollar sign
    font = _font(int(size * 0.56))
    text = "$"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0] - int(size * 0.08)
    y = (size - th) / 2 - bbox[1] - int(size * 0.04)
    draw.text((x, y), text, font=font, fill=WHITE)

    # two transfer arrows (incoming green, outgoing orange) on the right
    ax = int(size * 0.70)
    w = int(size * 0.045)
    top, mid, bottom = int(size * 0.30), int(size * 0.50), int(size * 0.70)
    head = int(size * 0.07)
    # up arrow (incoming)
    draw.line((ax, mid - int(size * 0.02), ax, top + head), fill=GREEN, width=w)
    draw.polygon([(ax - head, top + head), (ax + head, top + head), (ax, top)], fill=GREEN)
    # down arrow (outgoing)
    ax2 = ax + int(size * 0.13)
    draw.line((ax2, mid + int(size * 0.02), ax2, bottom - head), fill=ORANGE, width=w)
    draw.polygon([(ax2 - head, bottom - head), (ax2 + head, bottom - head), (ax2, bottom)], fill=ORANGE)
    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    base = draw_icon(512)
    base.save(ASSETS / "icon.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[-1].save(ASSETS / "icon.ico", format="ICO", sizes=[(s, s) for s in sizes],
                    append_images=frames[:-1])
    print(f"wrote {ASSETS / 'icon.ico'} and icon.png")


if __name__ == "__main__":
    main()
