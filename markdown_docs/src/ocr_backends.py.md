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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `RapidOCRBackend` (class): Tier-1 **CPU** OCR backend (RapidOCR / PP-OCRv5-v6 via ONNX Runtime). Scanned / image-only pages are handled on **any machine, CPU-only, no network** - the new default OCR tier for the local air-gapped product (AI-055...
- `RapidOCRBackend.__init__` (method of `RapidOCRBackend`): `RapidOCRBackend.__init__() -> None`
- `RapidOCRBackend.engine_available` (method of `RapidOCRBackend`): `RapidOCRBackend.engine_available() -> bool` - Whether the CPU ONNX engine is importable (ignores the PDF library).
- `AutoOcrBackend` (class): The auto tier (AI-055 default): tier-0 PyMuPDF whole-doc + tier-1 CPU RapidOCR for image-only pages. Whole-document parsing goes through PyMuPDF (tier 0, zero OCR cost - a mostly-text PDF stays fast). Image-only p...
- `AutoOcrBackend.__init__` (method of `AutoOcrBackend`): `AutoOcrBackend.__init__() -> None`
- `UnlimitedOCRBackend.__init__` (method of `UnlimitedOCRBackend`): `UnlimitedOCRBackend.__init__() -> None`
- `UnlimitedOCRBackend.engine_available` (method of `UnlimitedOCRBackend`): `UnlimitedOCRBackend.engine_available() -> bool` - Whether the GPU stack is usable (ignores the PDF library). Supports NVIDIA CUDA and AMD ROCm (via HIP).
- `OcrBackendUnavailableError` (class): An OCR backend was requested that this build cannot run. Raised instead of silently substituting a weaker engine. The message names the requested backend, where the request came from, why it cannot run, and the fix.
- `configured_ocr_backend_error` (function): `configured_ocr_backend_error() -> str | None` - The refusal line for the *configured* backend, or None when it can run. The UI calls this at startup so a bad OCR_BACKEND value or a stale saved setting is shown before a document is parsed, not discovered when th...


## How It Works (Internals)

Private `_`-helpers - the module's real logic (7 items). Grouped under the public function that calls them.

### `PyMuPDFBackend.available() -> bool` - method of `PyMuPDFBackend`

- `_pdf_library_available() -> bool` (function): Whether the PDF library (PyMuPDF, fitz) is importable here. Every backend in this module opens a PDF page or reads its text, so without fitz none of them can do its job. This delegates to :func:'src.pdf_ingest...

### `RapidOCRBackend.parse_page(path: str | Path, page_number: int) -> str` - method of `RapidOCRBackend`

- `_ensure_engine() -> Any` (method of `RapidOCRBackend`): Lazy-load the ONNX OCR engine on first use.
- `_result_to_text(result: Any) -> str` (method of `RapidOCRBackend`): Convert a RapidOCR result to plain text. RapidOCR 1.4.x returns (results, elapse), where each row of results is [box, text, score]. Older builds returned (boxes, texts, scores). Both shapes (and a dict...

### `UnlimitedOCRBackend.parse_pdf(path: str | Path) -> str` - method of `UnlimitedOCRBackend`

- `_ensure_model() -> None` (method of `UnlimitedOCRBackend`): Lazy-load the model on first use.

### `UnlimitedOCRBackend.parse_page(path: str | Path, page_number: int) -> str` - method of `UnlimitedOCRBackend`

- `_collect_output_text(output_dir: Path) -> str` (method of `UnlimitedOCRBackend`): Collect text from Unlimited-OCR output files. The model writes .mmd (markdown) and .txt files. Prefers .mmd for structured output, falls back to .txt.

### `configured_ocr_backend_error() -> str | None` - function

- `_configured_backend_name() -> tuple[str, str]` (function): Return (name, source) for the configured backend. Same order as :func:'get_ocr_backend' with no argument: the persisted setting wins, then OCR_BACKEND, then auto.
- `_unavailable_line(name: str, source: str) -> str | None` (function): The refusal line for *name*, or None when this build can run it. Never raises. auto is always available: it is the documented best-effort tier that reads text directly and uses CPU OCR when present. An explicit re...
