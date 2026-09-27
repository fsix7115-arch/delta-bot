"""Verify the avatar reads correctly at GitHub's real display sizes.

GitHub shows a profile avatar at 32px on the navbar, ~64px on the profile page
header, and 460px when you open the image directly. The design only works if
the monogram survives the smallest size and survives circular cropping, so
render all three and check them side by side rather than trusting the 1024px
source.
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "avatar.png")
OUT = os.path.join(HERE, "avatar_check.png")

SIZES = (32, 64, 128, 460)


def circle(img):
    """Apply GitHub's circular crop with a transparent outside."""
    out = img.convert("RGBA")
    mask = Image.new("L", out.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, out.size[0], out.size[1]), fill=255)
    out.putalpha(mask)
    return out


def main():
    src = Image.open(SRC).convert("RGB")
    tiles = []
    for s in SIZES:
        t = circle(src.resize((s, s), Image.LANCZOS))
        tiles.append((s, t))

    pad, label_h = 16, 22
    widths = [t.width for _, t in tiles]
    sheet_w = sum(widths) + pad * (len(tiles) + 1)
    sheet_h = max(t.height for _, t in tiles) + pad * 2 + label_h
    sheet = Image.new("RGB", (sheet_w, sheet_h), (24, 24, 28))
    d = ImageDraw.Draw(sheet)

    x = pad
    for s, t in tiles:
        y = pad
        sheet.paste(t, (x, y), t)
        d.text((x, y + t.height + 4), f"{s}px", fill=(200, 200, 210))
        x += t.width + pad

    sheet.save(OUT)
    print(f"wrote {OUT}  ({sheet_w}x{sheet_h})")

    # A cheap legibility proxy: contrast between ink and background inside the
    # circle, and how much of the circle area the strokes actually cover.
    g = src.convert("L")
    px = list(g.getdata())
    bright = sum(1 for v in px if v > 170)
    print(f"ink coverage: {bright/len(px)*100:.1f}% of pixels above L=170")
    print("(a monogram that covers <3% disappears at 32px; >18% turns to mush)")

    # Downscaled stroke check: does the A crossbar survive a 32px render?
    tiny = src.resize((32, 32), Image.LANCZOS)
    tp = list(tiny.convert("L").getdata())
    print(f"32px min/max luminance: {min(tp)}/{max(tp)}  "
          f"spread={max(tp)-min(tp)} (needs >90 to read as a shape)")


if __name__ == "__main__":
    main()
