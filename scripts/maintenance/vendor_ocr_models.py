#!/usr/bin/env python3
"""Vendor the RapidOCR models the CPU OCR tier needs (t-0810).

rapidocr v3 with the PyTorch engine resolves its models from ModelScope URLs
(``rapidocr/default_models.yaml``) and downloads them on first use unless an
explicit local path is given.  The product is zero-egress, so the four files
this script fetches ship in the repo under ``src/data/ocr/`` and every path is
pinned by SHA256.  ``src/ocr_backends.py`` passes those explicit paths, so
rapidocr never builds a URL for them.

The files are Apache-2.0 (Baidu / PaddleOCR via RapidOCR); provenance and the
licence notice are recorded in ``docs/licenses/DOCUMENT_READER_LICENSES.md``.

Usage:
    python scripts/maintenance/vendor_ocr_models.py            # fetch + verify + write manifest
    python scripts/maintenance/vendor_ocr_models.py --check    # offline: verify what is on disk

Exit codes: 0 = all files present and matching; 1 = a missing/mismatched file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "src" / "data" / "ocr"
MANIFEST_PATH = MODEL_DIR / "manifest.json"

#: RapidOCR release the models and the pinned rapidocr package are taken from.
RAPIDOCR_VERSION = "3.10.0"
_BASE = f"https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v{RAPIDOCR_VERSION}"


@dataclass(frozen=True)
class ModelFile:
    name: str
    role: str
    url: str
    sha256: str
    bytes: int


MODEL_FILES: tuple[ModelFile, ...] = (
    ModelFile(
        "PP-OCRv6_det_small.pth",
        "det",
        f"{_BASE}/torch/PP-OCRv6/det/PP-OCRv6_det_small.pth",
        "fbdc74c97ea7b770ab22cbdc1bba01a52bdf1975efcf3442057356d622b05d54",
        10248727,
    ),
    ModelFile(
        "PP-OCRv6_rec_small.pth",
        "rec",
        f"{_BASE}/torch/PP-OCRv6/rec/PP-OCRv6_rec_small.pth",
        "0107b2ad694ccc9b1db7cf9ed3ffbc93d1795d9e08d9cf823127243a87bce516",
        21326017,
    ),
    ModelFile(
        "ch_ppocr_mobile_v2.0_cls_mobile.pth",
        "cls",
        f"{_BASE}/torch/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.pth",
        "bfe13860824b3365c0c7f7ccfcddc8ff11645c60051739ff18bc9913f60c98e1",
        588638,
    ),
    ModelFile(
        "ppocrv6_dict.txt",
        "dict",
        f"{_BASE}/paddle/PP-OCRv6/rec/PP-OCRv6_rec_small/ppocrv6_dict.txt",
        "b5f2bfe2bdd9448429e3e82b51c789775d9b42f2403d082b00662eb77e401c5d",
        74947,
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, model: ModelFile) -> str | None:
    """Return an error string when *path* is missing or does not match, else None."""
    if not path.is_file():
        return "missing"
    if path.stat().st_size != model.bytes:
        return f"size {path.stat().st_size} != {model.bytes}"
    actual = _sha256(path)
    if actual != model.sha256:
        return f"sha256 {actual} != {model.sha256}"
    return None


def _download(path: Path, model: ModelFile) -> None:
    print(f"downloading {model.name} ({model.bytes / 1048576:.1f} MB)")
    with urllib.request.urlopen(model.url, timeout=300) as response:
        data = response.read()
    path.write_bytes(data)


def write_manifest() -> None:
    manifest = {
        "engine": "torch",
        "rapidocr_version": RAPIDOCR_VERSION,
        "licence": "Apache-2.0",
        "source": f"{_BASE}/torch/",
        "note": "Vendored so the CPU OCR tier never downloads models at runtime (zero egress).",
        "files": [
            {
                "name": model.name,
                "role": model.role,
                "sha256": model.sha256,
                "bytes": model.bytes,
                "url": model.url,
            }
            for model in MODEL_FILES
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the vendored files offline; do not download",
    )
    args = parser.parse_args(argv)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for model in MODEL_FILES:
        path = MODEL_DIR / model.name
        error = _verify(path, model)
        if error is None:
            print(f"ok      {model.name}")
            continue
        if args.check:
            failures.append(f"{model.name}: {error}")
            print(f"FAIL    {model.name}: {error}")
            continue
        _download(path, model)
        error = _verify(path, model)
        if error is not None:
            failures.append(f"{model.name}: {error}")
            print(f"FAIL    {model.name}: {error}")
        else:
            print(f"ok      {model.name}")

    if failures:
        print("\nVendored OCR models are not usable:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    if not args.check:
        write_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
