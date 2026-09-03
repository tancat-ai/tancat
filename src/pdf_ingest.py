"""PDF ingestion pipeline — extract text, headings, and tables from PDFs into DocChunks.

Uses PyMuPDF (fitz) for text extraction.  Handles:
- Heading detection via font-size threshold (no bookmarks required)
- Table extraction as markdown (kept whole, never split)
- Image-only pages (skipped with log warning)
- Chunking on heading boundaries with configurable token target

Outputs ``DocChunk`` objects compatible with the existing ``RAGStore.add_docs()`` API.

Usage::

    from src.pdf_ingest import ingest_pdf, ingest_pdf_directory
    from src.rag_store import DocChunk

    chunks: list[DocChunk] = ingest_pdf(path_to_pdf)
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from src.rag_store import DocChunk

if TYPE_CHECKING:
    import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def _import_fitz() -> type[fitz]:
    """Lazy-import PyMuPDF.  Raises ImportError with install instructions if absent."""
    try:
        import fitz as _fitz  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError("PyMuPDF (fitz) is required for PDF ingestion. Install with: pip install PyMuPDF") from None
    return _fitz  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum font size to classify a span as a heading.
# LV PDFs use 13.0 for section headings, 11.0 for body text.
HEADING_MIN_SIZE: float = 11.5

# Target token count per chunk (~500 tokens = ~2000 chars).
CHUNK_TARGET_CHARS: int = 2000

# Overlap between consecutive sub-chunks (chars).
CHUNK_OVERLAP_CHARS: int = 250

# Minimum characters on a page before we process it.
# Filters out image-only or blank pages.
MIN_PAGE_CHARS: int = 10

# ---------------------------------------------------------------------------
# Token estimation (matches rag_ingest.py)
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Rough token count: character length / 4."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Dedup key (AI-045 #4) — idempotent doc re-ingestion
# ---------------------------------------------------------------------------


def _normalise_for_dedup(text: str) -> str:
    """Normalise chunk text for the dedup key.

    Collapses whitespace, strips, and lowercases so the key is stable across
    cosmetic re-extraction differences (trailing spaces, line-break placement,
    case) while still distinguishing genuinely different content.
    """
    return re.sub(r"\s+", " ", text).strip().lower()


def doc_chunk_key(chunk: DocChunk) -> str:
    """Stable dedup key for a doc chunk.

    ``sha256(source \x00 heading_path \x00 normalised_text)``.  Two chunks are
    duplicates iff source, heading path, and normalised content all match.
    The ``\x00`` separators prevent field-boundary collisions (a source ending
    in a space can't collide with a heading starting with one).
    """
    payload = f"{chunk.source}\x00{chunk.heading_path}\x00{_normalise_for_dedup(chunk.text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------


def _extract_headings(page: fitz.Page) -> list[tuple[float, str]]:
    """Return heading candidates sorted by vertical position (y coordinate).

    Each result is ``(y_position, text)``.  Duplicates within the same
    vertical band (±2 px) are collapsed.
    """
    blocks = page.get_text("dict")["blocks"]
    candidates: list[tuple[float, str]] = []

    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                size = span.get("size", 0)
                text = span.get("text", "").strip()
                if size >= HEADING_MIN_SIZE and text:
                    y = span["bbox"][3]  # bottom of bbox
                    candidates.append((y, text))

    # Sort by vertical position
    candidates.sort(key=lambda c: c[0])

    # Collapse duplicates within ±2 px vertical band
    collapsed: list[tuple[float, str]] = []
    for y, text in candidates:
        if collapsed and abs(y - collapsed[-1][0]) < 2:
            # Keep the longer text (more complete heading)
            if len(text) > len(collapsed[-1][1]):
                collapsed[-1] = (y, text)
        else:
            collapsed.append((y, text))

    return collapsed


# ---------------------------------------------------------------------------
# Text extraction with heading markers
# ---------------------------------------------------------------------------


def _extract_page_text_with_headings(
    page: fitz.Page,
) -> str:
    """Extract page text and inject heading markers.

    Headings detected by font size are prefixed with ``## `` so the
    downstream chunking logic can split on them.
    """
    headings = _extract_headings(page)
    if not headings:
        return page.get_text()

    # Get plain text
    plain_text = page.get_text()

    # Replace heading occurrences with markdown markers
    result = plain_text
    for _y, heading_text in headings:
        # Escape special regex chars in heading text
        escaped = re.escape(heading_text)
        # Only replace if not already markdown-marked
        pattern = rf"^(?:\s*{escaped}\s*$)"
        result = re.sub(pattern, f"\n## {heading_text}\n", result, flags=re.MULTILINE)

    return result


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------


def _extract_tables_page(page: fitz.Page) -> list[str]:
    """Extract tables from a page as markdown strings.

    Returns empty list if no tables found.  Each table is a single
    markdown string kept whole (never split across chunks).
    """
    try:
        tables = page.find_tables()
    except Exception:
        # Some PDFs don't support table detection; skip silently.
        return []

    markdown_tables: list[str] = []
    for table in tables.tables:
        try:
            # Extract as list of lists first
            extracted = table.extract()
            if not extracted:
                continue

            # Convert to markdown
            md_lines: list[str] = []

            # Header row
            header = extracted[0]
            md_lines.append("| " + " | ".join(_md_cell(str(c)) for c in header) + " |")
            md_lines.append("| " + " | ".join("---" for _ in header) + " |")

            # Data rows
            for row in extracted[1:]:
                # Pad row to header width if uneven
                padded = list(row) + [""] * (len(header) - len(row))
                md_lines.append("| " + " | ".join(_md_cell(str(c)) for c in padded) + " |")

            markdown_tables.append("\n".join(md_lines))
        except Exception:
            logger.debug("Failed to extract table, skipping")
            continue

    return markdown_tables


def _md_cell(text: str) -> str:
    """Sanitise a table cell for markdown."""
    return text.replace("\n", " ").replace("|", "\\|").strip()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _chunk_text(text: str, source: str, doc_title: str) -> list[DocChunk]:
    """Split extracted text into DocChunks.

    Strategy:
    1. Split on ``## `` heading boundaries.
    2. Sections under the target size are used as-is.
    3. Sections over the target are split at paragraph boundaries
       with overlap between consecutive sub-chunks.
    4. Tables (lines containing ``| ... |``) are never split.
    """
    chunks: list[DocChunk] = []

    # Extract document title (use source filename if no title found)
    title_match = re.match(r"^#\s+(.+)$", text, re.MULTILINE)
    if title_match:
        doc_title = title_match.group(1).strip()

    # Split on ## boundaries
    sections = re.split(r"\n(?=##\s)", text)
    sections = [s.strip() for s in sections if s.strip()]

    # Skip bare # Title sections
    sections = [s for s in sections if not re.match(r"^# .+$", s.strip())]

    for section in sections:
        heading_match = re.match(r"^##\s+(.+)$", section, re.MULTILINE)
        section_heading = heading_match.group(1).strip() if heading_match else ""
        heading_path = f"{doc_title} > {section_heading}" if section_heading else doc_title

        if len(section) <= CHUNK_TARGET_CHARS:
            chunks.append(
                DocChunk(
                    text=section,
                    source=source,
                    heading_path=heading_path,
                )
            )
            continue

        # Check if this section is a table — keep whole
        if _is_table_section(section):
            chunks.append(
                DocChunk(
                    text=section,
                    source=source,
                    heading_path=heading_path,
                )
            )
            continue

        # Split at paragraph boundaries with overlap
        paragraphs = re.split(r"\n\n+", section)
        current_text = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_text + para) > CHUNK_TARGET_CHARS and current_text:
                chunks.append(
                    DocChunk(
                        text=current_text.strip(),
                        source=source,
                        heading_path=heading_path,
                    )
                )
                # Overlap: keep last CHUNK_OVERLAP_CHARS
                current_text = current_text[-CHUNK_OVERLAP_CHARS:] + "\n\n" + para
            else:
                current_text = current_text + "\n\n" + para if current_text else para

        if current_text.strip():
            chunks.append(
                DocChunk(
                    text=current_text.strip(),
                    source=source,
                    heading_path=heading_path,
                )
            )

    return chunks


def _is_table_section(text: str) -> bool:
    """Check if a section is primarily a markdown table."""
    lines = text.strip().split("\n")
    table_lines = sum(1 for line in lines if line.startswith("|") and line.endswith("|"))
    total_lines = sum(1 for line in lines if line.strip())
    return total_lines > 0 and table_lines / total_lines > 0.5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_pdf(
    filepath: Path,
    *,
    ocr_fallback: Callable[[Path, int], str] | None = None,
    page_report: list[tuple[int, str, str]] | None = None,
) -> list[DocChunk]:
    """Ingest a single PDF file into DocChunks.

    Processes all pages, detects headings, extracts tables, and
    chunks the result.  Returns an empty list for empty/unreadable PDFs.

    Args:
        filepath: Path to the PDF file.
        ocr_fallback: Optional page-scoped OCR hook for image-only pages.
            Called as ``ocr_fallback(filepath, page_number_1indexed)`` and
            should return extracted text (may be empty).  When provided, an
            image-only page is sent to OCR instead of being skipped.  With
            AI-055 tiering the hook routes to the **tier-1 CPU OCR** (RapidOCR)
            when installed.  When the hook returns empty, the page is skipped
            with a loud WARNING.
        page_report: Optional list that receives one
            ``(page_number, outcome, reason)`` tuple per page, where outcome is
            ``"text"`` (PyMuPDF text), ``"ocr"`` (extracted via the OCR
            fallback), or ``"skipped"`` (image-only, no OCR text).  For a
            skipped page, ``reason`` is one of ``"no_engine"`` (the OCR hook
            was not provided — the ``[ocr]`` extra is not installed),
            ``"ocr_no_text"`` (the OCR hook ran but could not read the page),
            or ``"ocr_failed"`` (the OCR hook raised).  For text/ocr pages,
            ``reason`` is ``""``.  Used by the ingestion quality summary
            (AI-055) to produce a cause-differentiated warning.  When ``None``,
            no per-page reporting.

    Returns:
        List of ``DocChunk`` objects ready for ``RAGStore.add_docs()``.
    """
    source = filepath.name

    try:
        doc = _import_fitz().open(str(filepath))
    except Exception:
        logger.error("Failed to open PDF: %s", filepath)
        return []

    doc_title = source.replace(".pdf", "")
    page_count = doc.page_count
    all_text = ""
    tables_extracted: list[str] = []

    for page_num in range(page_count):
        page = doc[page_num]

        # Quick check: pages with too few characters are image-only.
        quick_text = page.get_text()
        if len(quick_text) < MIN_PAGE_CHARS:
            if ocr_fallback is not None:
                try:
                    ocr_text = ocr_fallback(filepath, page_num + 1)
                except Exception:
                    logger.warning(
                        "  %s: page %d OCR fallback failed — page skipped",
                        source,
                        page_num + 1,
                        exc_info=True,
                    )
                    if page_report is not None:
                        page_report.append((page_num + 1, "skipped", "ocr_failed"))
                    continue
                if ocr_text and ocr_text.strip():
                    all_text += ocr_text.strip() + "\n\n"
                    logger.info(
                        "  %s: page %d extracted via OCR (%d chars)",
                        source,
                        page_num + 1,
                        len(ocr_text.strip()),
                    )
                    if page_report is not None:
                        page_report.append((page_num + 1, "ocr", ""))
                else:
                    logger.warning(
                        "  %s: page %d OCR returned no text — page skipped",
                        source,
                        page_num + 1,
                    )
                    if page_report is not None:
                        page_report.append((page_num + 1, "skipped", "ocr_no_text"))
            else:
                logger.warning(
                    "  %s: page %d skipped (%d chars, likely image-only). "
                    "Install the [ocr] extra (rapidocr_onnxruntime) or set "
                    "OCR_BACKEND=cpu to extract scanned pages on CPU.",
                    source,
                    page_num + 1,
                    len(quick_text),
                )
                if page_report is not None:
                    page_report.append((page_num + 1, "skipped", "no_engine"))
            continue

        # Extract text with heading markers
        page_text = _extract_page_text_with_headings(page)
        all_text += page_text + "\n\n"
        if page_report is not None:
            page_report.append((page_num + 1, "text", ""))

        # Extract tables
        page_tables = _extract_tables_page(page)
        if page_tables:
            tables_extracted.extend(page_tables)

    doc.close()

    chunks: list[DocChunk] = []

    # Chunk the main text
    if all_text.strip():
        chunks.extend(_chunk_text(all_text, source, doc_title))

    # Add tables as standalone chunks
    for table_md in tables_extracted:
        chunks.append(
            DocChunk(
                text=table_md,
                source=source,
                heading_path=f"{doc_title} > table",
            )
        )

    # Compute the dedup key for every chunk so re-ingestion is idempotent
    # (AI-045 #4).  RAGStore.add_docs skips chunks whose key already exists.
    for chunk in chunks:
        chunk.dedup_key = doc_chunk_key(chunk)

    logger.info("  %s → %d chunk(s) from %d pages", source, len(chunks), page_count)
    return chunks


def ingest_pdf_page_aware(
    filepath: Path,
    *,
    ocr_fallback: Callable[[Path, int], str] | None = None,
) -> list[DocChunk]:
    """Ingest a single PDF into page-tagged DocChunks (16b Phase 2).

    Unlike :func:`ingest_pdf` which concatenates all pages into one text
    blob and loses page boundaries, this function chunks **per page** so
    every ``DocChunk`` carries its physical PDF page index and printed
    page label.  This is the foundation for whole-document generation
    with page-level citations.

    Args:
        filepath: Path to the PDF file.
        ocr_fallback: Optional page-scoped OCR hook for image-only pages.
            Called as ``ocr_fallback(filepath, page_number_1indexed)``.

    Returns:
        List of ``DocChunk`` objects with ``page``, ``page_label``, and
        ``route`` fields populated for every chunk.
    """
    source = filepath.name

    try:
        doc = _import_fitz().open(str(filepath))
    except Exception:
        logger.error("Failed to open PDF: %s", filepath)
        return []

    doc_title = source.replace(".pdf", "")
    page_count = doc.page_count
    all_chunks: list[DocChunk] = []

    for page_num in range(page_count):
        page = doc[page_num]
        page_index = page_num + 1  # 1-indexed
        # Get the printed page label (e.g. "5") if the PDF has one
        page_label = ""
        try:
            page_label = page.get_label() or ""
        except Exception:
            pass

        # Quick check: pages with too few characters are image-only.
        quick_text = page.get_text()
        if len(quick_text) < MIN_PAGE_CHARS:
            if ocr_fallback is not None:
                try:
                    ocr_text = ocr_fallback(filepath, page_num + 1)
                except Exception:
                    logger.warning(
                        "  %s: page %d OCR fallback failed — page skipped",
                        source,
                        page_num + 1,
                        exc_info=True,
                    )
                    continue
                if ocr_text and ocr_text.strip():
                    # OCR route — chunk this page's text with route="ocr"
                    page_chunks = _chunk_text(
                        ocr_text.strip(),
                        source,
                        doc_title,
                    )
                    for chunk in page_chunks:
                        chunk.page = page_index
                        chunk.page_label = page_label
                        chunk.route = "ocr"
                        chunk.dedup_key = doc_chunk_key(chunk)
                    all_chunks.extend(page_chunks)
                else:
                    logger.warning(
                        "  %s: page %d OCR returned no text — page skipped",
                        source,
                        page_num + 1,
                    )
            else:
                logger.warning(
                    "  %s: page %d skipped (%d chars, likely image-only).",
                    source,
                    page_num + 1,
                    len(quick_text),
                )
            continue

        # Extract text with heading markers
        page_text = _extract_page_text_with_headings(page)
        if not page_text.strip():
            continue

        # Chunk this page's text with route="text"
        page_chunks = _chunk_text(
            page_text,
            source,
            doc_title,
        )
        for chunk in page_chunks:
            chunk.page = page_index
            chunk.page_label = page_label
            chunk.route = "text"
            chunk.dedup_key = doc_chunk_key(chunk)
        all_chunks.extend(page_chunks)

    doc.close()

    logger.info(
        "  %s → %d page-tagged chunk(s) from %d pages (16b page-aware)",
        source,
        len(all_chunks),
        page_count,
    )
    return all_chunks


def ingest_pdf_directory(
    directory: Path,
    *,
    ocr_fallback: Callable[[Path, int], str] | None = None,
    page_report: list[tuple[str, int, str, str]] | None = None,
) -> list[DocChunk]:
    """Ingest all PDFs in a directory.

    Args:
        directory: Path to a directory containing PDF files.
        ocr_fallback: Page-scoped OCR hook threaded through to
            :func:`ingest_pdf` for each file (see its docstring).
        page_report: Optional list that receives one
            ``(source_name, page_number, outcome, reason)`` tuple per page
            across all files (AI-055 ingestion quality summary).  ``outcome``
            and ``reason`` have the same meaning as in :func:`ingest_pdf` —
            for a skipped page, ``reason`` is ``"no_engine"`` / ``"ocr_no_text"``
            / ``"ocr_failed"``; for text/ocr pages it is ``""``.  When ``None``,
            no per-page reporting.

    Returns:
        Combined list of ``DocChunk`` objects from all PDFs.
    """
    all_chunks: list[DocChunk] = []
    pdf_files = sorted(directory.glob("*.pdf"))

    if not pdf_files:
        logger.warning("No .pdf files found in %s", directory)
        return all_chunks

    for fpath in pdf_files:
        per_file_report: list[tuple[int, str, str]] = []
        chunks = ingest_pdf(fpath, ocr_fallback=ocr_fallback, page_report=per_file_report)
        if page_report is not None:
            for page_num, outcome, reason in per_file_report:
                page_report.append((fpath.name, page_num, outcome, reason))
        all_chunks.extend(chunks)

    logger.info(
        "Loaded %d PDF chunks from %d file(s) in %s",
        len(all_chunks),
        len(pdf_files),
        directory,
    )
    return all_chunks
