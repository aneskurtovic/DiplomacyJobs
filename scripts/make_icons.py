"""Draws the DiplomacyJobs brand mark as the PWA and Apple touch icons in board/static/board/icons/."""
from pathlib import Path

from PIL import Image, ImageDraw

BLUE = (15, 76, 129)
WHITE = (255, 255, 255)
GLOBE_SPAN = 18.6  # outer diameter of the globe in the 32-unit mark, stroke included
SUPERSAMPLE = 4
OUT = Path(__file__).resolve().parents[1] / "board/static/board/icons"


def ring(draw, centre, rx, ry, width, unit):
    """Outline ellipse whose stroke is centred on the rx x ry curve; sizes are in mark units."""
    cx, cy = centre
    half = width / 2
    draw.ellipse([cx - rx * unit - half, cy - ry * unit - half, cx + rx * unit + half, cy + ry * unit + half], outline=WHITE, width=round(width))


def mark(size, unit, rounded):
    """The brand mark centred on a size x size canvas, one mark unit = unit pixels."""
    edge = size * SUPERSAMPLE
    scale = unit * SUPERSAMPLE
    # Transparent but blue, so edge pixels blend without a dark fringe.
    canvas = Image.new("RGBA", (edge, edge), BLUE + (0,) if rounded else BLUE + (255,))
    draw = ImageDraw.Draw(canvas)
    centre = (edge / 2, edge / 2)
    if rounded:
        draw.rounded_rectangle([0, 0, edge - 1, edge - 1], radius=7 * scale, fill=BLUE + (255,))
    ring(draw, centre, 8.5, 8.5, 1.6 * scale, scale)
    ring(draw, centre, 2.6, 8.5, 1.6 * scale, scale)
    draw.line([(centre[0] - 8.5 * scale, centre[1]), (centre[0] + 8.5 * scale, centre[1])], fill=WHITE, width=round(1.6 * scale))
    return canvas.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mark(192, 192 / 32, rounded=True).save(OUT / "icon-192.png", optimize=True)
    mark(512, 512 / 32, rounded=True).save(OUT / "icon-512.png", optimize=True)
    # Maskable: the globe sits in the central 60%, the rest is bleed for the platform mask.
    mark(512, 0.6 * 512 / GLOBE_SPAN, rounded=False).convert("RGB").save(OUT / "icon-maskable-512.png", optimize=True)
    # Apple: opaque square, no transparency allowed.
    mark(180, 0.7 * 180 / GLOBE_SPAN, rounded=False).convert("RGB").save(OUT / "apple-touch-icon.png", optimize=True)


if __name__ == "__main__":
    main()
