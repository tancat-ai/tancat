# `src/evidence_image.py`

## High-Level Purpose

Lossless re-encoding of evidence screenshots. Evidence images default to WebP so a run leaves a smaller footprint on disk and in reports. The encoding is done here with Pillow rather than by asking Playwright for `type="webp"`, because Chromium's WebP *lossless* encoder is pathologically inefficient on UI screenshots — it produced files **4.2x larger** than its own PNG output for the real saucedemo login page (111.8 KB vs 26.5 KB at 1280x720), whereas Pillow's lossless WebP of those same pixels is 10.3 KB.

Both encoders are lossless, so evidence stays pixel-identical either way — only the file size differs. That distinction matters: evidence is an audit artifact, so fidelity is never traded for size.

## Module Metadata

- **Lines:** 66
- **Imports:** `io`, `pathlib.Path`, `PIL.Image`, `src.config.evidence_image_format`

## Measured Savings

| Encoding | Size | vs PNG |
|----------|------|--------|
| PNG (old default) | 2501 KB | 100% |
| WebP lossless (Pillow, new default) | 1279 KB | **51%** |
| WebP q90 (lossy, not used) | — | 45% |
| WebP q80 (lossy, not used) | — | 33% |

The PNG → WebP figures are a live A/B: the same generated suite executed against the same site, 17 screenshots each way. A separate re-encode of 17 real evidence captures measured 59%.

## Functions

### `embed_preview_data_uri(image_path, *, max_width=EMBED_PREVIEW_MAX_WIDTH, quality=EMBED_PREVIEW_QUALITY) -> str | None`
Returns a **downscaled preview** of an evidence image as a data URI, for the report and the app.

An evidence frame is a full-page capture (~8,000-9,000 px tall, ~2.5 MB each); embedding
them whole made the report the customer keeps unsendable. The preview is scaled to
`EMBED_PREVIEW_MAX_WIDTH` (640 px) and encoded as lossy WebP. The lossless capture on
disk stays the artifact an audit reads, and every preview names its source file. Returns
`None` when the image cannot be read or scaled, so the caller can fall back.

Constants: `EMBED_PREVIEW_MAX_WIDTH = 640`, `EMBED_PREVIEW_QUALITY = 85`.

### `encode_evidence_image(png_bytes, image_format=None) -> bytes`
Re-encodes a PNG screenshot for evidence storage.
- `"png"` (or an explicit `image_format="png"`) returns `png_bytes` untouched.
- `"webp"` returns a lossless, pixel-identical WebP encoding (`lossless=True, quality=100`).
- Non-RGB/RGBA images are converted to RGB first (WebP has no palette mode).
- **Any encoding failure returns the original bytes** — evidence capture must never fail because of an image-format problem.

### `write_evidence_image(png_bytes, destination) -> int`
Writes `png_bytes` to `destination` in the configured format, creating parent directories, and returns the number of bytes written.

## Design Notes

- **Why Pillow and not Playwright.** Playwright does support `type="webp"`, and it is genuinely lossless — but Chromium's encoder inflates these UI screenshots badly. Capturing PNG and re-encoding with Pillow is what actually delivers the saving.
- **Why lossless.** A lossy WebP (q80) would save roughly twice as much again, but it would alter pixels, and the project's position is that evidence must remain audit-exact. The quality knob is therefore not exposed.
- **Format selection lives in config.** `src/config.py` owns `evidence_image_format()` / `evidence_image_extension()` (default `webp`, overridable with `AITEST_EVIDENCE_IMAGE_FORMAT=png`). This module only performs the encode, so the escape hatch stays in one place.

## Dependencies

- `PIL.Image` (Pillow — a declared project dependency; also already used by the CLI evidence generator for image dimensions)
- `src.config.evidence_image_format`

## Depended On By

- `src/evidence_tracker.py` — per-step runtime evidence screenshots
- `src/cli/evidence_generator.py` — CLI / bug-report screenshot capture
