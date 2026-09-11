"""Lossless re-encoding of evidence screenshots.

Evidence images default to WebP so a run leaves a smaller footprint on disk and
in reports. The encoding happens here, with Pillow, rather than by asking
Playwright for ``type="webp"``: Chromium's WebP *lossless* encoder is
pathologically inefficient on UI screenshots and produced files **4.2x larger**
than its own PNG output for the real saucedemo login page (111.8 KB vs 26.5 KB
at 1280x720). Pillow's lossless WebP of those same pixels is 10.3 KB — 39% of
the PNG.

Both encoders are lossless, so the image stays pixel-identical either way
(evidence is an audit artifact — fidelity is never traded for size); only the
file size differs.

Measured over 17 real evidence screenshots (``generated_tests/verify_*/evidence``)::

    Live A/B, same suite + same site   PNG 2501 KB -> WebP 1279 KB   (51%, 49% smaller)
    Re-encode of 17 real screenshots   PNG 2354 KB -> WebP 1382 KB   (59%)
    WebP q90 (lossy, not used)                                     (45%)
    WebP q80 (lossy, not used)                                     (33%)
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from src.config import evidence_image_format


def encode_evidence_image(png_bytes: bytes, image_format: str | None = None) -> bytes:
    """Re-encode a PNG screenshot for evidence storage.

    Returns *png_bytes* unchanged when the configured format is ``"png"``. For
    ``"webp"`` returns a lossless, pixel-identical WebP encoding.

    Encoding problems fall back to the original bytes: evidence capture must
    never fail because of an image-format issue.
    """
    fmt = image_format or evidence_image_format()
    if fmt == "png":
        return png_bytes
    try:
        buffer = io.BytesIO()
        with Image.open(io.BytesIO(png_bytes)) as opened:
            image: Image.Image = opened
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            image.save(buffer, format="WEBP", lossless=True, quality=100)
        return buffer.getvalue()
    except Exception:
        return png_bytes


def write_evidence_image(png_bytes: bytes, destination: Path | str) -> int:
    """Write *png_bytes* to *destination* in the configured evidence format.

    Returns the number of bytes written.
    """
    data = encode_evidence_image(png_bytes)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)
