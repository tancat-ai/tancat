"""Lossless re-encoding of evidence screenshots.

Evidence images are encoded with Pillow rather than by asking Playwright for
``type="webp"``: Chromium's WebP *lossless* encoder is pathologically
inefficient on UI screenshots and produced files **4.2x larger** than its own
PNG output for the real saucedemo login page (111.8 KB vs 26.5 KB at
1280x720).

**A5 (2026-09-21): the encode must be cheap, because it — not the screenshot —
dominates per-step evidence cost.** Measured on the real 1280x6533 landing
page: full-page screenshot ~320 ms, Pillow WebP lossless ``method=2`` ~2330 ms.
``method=0`` encodes in ~300 ms (7x faster) — but on flat UI pages its output
is *larger* than the source PNG (1202 KB vs 1015 KB), so the rule is:

    encode lossless WebP at ``method=0``; keep the PNG whenever the WebP
    output would not be strictly smaller.

Both branches are lossless and pixel-identical — evidence is an audit
artifact, so fidelity is never traded for size or speed. The file extension
follows the format actually written, which is why the public API returns the
format alongside the bytes (``encode_evidence_image`` / ``write_evidence_image``).

History — measured over real evidence screenshots::

    17 real screenshots, same suite    PNG 2354 KB -> WebP(m4) 1382 KB  (59%)
    1280x6533 landing page             PNG 1015 KB, WebP(m0) 1202 KB  -> PNG kept
    encode wall time, 1280x6533        m0 ~300 ms | m1 ~2000 ms | m2 ~2300 ms | m4 ~2400 ms

**Watch item (B-076):** Pillow, Chromium and the WebP bitstream keep improving.
Re-measure this trade whenever Pillow is upgraded or a new lossless option
appears (e.g. AVIF) — the method/keep-PNG threshold in ``encode_evidence_image``
is the single place to update.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from src.config import evidence_image_format


def encode_evidence_image(png_bytes: bytes, image_format: str | None = None) -> tuple[bytes, str]:
    """Re-encode a PNG screenshot for evidence storage.

    Returns ``(data, actual_format)`` where ``actual_format`` is ``"webp"`` or
    ``"png"`` and **matches the bytes returned** — the caller must name the
    file with the returned format's extension.

    With the default (WebP) the output is lossless WebP at ``method=0`` — or
    the original PNG unchanged whenever the WebP encoding would not be strictly
    smaller (A5: never grow the file, never pay for a lossless encoding that
    does not pay for itself).

    Returns *png_bytes* unchanged (as ``"png"``) when the configured format is
    ``"png"``.

    Encoding problems fall back to the original bytes: evidence capture must
    never fail because of an image-format issue.
    """
    fmt = image_format or evidence_image_format()
    if fmt == "png":
        return png_bytes, "png"
    try:
        buffer = io.BytesIO()
        with Image.open(io.BytesIO(png_bytes)) as opened:
            image: Image.Image = opened
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            # A5: method=0. Measured on the real 1280x6533 evidence capture:
            # ~300 ms vs ~2300 ms at method=2 — the extra compression passes
            # saved 15-35% of the *file* at 7x the *wall time*, and on flat UI
            # pages they still lose to PNG (see module docstring).
            image.save(buffer, format="WEBP", lossless=True, quality=100, method=0)
        webp = buffer.getvalue()
        if len(webp) >= len(png_bytes):
            # A5: keep the PNG — the WebP encoding did not pay for itself.
            return png_bytes, "png"
        return webp, "webp"
    except Exception:
        return png_bytes, "png"


def write_evidence_image(png_bytes: bytes, destination: Path | str) -> tuple[int, str]:
    """Write *png_bytes* to *destination* in the configured evidence format.

    Returns ``(bytes_written, actual_format)`` — the format actually written,
    which may differ from the configured one when the adaptive rule (A5)
    keeps the PNG.

    NOTE: *destination* is used verbatim. If the adaptive rule may switch
    formats, callers that care about the extension should use
    ``encode_evidence_image`` and build the path from the returned format.
    """
    data, actual = encode_evidence_image(png_bytes)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data), actual
