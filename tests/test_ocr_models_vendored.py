"""Vendored OCR models: present, pinned, and offline (t-0810).

The product is zero-egress, so the CPU OCR tier must never download a model at
runtime.  The four PP-OCRv6 files live in ``src/data/ocr/`` and every path is
pinned by SHA256 in ``manifest.json``.  These tests are fully offline.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.ocr_backends import _OCR_MODEL_DIR, _vendored_ocr_models

MODEL_DIR = Path(__file__).resolve().parents[1] / "src" / "data" / "ocr"
MANIFEST_PATH = MODEL_DIR / "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_exists_and_pins_four_files(manifest: dict) -> None:
    assert manifest["engine"] == "torch"
    assert manifest["rapidocr_version"] == "3.10.0"
    assert manifest["licence"] == "Apache-2.0"
    assert len(manifest["files"]) == 4
    for entry in manifest["files"]:
        assert entry["sha256"], f"{entry['name']} has no pinned SHA256"


def test_every_vendored_model_matches_its_pinned_sha256(manifest: dict) -> None:
    for entry in manifest["files"]:
        path = MODEL_DIR / entry["name"]
        assert path.is_file(), f"vendored OCR model missing: {path}"
        assert path.stat().st_size == entry["bytes"], f"{entry['name']} size drift"
        assert _sha256(path) == entry["sha256"], f"{entry['name']} SHA256 drift"


def test_backend_resolves_the_manifest_files() -> None:
    """The code's model paths are the files the manifest pins."""
    assert _OCR_MODEL_DIR == MODEL_DIR
    resolved = {path.name for path in _vendored_ocr_models().values()}
    pinned = {entry["name"] for entry in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["files"]}
    assert resolved == pinned


def test_vendoring_script_check_passes_offline() -> None:
    """`vendor_ocr_models.py --check` is the documented offline guard."""
    from scripts.maintenance.vendor_ocr_models import main

    assert main(["--check"]) == 0
