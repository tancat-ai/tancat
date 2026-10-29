"""Generate the synthetic scanned-page OCR fixture (t-0834).

Writes ``tests/fixtures/ocr_scanned_page.pdf``: one US-Letter page with a
line-item table and a bar-chart graphic, saved as an **image-only 300 DPI PDF**
(all text is pixels; there is no text layer).  It is the stand-in for a scanned
document so the tier-1 CPU OCR path (``RapidOCRBackend.parse_page``) has an
offline regression fixture: the docs in the eval set are native-text PDFs, so
without this the CPU OCR tier is never exercised.

Fully synthetic - no real LV or customer document is drawn, read, or committed.
No network is used: the page is rendered locally with Pillow and the font comes
from the OS (with a built-in fallback).

Run:

    python scripts/maintenance/make_ocr_scanned_fixture.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# US Letter at 300 DPI (the DPI the OCR path rasterises at).
DPI = 300
PAGE_W = round(8.5 * DPI)  # 2550 px
PAGE_H = round(11 * DPI)  # 3300 px

_OUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ocr_scanned_page.pdf"

#: Plain-ASCII tokens the regression test asserts on (drawn large, black on
#: white, so PP-OCRv6 recovers them reliably).
KNOWN_TOKENS = ("Invoice", "Widget", "Gadget", "Total", "15.00")

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """A clean sans-serif at *size* px; falls back to Pillow's built-in font."""
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _draw_table(draw: ImageDraw.ImageDraw, top: int) -> None:
    """A 4-column line-item table with grid lines, black on white."""
    left = 180
    widths = (900, 260, 420, 420)
    row_h = 100
    rows = (
        ("Item", "Qty", "Price", "Total"),
        ("Widget", "2", "15.00", "30.00"),
        ("Gadget", "1", "40.00", "40.00"),
        ("Service", "3", "10.00", "30.00"),
        ("Total Due", "", "", "100.00"),
    )
    font = _font(46)
    x = left
    for col, width in enumerate(widths):
        for row_i, row in enumerate(rows):
            y0 = top + row_i * row_h
            draw.rectangle([x, y0, x + width, y0 + row_h], outline="black", width=6)
            text = row[col]
            if text:
                pad = 30 if col == 0 else 24
                draw.text((x + pad, y0 + 22), text, font=font, fill="black")
        x += width


def _draw_chart(draw: ImageDraw.ImageDraw, top: int) -> None:
    """A bar-chart graphic (axes + three bars + labels) - the non-text content."""
    baseline = top + 560
    draw.line([260, baseline, 1400, baseline], fill="black", width=8)  # x axis
    draw.line([260, baseline, 260, top + 40], fill="black", width=8)  # y axis
    bars = ((360, 240), (680, 460), (1000, 350))
    labels = ("A", "B", "C")
    font = _font(44)
    for (x, height), label in zip(bars, labels, strict=True):
        draw.rectangle([x, baseline - height, x + 160, baseline], outline="black", width=6)
        draw.text((x + 50, baseline + 24), label, font=font, fill="black")
    draw.text((260, top - 60), "Quarterly usage", font=_font(44), fill="black")


def main() -> None:
    img = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(img)

    draw.text((180, 160), "Invoice", font=_font(96), fill="black")
    draw.text((180, 320), "Number: INV-2026-001", font=_font(48), fill="black")
    draw.text((180, 430), "Billed to: Acme Corporation", font=_font(48), fill="black")

    _draw_table(draw, 620)
    _draw_chart(draw, 1350)

    draw.text((180, PAGE_H - 180), "Page 1 of 1 - synthetic document, no real data.", font=_font(36), fill="black")

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(_OUT, format="PDF", resolution=float(DPI), quality=95)
    print(f"wrote {_OUT} ({_OUT.stat().st_size} bytes, {PAGE_W}x{PAGE_H} px at {DPI} DPI, image-only)")
    print(f"known tokens: {', '.join(KNOWN_TOKENS)}")


if __name__ == "__main__":
    main()
