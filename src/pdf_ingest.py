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

import logging
import re
from pathlib import Path

import fitz  # PyMuPDF # type: ignore[import-untyped]

from src.rag_store import DocChunk

logger = logging.getLogger(__name__)

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


def ingest_pdf(filepath: Path) -> list[DocChunk]:
    """Ingest a single PDF file into DocChunks.

    Processes all pages, detects headings, extracts tables, and
    chunks the result.  Returns an empty list for empty/unreadable PDFs.

    Args:
        filepath: Path to a PDF file.

    Returns:
        List of ``DocChunk`` objects ready for ``RAGStore.add_docs()``.
    """
    source = filepath.name

    try:
        doc = fitz.open(str(filepath))
    except Exception:
        logger.error("Failed to open PDF: %s", filepath)
        return []

    doc_title = source.replace(".pdf", "")
    page_count = doc.page_count
    all_text = ""
    tables_extracted: list[str] = []

    for page_num in range(page_count):
        page = doc[page_num]

        # Quick check: skip pages with too few characters (image-only)
        quick_text = page.get_text()
        if len(quick_text) < MIN_PAGE_CHARS:
            logger.info(
                "  %s: page %d skipped (%d chars, likely image-only)",
                source,
                page_num + 1,
                len(quick_text),
            )
            continue

        # Extract text with heading markers
        page_text = _extract_page_text_with_headings(page)
        all_text += page_text + "\n\n"

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

    logger.info("  %s → %d chunk(s) from %d pages", source, len(chunks), page_count)
    return chunks


def ingest_pdf_directory(directory: Path) -> list[DocChunk]:
    """Ingest all PDFs in a directory.

    Args:
        directory: Path to a directory containing PDF files.

    Returns:
        Combined list of ``DocChunk`` objects from all PDFs.
    """
    all_chunks: list[DocChunk] = []
    pdf_files = sorted(directory.glob("*.pdf"))

    if not pdf_files:
        logger.warning("No .pdf files found in %s", directory)
        return all_chunks

    for fpath in pdf_files:
        chunks = ingest_pdf(fpath)
        all_chunks.extend(chunks)

    logger.info(
        "Loaded %d PDF chunks from %d file(s) in %s",
        len(all_chunks),
        len(pdf_files),
        directory,
    )
    return all_chunks
