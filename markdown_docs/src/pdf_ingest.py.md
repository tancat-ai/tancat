# `src/pdf_ingest.py` — PDF Ingestion Pipeline (AI-030)

## Purpose
Extracts text, headings, and tables from PDFs into `DocChunk` objects for RAG ingestion. Uses PyMuPDF (fitz) for text extraction.

## Features
- Heading detection via font-size threshold (no bookmarks required)
- Table extraction as Markdown (kept whole, never split)
- Image-only pages: page-scoped OCR fallback when an `ocr_fallback` hook is
  supplied; otherwise skipped with a loud WARNING hinting at
  `OCR_BACKEND=unlimited-ocr` (AI-045 #4)
- Chunking on heading boundaries with configurable token target
- Stable **dedup key** computed per chunk so re-ingestion is idempotent (AI-045 #4)

## Functions
- `ingest_pdf(path: Path, *, ocr_fallback: Callable[[Path, int], str] | None = None, page_report: list[tuple[int, str, str]] | None = None) -> list[DocChunk]` — extract single PDF; `ocr_fallback` is called for image-only pages; `page_report` receives one `(page_number, outcome, reason)` tuple per page (AI-055 quality summary)
- `ingest_pdf_directory(directory: Path, *, ocr_fallback: Callable[[Path, int], str] | None = None, page_report: list[tuple[str, int, str, str]] | None = None) -> list[DocChunk]` — extract all PDFs in directory (threads `ocr_fallback` and `page_report` through)
- `doc_chunk_key(chunk: DocChunk) -> str` — stable sha256 dedup key (`source \x00 heading_path \x00 normalised_text`)
- `_normalise_for_dedup(text: str) -> str` — collapse whitespace + strip + lower (for the dedup key)

## Related
- `src/rag_store.py` — `DocChunk` consumer
- `scripts/rag_ingest.py` — CLI entry point with `--pdfs` flag
- `src/ocr_backends.py` — `PyMuPDFBackend` delegates to this

## How It Works (Internals)

Private `_`-helpers — the module's real logic (6 items). Grouped under the public function that uses them:

### `ingest_pdf`
- `_chunk_text(text: str, source: str, doc_title: str) -> list[DocChunk]` (function) — Split extracted text into DocChunks.
- Image-only page branch: when `ocr_fallback` is set, an image-only page is
  sent to `ocr_fallback(path, page_number)` and the returned text is merged in;
  an empty result or exception logs a WARNING and skips the page. When
  `ocr_fallback` is `None`, the page is skipped with a WARNING naming the
  `unlimited-ocr` opt-in. Every returned chunk is stamped with its
  `dedup_key` (via `doc_chunk_key`) before the list is returned.
- `_extract_page_text_with_headings(page: fitz.Page) -> str` (function) — Extract page text and inject heading markers.
- `_extract_tables_page(page: fitz.Page) -> list[str]` (function) — Extract tables from a page as markdown strings.
- `_import_fitz() -> type[fitz]` (function) — Lazy-import PyMuPDF.  Raises ImportError with install instructions if absent.

### Internal utilities
- `_extract_headings(page: fitz.Page) -> list[tuple[float, str]]` (function) — Return heading candidates sorted by vertical position (y coordinate).
- `_is_table_section(text: str) -> bool` (function) — Check if a section is primarily a markdown table.

## Page Report Outcome Semantics (AI-055)

`page_report` receives one tuple per page. The `outcome` field distinguishes what happened to each page:

| Outcome | Meaning | Reason |
|---------|---------|--------|
| `"text"` | Page checked via PyMuPDF, content found | `""` |
| `"ocr"` | Page checked via OCR fallback, content found | `""` |
| `"empty"` | Page **was checked** via OCR but no usable content found (genuinely blank or unreadable) | `"ocr_no_text"` or `"ocr_failed"` |
| `"skipped"` | Page was **NOT checked** at all (no OCR engine available) | `"no_engine"` |

The distinction between `"empty"` and `"skipped"` matters for the CI regression
test (`test_lv_docs_no_pages_skipped_regression`): it asserts 0 `"skipped"`
(0 pages not checked) while allowing `"empty"` pages. A blank page is checked
(OCR ran) → `"empty"`. A lost content page (no engine) → `"skipped"` → test
goes red.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `render_page_png` (function): `render_page_png(filepath: Path, page_number: int, out_path: Path, *, dpi: int = 300) -> bool` - Render one PDF page (1-indexed) to a PNG. Returns False when the page is out of range. The OCR backends use this to rasterise a page for RapidOCR / the vision model - PyMuPDF did this before the 2026-10-01 licence-cle...
- `render_all_pages_png` (function): `render_all_pages_png(filepath: Path, out_dir: Path, *, dpi: int = 300) -> list[Path]` - Render every page of a PDF to out_dir/page_NNNN.png. Returns the written paths in page order.
- `pdf_reader_available` (function): `pdf_reader_available() -> bool` - Whether both PDF-reader libraries can be imported in this environment. find_spec does not import them, so the UI can ask without paying the import cost or risking a raise. This is the honest capability check.
- `pdf_reader_missing_message` (function): `pdf_reader_missing_message() -> str` - Plain sentence for the UI: what is missing and how to install it.
- `ingest_pdf_page_aware` (function): `ingest_pdf_page_aware(filepath: Path, *, ocr_fallback: Callable[[Path, int], str] | None = None) -> list[DocChunk]` - Ingest a single PDF into page-tagged DocChunks (16b Phase 2). Unlike :func:'ingest_pdf' which concatenates all pages into one text blob and loses page boundaries, this function chunks **per page** so every DocChunk'...
- `PDF_READER_INSTALL_HINT` (constant): `PDF_READER_INSTALL_HINT = 'uv sync --extra pdf (or pip install pypdfium2 pdfplumber)'`
- `PDF_READER_PACKAGES` (constant): `PDF_READER_PACKAGES = ('pypdfium2', 'pdfplumber')`
- `HEADING_MIN_SIZE` (constant): `HEADING_MIN_SIZE = 11.5`
- `CHUNK_TARGET_CHARS` (constant): `CHUNK_TARGET_CHARS = 2000`
- `CHUNK_OVERLAP_CHARS` (constant): `CHUNK_OVERLAP_CHARS = 250`
- `MIN_PAGE_CHARS` (constant): `MIN_PAGE_CHARS = 10`


### Additional helpers (docs refresh 2026-10-02)

Private helpers with real logic not listed above.

### `ingest_pdf(filepath: Path, *, ocr_fallback: Callable[[Path, int], str] | None = None, page_report: list[tuple[int, str, str]] | None = None) -> list[DocChunk]` - function

- `_require_pdfplumber() -> Any` (function): Lazy-import pdfplumber (page text, font-size headings, tables).

### `render_page_png(filepath: Path, page_number: int, out_path: Path, *, dpi: int = 300) -> bool` - function

- `_require_pdfium() -> Any` (function): Lazy-import pypdfium2 (page count, labels, rendering).

### `ingest_pdf_page_aware(filepath: Path, *, ocr_fallback: Callable[[Path, int], str] | None = None) -> list[DocChunk]` - function

- `_page_labels(filepath: Path, page_count: int) -> list[str]` (function): Printed page labels for a PDF (e.g. "5"), or empty strings. Best-effort: a PDF without labels, or a missing pypdfium2, yields empty strings and ingestion continues.
