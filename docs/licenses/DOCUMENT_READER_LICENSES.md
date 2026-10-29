# PDF reader dependencies and their licences

**Created:** 2026-10-01
**Decision:** owner, 2026-10-01 - retire PyMuPDF, ship a licence-clean reader.

This records every dependency the document reader pulls in, so the next reader
can re-check it. The product is Apache-2.0; a dependency whose licence forbids
commercial use must not be shipped.

## Why PyMuPDF was removed

`PyMuPDF` (import name `fitz`) is dual-licensed **AGPL-3.0 or a paid Artifex
commercial licence**. AGPL-3.0 is strong copyleft and conflicts with an
Apache-2.0 product, and with any proprietary release. It was declared as the
`[pdf]` extra but was not installed in the image, so the conflict was latent.
It is now removed and must not come back.

## Shipped readers

### `[pdf]` extra - text, layout, tables

| Package | Version | Licence | Role |
|---|---|---|---|
| pypdfium2 | 5.13.0 | Apache-2.0 (wrapper) + BSD-3-Clause (PDFium) | text extraction, page render, page count/labels |
| pdfplumber | 0.11.10 | MIT | font-size heading detection, table structure |
| pdfminer.six | 20260107 | MIT | pdfplumber's text/layout engine (transitive) |
| Pillow | 12.3.0 | MIT-CMU (HPND) | image objects from the render path (transitive) |
| charset-normalizer | 3.4.9 | MIT | encoding detection (transitive) |

### `[ocr]` extra - scanned / image-only pages

| Package | Version | Licence | Role |
|---|---|---|---|
| rapidocr | 3.10.0 | Apache-2.0 | tier-1 CPU OCR engine (PP-OCRv6, **PyTorch** engine) |
| omegaconf | 2.4.0 | BSD-3-Clause | rapidocr configuration (transitive) |
| colorlog | 6.12.0 | MIT | rapidocr logging (transitive) |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | image ops, server/headless build (no GUI libraries). **Note:** the PyPI wheel can bundle FFmpeg; the OpenCV project is Apache-2.0, the bundled FFmpeg build is the thing to re-check if OpenCV is ever used beyond OCR | 
| numpy | 2.5.3 | BSD-3-Clause | arrays (transitive) |
| pyclipper | 1.4.0 | MIT | polygon clipping (transitive) |
| shapely | 2.1.2 | BSD-3-Clause | geometry (transitive) |

The PyTorch engine uses `torch` (2.14.1, Apache-2.0), which is already a base
dependency; `onnxruntime` left with the retired `rapidocr-onnxruntime` engine.

### Vendored OCR models (2026-10-13)

The CPU OCR tier (RapidOCR/PP-OCRv6 on the **PyTorch** engine) ships its models
in the repo at `src/data/ocr/` - they are not downloaded at runtime. rapidocr
would otherwise fetch them from ModelScope, which breaks the zero-egress rule.

| File | Role | Size | Licence |
|---|---|---|---|
| `PP-OCRv6_det_small.pth` | text detection | 9.8 MB | Apache-2.0 (Baidu / PaddleOCR) |
| `PP-OCRv6_rec_small.pth` | text recognition | 20.3 MB | Apache-2.0 (Baidu / PaddleOCR) |
| `ch_ppocr_mobile_v2.0_cls_mobile.pth` | text-line angle classifier | 0.6 MB | Apache-2.0 (Baidu / PaddleOCR) |
| `ppocrv6_dict.txt` | recognition character dictionary | 75 KB | Apache-2.0 (Baidu / PaddleOCR) |

Provenance: ModelScope, repository `RapidAI/RapidOCR`, tag `v3.10.0` (the same
tag the pinned rapidocr package ships). Each file's SHA256 is in
`src/data/ocr/manifest.json`; `src/ocr_backends.py` passes explicit local paths
so rapidocr never builds a model URL. Refresh or verify with
`python scripts/maintenance/vendor_ocr_models.py` (`--check` is offline).
The rapidocr wheel carries the same upstream notice in its own
`MODEL_LICENSES.md`.

Both extras are installed in the product image (`Dockerfile`, `uv sync --extra
pdf --extra ocr`).

### OpenCV: headless, not the GUI build (2026-10-01)

RapidOCR declares a dependency on `opencv-python` (the GUI build). The product
is a server, so the `[ocr]` extra ships **`opencv-python-headless`** instead
(owner direction, 2026-10-01). It provides the same `cv2` module without the
GUI libraries.

How: `[tool.uv] override-dependencies` in `pyproject.toml` overrides the
`opencv-python` requirement away (a never-true marker), and the `[ocr]` extra
adds `opencv-python-headless`. Measured cost:

| Build | Linux x86_64 wheel | Note |
|---|---|---|
| opencv-python (GUI) | 67.8 MB | pulls GUI runtime libraries |
| opencv-python-headless | 53.9 MB | same `cv2`, no GUI libs |

That is **~14 MB smaller compressed**, and the image saving is larger again
because the GUI runtime libraries are no longer needed.

## Runtime-downloaded model - the optional GPU OCR backend

The tier-3 GPU OCR backend is a Hugging Face model fetched at runtime on first
use, not a build dependency, so `uv.lock` and the generated
`docs/licenses/DEPENDENCIES.md` cannot see it. It is recorded here instead. The
in-product label is generic ("GPU OCR"), but a licence record must name what it
licences.

| Model | Fetched by | Licence | Attribution |
|---|---|---|---|
| `baidu/Unlimited-OCR` | the optional GPU OCR backend, only when `OCR_BACKEND=power` is set (needs CUDA/ROCm) | MIT | Copyright (c) 2026 Baidu. Base models are Apache-2.0. |

**Why MIT, not Apache-2.0.** The upstream GitHub `LICENSE` reads "Copyright (c)
2026 Baidu" under the MIT licence, and the Hugging Face model card declares
`license: mit`. Its base models are Apache-2.0. MIT is permissive and compatible
with this product's Apache-2.0 licence.

**Do not** replace the tier-3 model with one from the "Blocked" list below
(non-commercial or AGPL) without re-checking this file. Re-check when tier 3 is
re-picked (see `docs/specs/FEATURE_SPEC_ingestion_local.md`).

## Optional, proposed only (not shipped)

Named here per the research (t-0185) recommendation; neither is added.

| Candidate | Weights | Licence | Note |
|---|---|---|---|
| Granite-Docling 258M | ~0.5 GB | Apache-2.0 | CPU-capable layout/tables; would need offline vendoring |
| LightOnOCR 2 1B | ~2.0 GB | Apache-2.0 | CPU-capable, better table/scan quality |

## Blocked - do not ship

Jina VLM (CC-BY-NC-4.0), OCRFlux 3B and Dolphin v2 (Qwen Research,
non-commercial), MinerU 2.5 (AGPL-3.0), Chandra (restricted OpenRAIL-M),
Nanonets OCR2 (no declared licence), HunyuanOCR (Tencent community terms),
PyMuPDF (AGPL-3.0 / Artifex commercial).

## How to re-check

```bash
uv pip show pypdfium2 pdfplumber rapidocr   # installed metadata
```

The authoritative source is each package's PyPI page (license field /
classifiers) and the upstream repository LICENSE. Re-check on every upgrade.
