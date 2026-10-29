# Vendored OCR models (RapidOCR / PP-OCRv6, PyTorch engine)

These four files are the CPU OCR models the `rapidocr` package needs for its
**PyTorch** engine. They ship in the repo so the product never downloads a
model at runtime — the zero-egress rule.

| File | Role | Size | SHA256 |
|---|---|---|---|
| `PP-OCRv6_det_small.pth` | text detection | 9.8 MB | `fbdc74c9…d54` |
| `PP-OCRv6_rec_small.pth` | text recognition | 20.3 MB | `0107b2ad…e516` |
| `ch_ppocr_mobile_v2.0_cls_mobile.pth` | text-line angle classifier | 0.6 MB | `bfe13860…8e1` |
| `ppocrv6_dict.txt` | recognition character dictionary | 75 KB | `b5f2bfe2…c5d` |

`manifest.json` holds the full names, sizes, SHA256 digests and source URLs.

## Provenance and licence

- Source: ModelScope, repository `RapidAI/RapidOCR`, release tag `v3.10.0`
  (`torch/PP-OCRv6/...`, `torch/PP-OCRv4/cls/...`, `paddle/PP-OCRv6/rec/...`).
- Upstream weights: Baidu / PaddleOCR.
- Licence: **Apache-2.0**, compatible with this Apache-2.0 product. The
  rapidocr wheel carries the same notice in its own `MODEL_LICENSES.md`.
- Recorded in `docs/licenses/DOCUMENT_READER_LICENSES.md`.

## Why these files and not the wheel's bundled models

The `rapidocr` wheel bundles ONNX models for its `onnxruntime` engine, but the
product uses the **PyTorch** engine: only that engine has Python 3.15 wheels,
and torch already ships with the product. The torch models are not in the
wheel, so the four files above are vendored here instead.

## Refresh / verify

```bash
python scripts/maintenance/vendor_ocr_models.py          # fetch missing files, verify, write manifest
python scripts/maintenance/vendor_ocr_models.py --check  # offline verify (used by tests)
```

The script skips a file whose SHA256 already matches, so re-running it is a
no-op unless a file is missing or corrupt. Bump `RAPIDOCR_VERSION` in the
script together with the `rapidocr` pin in `pyproject.toml`.
