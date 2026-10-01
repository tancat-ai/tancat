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
| rapidocr-onnxruntime | 1.4.4 | Apache-2.0 | tier-1 CPU OCR engine |
| onnxruntime | 1.29.0 | MIT | ONNX inference runtime (transitive) |
| opencv-python | 5.0.0.93 | Apache-2.0 | image ops. **Note:** the PyPI wheel can bundle FFmpeg; the OpenCV project is Apache-2.0, the bundled FFmpeg build is the thing to re-check if OpenCV is ever used beyond OCR | 
| numpy | 2.5.3 | BSD-3-Clause | arrays (transitive) |
| pyclipper | 1.4.0 | MIT | polygon clipping (transitive) |
| shapely | 2.1.2 | BSD-3-Clause | geometry (transitive) |

Both extras are installed in the product image (`Dockerfile`, `uv sync --extra
pdf --extra ocr`).

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
uv pip show pypdfium2 pdfplumber rapidocr-onnxruntime   # installed metadata
```

The authoritative source is each package's PyPI page (license field /
classifiers) and the upstream repository LICENSE. Re-check on every upgrade.
