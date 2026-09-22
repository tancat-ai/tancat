"""Tests for the evidence screenshot image format.

Evidence is encoded *losslessly* by Pillow (see ``src/evidence_image.py``):
lossless WebP at ``method=0``, or the original PNG whenever the WebP output
would not be strictly smaller (A5 — the encode must be cheap, and the file
must never grow). Either way the image stays pixel-identical: evidence is an
audit artifact, so fidelity is never traded for size or speed.

These tests pin:
1. the default really is lossless WebP (adaptive fallback to PNG allowed),
2. ``AITEST_EVIDENCE_IMAGE_FORMAT`` is a working escape hatch to PNG (and an
   unsupported value can never break evidence capture),
3. the encoder is genuinely lossless (pixel-identical) and never grows the
   file (A5),
4. the CLI evidence generator names files with the configured extension.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from src.analyzer import AnalyzedTestCase
from src.cli.evidence_generator import ScreenshotCapturer
from src.config import (
    EVIDENCE_IMAGE_FORMAT_DEFAULT,
    ScreenshotNaming,
    evidence_image_extension,
    evidence_image_format,
)
from src.evidence_image import encode_evidence_image, write_evidence_image

ENV_VAR = "AITEST_EVIDENCE_IMAGE_FORMAT"


def _png_bytes(size: tuple[int, int] = (200, 120)) -> bytes:
    """A small gradient PNG — smooth content where lossless WebP wins."""
    img = Image.new("RGB", size)
    for y in range(size[1]):
        for x in range(size[0]):
            img.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _noise_png_bytes(size: tuple[int, int] = (400, 300)) -> bytes:
    """Banded-sinusoid content where lossless WebP at method=0 LOSES to PNG.

    Measured 2026-09-21 (A5): webp-m0 is ~157% of the PNG here, so the
    adaptive rule must keep the PNG — this is the real-world flat-UI case on
    the 1280x6533 landing page (1202 KB webp vs 1015 KB png).
    """
    import math

    img = Image.new("RGB", size)
    for y in range(size[1]):
        for x in range(size[0]):
            r = int(127 + 127 * math.sin(x / 17.0) * math.cos(y / 23.0))
            g = int(127 + 127 * math.sin(x / 31.0 + 1.7) * math.sin(y / 11.0))
            b = int(127 + 127 * math.cos(x / 7.0 - y / 29.0))
            img.putpixel((x, y), (r, g, b))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def test_default_is_lossless_webp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert EVIDENCE_IMAGE_FORMAT_DEFAULT == "webp"
    assert evidence_image_format() == "webp"
    assert evidence_image_extension() == ".webp"


@pytest.mark.parametrize("value", ["png", "PNG", " png "])
def test_env_override_forces_png(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ENV_VAR, value)

    assert evidence_image_format() == "png"
    assert evidence_image_extension() == ".png"


def test_env_explicit_webp_stays_webp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "webp")

    assert evidence_image_format() == "webp"


@pytest.mark.parametrize("value", ["gif", "jpeg", "bmp", "", "   "])
def test_unsupported_format_falls_back_to_webp(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """An unusable value must degrade to the default, never break capture."""
    monkeypatch.setenv(ENV_VAR, value)

    assert evidence_image_format() == "webp"
    assert evidence_image_extension() == ".webp"


@pytest.mark.parametrize("convention", list(ScreenshotNaming))
def test_generator_filename_uses_default_extension(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, convention: ScreenshotNaming
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ENV_VAR, raising=False)
    capturer = ScreenshotCapturer()
    capturer.naming_convention = convention

    name = capturer._generate_filename(  # noqa: SLF001 - unit under test
        AnalyzedTestCase(title="Login Test", description="logs in"), "navigate", ""
    )

    assert name.endswith(".webp"), name


def test_generator_filename_honours_png_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(ENV_VAR, "png")
    capturer = ScreenshotCapturer()

    name = capturer._generate_filename(  # noqa: SLF001 - unit under test
        AnalyzedTestCase(title="Login Test", description="logs in"), "navigate", ""
    )

    assert name.endswith(".png"), name


# ── encoder ───────────────────────────────────────────────────────────────


def test_encode_returns_png_untouched_when_format_is_png(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "png")
    png = _png_bytes()

    data, fmt = encode_evidence_image(png)

    assert data == png
    assert fmt == "png"


def test_encode_webp_is_lossless_and_pixel_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    """The encoded evidence must stay pixel-for-pixel identical to the PNG."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    png = _png_bytes(size=(300, 200))

    encoded, fmt = encode_evidence_image(png)

    with Image.open(io.BytesIO(encoded)) as decoded:
        assert decoded.format == ("WEBP" if fmt == "webp" else "PNG")
        assert decoded.size == (300, 200)
        with Image.open(io.BytesIO(png)) as original:
            diff = ImageChops.difference(original.convert("RGB"), decoded.convert("RGB"))
            assert diff.getbbox() is None, "lossless encoding must not alter any pixel"


def test_encode_picks_webp_when_it_shrinks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smooth (real-page-like) content: WebP wins on size at identical fidelity."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    png = _png_bytes(size=(400, 300))

    encoded, fmt = encode_evidence_image(png)

    assert fmt == "webp"
    assert len(encoded) < len(png), f"webp {len(encoded)}B not smaller than png {len(png)}B"


def test_encode_never_grows_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """A5: when WebP at method=0 would be LARGER than the PNG, keep the PNG."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    png = _noise_png_bytes()

    encoded, fmt = encode_evidence_image(png)

    assert len(encoded) <= len(png)
    if fmt == "webp":
        assert len(encoded) < len(png)
    else:
        assert fmt == "png"
        assert encoded == png


def test_encode_falls_back_to_original_on_unusable_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evidence capture must never fail because of an image problem."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    junk = b"this is not an image"

    data, fmt = encode_evidence_image(junk)

    assert data == junk
    assert fmt == "png"


def test_write_evidence_image_writes_actual_format_and_returns_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    destination = tmp_path / "evidence" / "nested" / "shot.webp"

    written, fmt = write_evidence_image(_png_bytes(), destination)

    assert destination.exists()
    assert written == destination.stat().st_size
    assert Image.open(destination).format == ("WEBP" if fmt == "webp" else "PNG")
