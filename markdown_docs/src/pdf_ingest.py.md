# `src/pdf_ingest.py` — PDF Ingestion Pipeline (AI-030)

## Purpose
Extracts text, headings, and tables from PDFs into `DocChunk` objects for RAG ingestion. Uses PyMuPDF (fitz) for text extraction.

## Features
- Heading detection via font-size threshold (no bookmarks required)
- Table extraction as Markdown (kept whole, never split)
- Image-only pages skipped with log warning
- Chunking on heading boundaries with configurable token target

## Functions
- `ingest_pdf(path: Path) -> list[DocChunk]` — extract single PDF
- `ingest_pdf_directory(directory: Path) -> list[DocChunk]` — extract all PDFs in directory

## Related
- `src/rag_store.py` — `DocChunk` consumer
- `scripts/rag_ingest.py` — CLI entry point with `--pdfs` flag
- `src/ocr_backends.py` — `PyMuPDFBackend` delegates to this

## How It Works (Internals)

Private `_`-helpers — the module's real logic (6 items). Grouped under the public function that uses them:

### `ingest_pdf`
- `_chunk_text(text: str, source: str, doc_title: str) -> list[DocChunk]` (function) — Split extracted text into DocChunks.
- `_extract_page_text_with_headings(page: fitz.Page) -> str` (function) — Extract page text and inject heading markers.
- `_extract_tables_page(page: fitz.Page) -> list[str]` (function) — Extract tables from a page as markdown strings.
- `_import_fitz() -> type[fitz]` (function) — Lazy-import PyMuPDF.  Raises ImportError with install instructions if absent.

### Internal utilities
- `_extract_headings(page: fitz.Page) -> list[tuple[float, str]]` (function) — Return heading candidates sorted by vertical position (y coordinate).
- `_is_table_section(text: str) -> bool` (function) — Check if a section is primarily a markdown table.
