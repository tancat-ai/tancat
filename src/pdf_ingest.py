"""PDF ingestion pipeline — extract text, headings, and tables from PDFs into DocChunks.

Uses the licence-clean reader: pdfplumber for page text, font-size heading
detection and tables, and pypdfium2 for page rendering in the OCR path.  PyMuPDF
was removed on 2026-10-01 (AGPL-3.0 / paid Artifex).  Handles:
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
from typing import Any

from src.rag_store import DocChunk

logger = logging.getLogger(__name__)


#: How to install the PDF reader.  One string, so the UI, the CLI and the
#: pipeline cannot drift on what to tell a user who needs it.
PDF_READER_INSTALL_HINT = "uv sync --extra pdf (or pip install pypdfium2 pdfplumber)"

#: The libraries the ``[pdf]`` extra provides.  Both must be importable.
PDF_READER_PACKAGES: tuple[str, ...] = ("pypdfium2", "pdfplumber")


def _require_pdfplumber() -> Any:
    """Lazy-import pdfplumber (page text, font-size headings, tables)."""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(f"pdfplumber is required to read PDFs. Install with: {PDF_READER_INSTALL_HINT}") from None
    return pdfplumber


def _require_pdfium() -> Any:
    """Lazy-import pypdfium2 (page count, labels, rendering)."""
    try:
        import pypdfium2
    except ImportError:
        raise ImportError(f"pypdfium2 is required to read PDFs. Install with: {PDF_READER_INSTALL_HINT}") from None
    return pypdfium2


def render_page_png(filepath: Path, page_number: int, out_path: Path, *, dpi: int = 300) -> bool:
    """Render one PDF page (1-indexed) to a PNG.

    Returns False when the page is out of range.  The OCR backends use this to
    rasterise a page for RapidOCR / the vision model - PyMuPDF did this before
    the 2026-10-01 licence-clean swap.
    """
    pdfium = _require_pdfium()
    doc = pdfium.PdfDocument(str(filepath))
    try:
        if page_number < 1 or page_number > len(doc):
            return False
        bitmap = doc[page_number - 1].render(scale=dpi / 72)
        bitmap.to_pil().save(str(out_path), format="PNG")
        return True
    finally:
        doc.close()


def render_all_pages_png(filepath: Path, out_dir: Path, *, dpi: int = 300) -> list[Path]:
    """Render every page of a PDF to ``out_dir/page_NNNN.png``.

    Returns the written paths in page order.
    """
    pdfium = _require_pdfium()
    doc = pdfium.PdfDocument(str(filepath))
    paths: list[Path] = []
    try:
        for index in range(len(doc)):
            out = out_dir / f"page_{index + 1:04d}.png"
            bitmap = doc[index].render(scale=dpi / 72)
            bitmap.to_pil().save(str(out), format="PNG")
            paths.append(out)
        return paths
    finally:
        doc.close()


def _page_labels(filepath: Path, page_count: int) -> list[str]:
    """Printed page labels for a PDF (e.g. "5"), or empty strings.

    Best-effort: a PDF without labels, or a missing pypdfium2, yields empty
    strings and ingestion continues.
    """
    try:
        pdfium = _require_pdfium()
        doc = pdfium.PdfDocument(str(filepath))
    except Exception:
        return [""] * page_count
    try:
        labels: list[str] = []
        for index in range(page_count):
            try:
                labels.append(doc.get_page_label(index) or "")
            except Exception:
                labels.append("")
        return labels
    finally:
        doc.close()


def pdf_reader_available() -> bool:
    """Whether both PDF-reader libraries can be imported in this environment.

    ``find_spec`` does not import them, so the UI can ask without paying the
    import cost or risking a raise.  This is the honest capability check.
    """
    import importlib.util

    return all(importlib.util.find_spec(pkg) is not None for pkg in PDF_READER_PACKAGES)


def pdf_reader_missing_message() -> str:
    """Plain sentence for the UI: what is missing and how to install it."""
    import importlib.util

    missing = [pkg for pkg in PDF_READER_PACKAGES if importlib.util.find_spec(pkg) is None]
    names = ", ".join(missing) if missing else ", ".join(PDF_READER_PACKAGES)
    return (
        "This build cannot read PDFs - document mode has no PDF reader: "
        f"missing {names}. Install with `{PDF_READER_INSTALL_HINT}`."
    )


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


def _extract_headings(page: Any) -> list[tuple[float, str]]:
    """Return heading candidates sorted by vertical position (y coordinate).

    ``page`` is a pdfplumber page.  Each result is ``(y_position, text)``; a
    line is a heading when its largest font size is at or above
    :data:`HEADING_MIN_SIZE`.  Duplicates within the same vertical band (2 px)
    are collapsed, keeping the longer text.
    """
    candidates: list[tuple[float, str]] = []

    for line in page.extract_text_lines():
        chars = line.get("chars") or []
        text = (line.get("text") or "").strip()
        if not chars or not text:
            continue
        size = max(float(c.get("size", 0) or 0) for c in chars)
        if size >= HEADING_MIN_SIZE:
            candidates.append((float(line.get("bottom", 0.0) or 0.0), text))

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
    page_text: str,
    headings: list[tuple[float, str]],
) -> str:
    """Inject heading markers into page text.

    Headings detected by font size are prefixed with ``## `` so the
    downstream chunking logic can split on them.
    """
    if not headings:
        return page_text

    result = page_text
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


def _extract_tables_page(page: Any) -> list[str]:
    """Extract tables from a pdfplumber page as markdown strings.

    Returns empty list if no tables found.  Each table is a single
    markdown string kept whole (never split across chunks).
    """
    try:
        extracted_tables = page.extract_tables()
    except Exception:
        # Some PDFs don't support table detection; skip silently.
        return []

    markdown_tables: list[str] = []
    for extracted in extracted_tables:
        if not extracted:
            continue
        try:
            md_lines: list[str] = []

            # Header row
            header = extracted[0]
            md_lines.append("| " + " | ".join(_md_cell(_cell_str(c)) for c in header) + " |")
            md_lines.append("| " + " | ".join("---" for _ in header) + " |")

            # Data rows
            for row in extracted[1:]:
                # Pad row to header width if uneven
                padded = list(row) + [""] * (len(header) - len(row))
                md_lines.append("| " + " | ".join(_md_cell(_cell_str(c)) for c in padded) + " |")

            markdown_tables.append("\n".join(md_lines))
        except Exception:
            logger.debug("Failed to extract table, skipping")
            continue

    return markdown_tables


def _cell_str(value: Any) -> str:
    """A pdfplumber cell can be None; normalise it to an empty string."""
    return "" if value is None else str(value)


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
            ``"text"`` (text layer), ``"ocr"`` (extracted via the OCR
            fallback), ``"empty"`` (page was checked via OCR but no usable
            content found — the page is genuinely blank or the OCR could not
            read it), or ``"skipped"`` (page was NOT checked — the OCR hook
            was not provided, i.e. the ``[ocr]`` extra is not installed).
            For an empty page, ``reason`` is one of ``"ocr_no_text"`` (the OCR
            hook ran but returned nothing) or ``"ocr_failed"`` (the OCR hook
            raised).  For a skipped page, ``reason`` is ``"no_engine"``.
            For text/ocr pages, ``reason`` is ``""``.  Used by the ingestion
            quality summary (AI-055) to produce a cause-differentiated
            warning.  When ``None``, no per-page reporting.

    Returns:
        List of ``DocChunk`` objects ready for ``RAGStore.add_docs()``.
    """
    source = filepath.name

    try:
        doc = _require_pdfplumber().open(str(filepath))
    except Exception:
        logger.error("Failed to open PDF: %s", filepath)
        return []

    doc_title = source.replace(".pdf", "")
    page_count = len(doc.pages)
    all_text = ""
    tables_extracted: list[str] = []

    for page_num in range(page_count):
        page = doc.pages[page_num]

        # Quick check: pages with too few characters are image-only.
        quick_text = page.extract_text() or ""
        if len(quick_text) < MIN_PAGE_CHARS:
            if ocr_fallback is not None:
                try:
                    ocr_text = ocr_fallback(filepath, page_num + 1)
                except Exception:
                    logger.warning(
                        "  %s: page %d OCR fallback failed — page empty (checked, no content)",
                        source,
                        page_num + 1,
                        exc_info=True,
                    )
                    if page_report is not None:
                        page_report.append((page_num + 1, "empty", "ocr_failed"))
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
                        "  %s: page %d OCR returned no text — page empty (checked, no content)",
                        source,
                        page_num + 1,
                    )
                    if page_report is not None:
                        page_report.append((page_num + 1, "empty", "ocr_no_text"))
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
        headings = _extract_headings(page)
        page_text = _extract_page_text_with_headings(quick_text, headings)
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
        doc = _require_pdfplumber().open(str(filepath))
    except Exception:
        logger.error("Failed to open PDF: %s", filepath)
        return []

    doc_title = source.replace(".pdf", "")
    page_count = len(doc.pages)
    all_chunks: list[DocChunk] = []
    page_labels = _page_labels(filepath, page_count)

    for page_num in range(page_count):
        page = doc.pages[page_num]
        page_index = page_num + 1  # 1-indexed
        page_label = page_labels[page_num]

        # Quick check: pages with too few characters are image-only.
        quick_text = page.extract_text() or ""
        if len(quick_text) < MIN_PAGE_CHARS:
            if ocr_fallback is not None:
                try:
                    ocr_text = ocr_fallback(filepath, page_num + 1)
                except Exception:
                    logger.warning(
                        "  %s: page %d OCR fallback failed — page empty (checked, no content)",
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
                        "  %s: page %d OCR returned no text — page empty (checked, no content)",
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
        headings = _extract_headings(page)
        page_text = _extract_page_text_with_headings(quick_text, headings)
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
