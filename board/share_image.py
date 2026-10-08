"""Open Graph share image for a job: title, employer and deadline on the brand background, for links shared in Viber and WhatsApp groups."""
from io import BytesIO
from pathlib import Path

from django.utils.translation import gettext
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
MARGIN = 72
FONTS = Path(__file__).resolve().parent / "og_fonts"
# tokens.css: --dj-blue-800 background, --dj-blue-700 brand mark, --dj-blue-200 and --dj-blue-100 for secondary text.
BACKGROUND, MARK, SOFT, TEXT, PANEL = "#0b3a63", "#0f4c81", "#b6cfe7", "#ffffff", "#082b4a"


def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"PublicSans-{weight}.ttf"), size)


def wrap(draw, text, face, width, max_lines):
    """Greedy word wrap; the last allowed line ends in an ellipsis after a whole word when text is left over."""
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=face) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    else:
        if line:
            lines.append(line)
        return lines
    last = lines[max_lines - 1].split()
    while len(last) > 1 and draw.textlength(" ".join(last) + "…", font=face) > width:
        last.pop()
    return lines[:max_lines - 1] + [" ".join(last).rstrip(",;:–-") + "…"]


def brand_mark(draw, x, y, size):
    draw.rounded_rectangle((x, y, x + size, y + size), radius=size * 7 // 32, fill=MARK)
    centre, radius, stroke = x + size / 2, size * 8.5 / 32, max(2, size // 20)
    cy = y + size / 2
    draw.ellipse((centre - radius, cy - radius, centre + radius, cy + radius), outline=TEXT, width=stroke)
    draw.line((centre - radius, cy, centre + radius, cy), fill=TEXT, width=stroke)
    draw.ellipse((centre - radius * 0.42, cy - radius, centre + radius * 0.42, cy + radius), outline=TEXT, width=stroke)


def render(job):
    """PNG bytes for one job, in the active interface language."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    text_width = WIDTH - 2 * MARGIN

    brand_mark(draw, MARGIN, MARGIN, 52)
    draw.text((MARGIN + 68, MARGIN + 26), "DiplomacyJobs", font=font("Bold", 30), fill=TEXT, anchor="lm")

    y = MARGIN + 104
    for line in wrap(draw, job.employer_label, font("Regular", 30), text_width, 1):
        draw.text((MARGIN, y), line, font=font("Regular", 30), fill=SOFT)
        y += 48

    # Long titles step down a size before they are cut.
    for size in (60, 52, 46):
        face = font("Bold", size)
        lines = wrap(draw, job.title, face, text_width, 3)
        if not lines[-1].endswith("…"):
            break
    line_height = round(size * 1.18)
    for line in lines:
        draw.text((MARGIN, y), line, font=face, fill=TEXT)
        y += line_height

    # Footer panel: deadline on the left, place on the right.
    top = HEIGHT - MARGIN - 84
    draw.rounded_rectangle((MARGIN, top, WIDTH - MARGIN, HEIGHT - MARGIN), radius=14, fill=PANEL)
    if job.deadline:
        deadline = job.deadline.strftime("%d.%m.%Y.")
    elif job.open_until_filled:
        deadline = gettext("Do popune mjesta")
    else:
        deadline = gettext("Nije naveden")
    label = gettext("Rok prijave")
    label_face, value_face = font("Regular", 28), font("Bold", 34)
    middle = top + 42
    draw.text((MARGIN + 28, middle), label, font=label_face, fill=SOFT, anchor="lm")
    draw.text((MARGIN + 28 + draw.textlength(label, font=label_face) + 16, middle), deadline, font=value_face, fill=TEXT, anchor="lm")
    place = job.city or gettext("Bosna i Hercegovina")
    draw.text((WIDTH - MARGIN - 28, middle), place, font=label_face, fill=SOFT, anchor="rm")

    buffer = BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
