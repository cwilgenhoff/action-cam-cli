"""Telemetry overlay frame rendering (Pillow).

Pure, in-memory frame composition: given a speed value and a frame size, draw the
gauge onto a transparent RGBA image. No I/O, no ffmpeg — the encode lives in
``encode.py`` (mirrors grading's ffmpeg.py / executor.py split).

The font is Pillow's bundled scalable default (``ImageFont.load_default(size=...)``,
Pillow >= 10.1), so there is no font file to ship and no dependence on system fonts.
"""

from PIL import Image, ImageDraw, ImageFont

Size = tuple[int, int]


def format_speed(speed_kmh: float) -> str:
    """Format a speed for display: 24.54 -> '24.5 km/h' (one decimal + unit)."""
    return f"{speed_kmh:.1f} km/h"


def render_frame(speed_kmh: float, size: Size, margin_frac: float = 0.05) -> Image.Image:
    """Render one transparent RGBA frame with the speed gauge in the lower-left.

    White text with a black stroke for legibility against bright skies or dark
    tarmac. Font size scales with frame height; every pixel except the text/stroke
    stays fully transparent so the overlay composites cleanly over the footage.
    """
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    font_size = max(round(height * 0.05), 12)
    font = ImageFont.load_default(size=font_size)
    stroke = max(round(font_size * 0.08), 1)
    margin = round(min(width, height) * margin_frac)

    draw.text(
        (margin, height - margin),
        format_speed(speed_kmh),
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=stroke,
        stroke_fill=(0, 0, 0, 255),
        anchor="ls",  # left edge, text baseline
    )
    return image
