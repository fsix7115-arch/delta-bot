"""Generate a clean geometric avatar for the GitHub profile.

GitHub renders any uploaded image as a circle, so the design has to survive
circular cropping: nothing important near the corners, high contrast, no
thin strokes. A monogram with a diagonal accent reads well at 32px and still
looks deliberate at 460px.
"""
import math
import os

from PIL import Image, ImageDraw

SIZE = 1024
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatar.png")

BG_TOP = (13, 27, 42)
BG_BOT = (20, 60, 92)
ACCENT = (56, 189, 248)
INK = (240, 248, 255)
MUTED = (125, 178, 214)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def build(monogram="AX", accent_side="right"):
    img = Image.new("RGB", (SIZE, SIZE), BG_TOP)
    d = ImageDraw.Draw(img)

    # Vertical gradient background
    for y in range(SIZE):
        d.line([(0, y), (SIZE, y)], fill=lerp(BG_TOP, BG_BOT, y / SIZE))

    # Subtle concentric rings, kept faint so they never fight the monogram
    cx = cy = SIZE / 2
    for r, alpha in ((430, 16), (350, 12), (270, 9)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  outline=lerp(BG_BOT, ACCENT, alpha / 40),
                  width=3)

    # Diagonal accent wedge in the lower-right, the direction the "X" points
    if accent_side == "right":
        d.polygon([(SIZE, int(SIZE * 0.58)), (SIZE, SIZE),
                   (int(SIZE * 0.52), SIZE)], fill=ACCENT)

    # Monogram: two geometric strokes rather than a font, so it never
    # depends on a font being installed and always renders identically.
    pad = SIZE * 0.24
    w = SIZE * 0.075          # stroke weight
    top, bot = SIZE * 0.30, SIZE * 0.70
    gap = SIZE * 0.055

    # "A" - two diagonals + crossbar
    a_cx = pad + w
    a_top_x, a_bot_l, a_bot_r = a_cx, a_cx - w * 1.55, a_cx + w * 1.55
    d.line([(a_top_x, top), (a_bot_l, bot)], fill=INK, width=int(w))
    d.line([(a_top_x, top), (a_bot_r, bot)], fill=INK, width=int(w))
    bar_y = bot - (bot - top) * 0.34
    d.line([(a_cx - w * 1.0, bar_y), (a_cx + w * 1.0, bar_y)],
           fill=INK, width=int(w * 0.72))

    # "X" - two crossing diagonals
    x_cx = SIZE - pad - w
    x_l = x_cx - w * 1.35
    x_r = x_cx + w * 1.35
    d.line([(x_l, top), (x_r, bot)], fill=INK, width=int(w))
    d.line([(x_r, top), (x_l, bot)], fill=INK, width=int(w))

    return img


if __name__ == "__main__":
    build().save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")
