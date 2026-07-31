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
