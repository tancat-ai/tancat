"""Tests for the evidence screenshot image format.

Evidence defaults to WebP, encoded *losslessly* by Pillow (see
``src/evidence_image.py``), so the image stays pixel-identical — evidence is an
audit artifact, so fidelity is never traded for size — while measuring ~59% of
the PNG size over real evidence captures.

These tests pin four things:
1. the default really is lossless WebP,
2. ``AITEST_EVIDENCE_IMAGE_FORMAT`` is a working escape hatch to PNG (and an
   unsupported value can never break evidence capture),
3. the encoder is genuinely lossless (pixel-identical) and actually smaller,
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
    """A small gradient PNG — gradient content stands in for a real page."""
    img = Image.new("RGB", size)
    for y in range(size[1]):
        for x in range(size[0]):
            img.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
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

    assert encode_evidence_image(png) == png


def test_encode_webp_is_lossless_and_pixel_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    """The encoded evidence must stay pixel-for-pixel identical to the PNG."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    png = _png_bytes(size=(300, 200))

    encoded = encode_evidence_image(png)

    with Image.open(io.BytesIO(encoded)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (300, 200)
        with Image.open(io.BytesIO(png)) as original:
            diff = ImageChops.difference(original.convert("RGB"), decoded.convert("RGB"))
            assert diff.getbbox() is None, "lossless WebP must not alter any pixel"


def test_encode_webp_is_smaller_than_the_png(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of the default: smaller files at identical fidelity."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    png = _png_bytes(size=(400, 300))

    encoded = encode_evidence_image(png)

    assert len(encoded) < len(png), f"webp {len(encoded)}B not smaller than png {len(png)}B"


def test_encode_falls_back_to_original_on_unusable_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evidence capture must never fail because of an image problem."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    junk = b"this is not an image"

    assert encode_evidence_image(junk) == junk


def test_write_evidence_image_writes_webp_and_returns_size(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    destination = tmp_path / "evidence" / "nested" / "shot.webp"

    written = write_evidence_image(_png_bytes(), destination)

    assert destination.exists()
    assert written == destination.stat().st_size
    assert Image.open(destination).format == "WEBP"
