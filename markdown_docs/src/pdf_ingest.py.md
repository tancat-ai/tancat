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
- `ingest_pdf(path: Path, *, ocr_fallback: Callable[[Path, int], str] | None = None) -> list[DocChunk]` — extract single PDF; `ocr_fallback` is called for image-only pages
- `ingest_pdf_directory(directory: Path, *, ocr_fallback: Callable[[Path, int], str] | None = None) -> list[DocChunk]` — extract all PDFs in directory (threads `ocr_fallback` through)
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
