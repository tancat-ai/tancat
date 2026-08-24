# `src/ocr_backends.py` — OCR Backend Adapter (Phase 1i)

## Purpose

Pluggable backend interface for PDF → text conversion in the document parsing pipeline node. Provides two backends selectable via the `OCR_BACKEND` environment variable.

## Architecture

```
OcrBackend (ABC)
├── PyMuPDFBackend      ← default, CPU, zero deps
└── UnlimitedOCRBackend ← GPU, 3B vision model (Baidu)
```

## Classes

### `OcrBackend` (ABC)
Abstract interface with three methods:

- `parse_pdf(path: str | Path) -> str` — convert PDF to plain text
- `parse_markdown(path: str | Path) -> str` — read Markdown directly
- `parse_page(path: str | Path, page_number: int) -> str` — OCR a single page (1-indexed); default returns `""` (no page-level OCR). Used by the production ingest path for image-only pages (AI-045 #4).
- `name: str` (property) — human-readable backend name
- `available: bool` (property) — whether this backend works in current environment

### `PyMuPDFBackend`
Default CPU backend. Delegates to `src/pdf_ingest.ingest_pdf()` for PDFs (heading detection, table extraction, chunking). Reads Markdown files directly.

### `UnlimitedOCRBackend`
GPU-accelerated backend using Baidu's `baidu/Unlimited-OCR` 3B vision-language model. Renders PDF pages to 300 DPI PNGs via PyMuPDF, then feeds to `model.infer_multi()` for single-pass multi-page OCR. Supports CUDA and ROCm (via HIP). Model is lazily loaded on first `parse_pdf()` call (~6 GB download from Hugging Face).

Key methods:
- `_ensure_model() -> None` — lazy-load tokenizer + model, detects bfloat16/float16
- `parse_pdf(path) -> str` — render → OCR → collect `.mmd`/`.txt` output
- `parse_page(path, page_number) -> str` — rasterise just that page at 300 DPI and OCR the single image (cheaper than a whole-document pass); used for image-only-page fallback
- `_collect_output_text(output_dir) -> str` — static; prefers `.mmd`, falls back to `.txt`

## Factory

### `get_ocr_backend(backend_name: str | None = None) -> OcrBackend`
Reads `OCR_BACKEND` env var. Falls back to `PyMuPDFBackend` if requested backend is unavailable (e.g., no GPU). Explicit `backend_name` argument overrides env var.

## Related
- `src/pdf_ingest.py` — PyMuPDF pipeline used by the default backend
- `src/agents/pipeline_graph.py` — `_parse_document()` node calls `get_ocr_backend()`
- Phase 1i spec: `docs/specs/FEATURE_SPEC_phase1_multi_agent.md` §9
