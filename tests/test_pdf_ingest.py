"""Unit tests for src/pdf_ingest.py — PDF text extraction and chunking.

Reader layer (2026-10-01): pypdfium2 + pdfplumber replaced PyMuPDF.  The
reader-dependent tests use fake pdfplumber pages/documents so they run without a
real PDF writer; the integration tests use the real LV docs in
``docs/rag_corpus/lv_docs/``.

Covers:
- Heading detection and deduplication
- Text extraction with heading markers
- Table extraction and sanitisation
- Chunking logic (split on headings, paragraph splitting, table preservation)
- ingest_pdf / ingest_pdf_directory, including the page-scoped OCR fallback
- Dedup keys (idempotent re-ingestion)
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.pdf_ingest import (
    CHUNK_OVERLAP_CHARS,
    CHUNK_TARGET_CHARS,
    HEADING_MIN_SIZE,
    MIN_PAGE_CHARS,
    _chunk_text,
    _estimate_tokens,
    _extract_headings,
    _extract_page_text_with_headings,
    _extract_tables_page,
    _is_table_section,
    _md_cell,
    ingest_pdf,
    ingest_pdf_directory,
)
from src.rag_store import DocChunk

# ---------------------------------------------------------------------------
# Fake pdfplumber surface
# ---------------------------------------------------------------------------


def _fake_page(
    text: str = "",
    *,
    lines: list[dict[str, Any]] | None = None,
    tables: list[list[list[Any]]] | None = None,
) -> Any:
    """A fake pdfplumber page with the three methods the reader uses."""
    page = MagicMock()
    page.extract_text.return_value = text
    page.extract_text_lines.return_value = lines or []
    page.extract_tables.return_value = tables or []
    return page


def _fake_doc(pages: list[Any]) -> Any:
    """A fake pdfplumber document whose ``.pages`` is the given list."""
    doc = MagicMock()
    doc.pages = pages
    doc.close.return_value = None
    return doc


def _text_line(text: str, size: float, bottom: float) -> dict[str, Any]:
    """A fake pdfplumber text line (``extract_text_lines`` shape)."""
    return {"text": text, "bottom": bottom, "chars": [{"size": size}]}


def _patch_reader(doc: Any) -> Any:
    """Patch the reader so ``ingest_pdf`` opens *doc* instead of a real PDF."""
    fake_module = MagicMock()
    fake_module.open.return_value = doc
    return patch("src.pdf_ingest._require_pdfplumber", return_value=fake_module)


def _require_pdf_reader() -> None:
    """Skip a test that needs a real PDF reader when the ``[pdf]`` extra is absent.

    The fake-reader tests above never call this; only the tests that open a
    real PDF on disk do, so a plain ``uv sync`` (no extras) skips them instead
    of failing, and names the missing package.
    """
    pytest.importorskip("pypdfium2", reason="[pdf] extra not installed (pypdfium2)")
    pytest.importorskip("pdfplumber", reason="[pdf] extra not installed (pdfplumber)")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_text_simple() -> str:
    """Simple multi-section text."""
    return """\
# Document Title

Introduction text here.

## Section One

Content of section one with some details.

## Section Two

Content of section two with different details.

## Section Three

Final section content.
"""


@pytest.fixture
def sample_text_with_table() -> str:
    """Text containing a markdown table."""
    return """\
# Tables Document

## Coverage Limits

| Cover Type | Limit | Excess |
|---|---|---|
| Third Party | £1M | £250 |
| Comprehensive | £2M | £500 |
| Third Party Fire | £1.5M | £375 |

## Notes

Some additional notes here.
"""


@pytest.fixture
def sample_text_large_section() -> str:
    """Text with a section exceeding CHUNK_TARGET_CHARS."""
    paragraphs = "\n\n".join(
        [f"Paragraph {i} of the large section with enough text to be substantial." for i in range(30)]
    )
    return f"""\
# Large Document

## Small Section

Brief content.

## Large Section

{paragraphs}
"""


# ---------------------------------------------------------------------------
# _estimate_tokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_basic(self) -> None:
        assert _estimate_tokens("Hello world") == 2

    def test_empty(self) -> None:
        assert _estimate_tokens("") == 1

    def test_long(self) -> None:
        text = "x" * 4000
        assert _estimate_tokens(text) == 1000

    def test_four_char_boundary(self) -> None:
        assert _estimate_tokens("abcd") == 1


# ---------------------------------------------------------------------------
# _md_cell
# ---------------------------------------------------------------------------


class TestMdCell:
    def test_plain(self) -> None:
        assert _md_cell("hello") == "hello"

    def test_strips_pipe(self) -> None:
        assert _md_cell("a|b") == "a\\|b"

    def test_strips_newlines(self) -> None:
        assert _md_cell("line1\nline2") == "line1 line2"

    def test_strips_whitespace(self) -> None:
        assert _md_cell("  hello  ") == "hello"

    def test_empty(self) -> None:
        assert _md_cell("") == ""


# ---------------------------------------------------------------------------
# _is_table_section
# ---------------------------------------------------------------------------


class TestIsTableSection:
    def test_table(self) -> None:
        text = "| a | b |\n|---|---|\n| 1 | 2 |"
        assert _is_table_section(text) is True

    def test_not_table(self) -> None:
        assert _is_table_section("just some text\n\nmore text") is False

    def test_mixed(self) -> None:
        text = "Introduction\n\n| a | b |\n|---|---|\n| 1 | 2 |"
        assert _is_table_section(text) is True

    def test_empty(self) -> None:
        assert _is_table_section("") is False


# ---------------------------------------------------------------------------
# _chunk_text
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_basic_split_on_headings(self, sample_text_simple: str) -> None:
        chunks = _chunk_text(sample_text_simple, "test.md", "Test Doc")
        assert len(chunks) == 4
        assert all(isinstance(c, DocChunk) for c in chunks)

    def test_heading_paths(self, sample_text_simple: str) -> None:
        chunks = _chunk_text(sample_text_simple, "test.md", "Test Doc")
        heading_paths = [c.heading_path for c in chunks]
        assert "Document Title > Section One" in heading_paths
        assert "Document Title > Section Two" in heading_paths
        assert "Document Title > Section Three" in heading_paths

    def test_source_preserved(self, sample_text_simple: str) -> None:
        chunks = _chunk_text(sample_text_simple, "test.pdf", "Test")
        assert all(c.source == "test.pdf" for c in chunks)

    def test_table_not_split(self, sample_text_with_table: str) -> None:
        chunks = _chunk_text(sample_text_with_table, "test.md", "Test")
        table_chunks = [c for c in chunks if "Coverage Limits" in c.heading_path]
        assert len(table_chunks) == 1
        assert "|" in table_chunks[0].text

    def test_large_section_split(self, sample_text_large_section: str) -> None:
        chunks = _chunk_text(sample_text_large_section, "test.md", "Test")
        large_chunks = [c for c in chunks if "Large Section" in c.heading_path]
        assert len(large_chunks) >= 2

    def test_empty_text(self) -> None:
        chunks = _chunk_text("", "test.md", "Test")
        assert chunks == []

    def test_no_headings(self) -> None:
        text = "Just plain text without headings."
        chunks = _chunk_text(text, "test.md", "Test")
        assert len(chunks) == 1
        assert chunks[0].heading_path == "Test"


# ---------------------------------------------------------------------------
# _extract_headings (fake pdfplumber page)
# ---------------------------------------------------------------------------


class TestExtractHeadings:
    def test_detects_large_spans(self) -> None:
        page = _fake_page(lines=[_text_line("Hello", 10.0, 20), _text_line("Chapter 1", 14.0, 50)])
        headings = _extract_headings(page)
        assert len(headings) == 1
        assert headings[0][1] == "Chapter 1"

    def test_collapses_same_line(self) -> None:
        page = _fake_page(lines=[_text_line("Chapter", 14.0, 45), _text_line("Chapter 1", 14.0, 46)])
        headings = _extract_headings(page)
        assert len(headings) == 1
        assert headings[0][1] == "Chapter 1"

    def test_empty_page(self) -> None:
        assert _extract_headings(_fake_page()) == []

    def test_threshold_boundary(self) -> None:
        page = _fake_page(lines=[_text_line("Small", 11.4, 10), _text_line("Heading", 11.5, 30)])
        headings = _extract_headings(page)
        assert len(headings) == 1
        assert headings[0][1] == "Heading"


# ---------------------------------------------------------------------------
# _extract_page_text_with_headings
# ---------------------------------------------------------------------------


class TestExtractPageTextWithHeadings:
    def test_injects_heading_markers(self) -> None:
        result = _extract_page_text_with_headings(
            "Hello\nWelcome to LV=\nSome content",
            [(25.0, "Welcome to LV=")],
        )
        assert "## Welcome to LV=" in result

    def test_no_headings_is_identity(self) -> None:
        assert _extract_page_text_with_headings("plain text", []) == "plain text"


# ---------------------------------------------------------------------------
# _extract_tables_page
# ---------------------------------------------------------------------------


class TestExtractTablesPage:
    def test_table_to_markdown(self) -> None:
        page = _fake_page(tables=[[["Cover Type", "Limit"], ["Third Party", "£1M"]]])
        tables = _extract_tables_page(page)
        assert len(tables) == 1
        assert "| Cover Type | Limit |" in tables[0]
        assert "| Third Party | £1M |" in tables[0]

    def test_none_cell_becomes_empty(self) -> None:
        page = _fake_page(tables=[[["A", "B"], [None, "x"]]])
        tables = _extract_tables_page(page)
        assert "|  | x |" in tables[0]

    def test_no_tables(self) -> None:
        assert _extract_tables_page(_fake_page()) == []

    def test_extract_tables_failure_is_swallowed(self) -> None:
        page = MagicMock()
        page.extract_tables.side_effect = RuntimeError("boom")
        assert _extract_tables_page(page) == []


# ---------------------------------------------------------------------------
# ingest_pdf (integration with real PDFs)
# ---------------------------------------------------------------------------


class TestIngestPdf:
    def test_real_tcs_pdf(self) -> None:
        _require_pdf_reader()
        path = Path("docs/rag_corpus/lv_docs/35880-2023-car-tc.pdf")
        if not path.exists():
            pytest.skip("PDF not available")
        chunks = ingest_pdf(path)
        assert len(chunks) > 0
        assert all(isinstance(c, DocChunk) for c in chunks)
        assert all(c.source == "35880-2023-car-tc.pdf" for c in chunks)
        assert any("Your insurance policy" in c.heading_path for c in chunks)

    def test_real_ipid_pdf(self) -> None:
        _require_pdf_reader()
        path = Path("docs/rag_corpus/lv_docs/0042748-2025-car-ipid.pdf")
        if not path.exists():
            pytest.skip("PDF not available")
        chunks = ingest_pdf(path)
        assert len(chunks) > 0
        assert any("What is this type of insurance" in c.heading_path for c in chunks)

    def test_real_cover_limits_pdf(self) -> None:
        _require_pdf_reader()
        path = Path("docs/rag_corpus/lv_docs/40383-2025-Cover-and-limits-v4-1.pdf")
        if not path.exists():
            pytest.skip("PDF not available")
        chunks = ingest_pdf(path)
        assert len(chunks) > 0

    def test_nonexistent_file(self) -> None:
        chunks = ingest_pdf(Path("/nonexistent/file.pdf"))
        assert chunks == []

    def test_contains_insurance_terms(self) -> None:
        _require_pdf_reader()
        path = Path("docs/rag_corpus/lv_docs/35880-2023-car-tc.pdf")
        if not path.exists():
            pytest.skip("PDF not available")
        chunks = ingest_pdf(path)
        all_text = " ".join(c.text for c in chunks)
        assert "insurance" in all_text.lower()
        assert "claim" in all_text.lower()


# ---------------------------------------------------------------------------
# ingest_pdf_directory
# ---------------------------------------------------------------------------


class TestIngestPdfDirectory:
    def test_all_pdfs(self) -> None:
        _require_pdf_reader()
        directory = Path("docs/rag_corpus/lv_docs")
        if not directory.exists():
            pytest.skip("Directory not available")
        chunks = ingest_pdf_directory(directory)
        assert len(chunks) > 0
        sources = {c.source for c in chunks}
        assert "35880-2023-car-tc.pdf" in sources
        assert "0042748-2025-car-ipid.pdf" in sources
        assert "40383-2025-Cover-and-limits-v4-1.pdf" in sources

    def test_lv_docs_no_pages_skipped_regression(self) -> None:
        """CI regression guard: the LV docs have native text, so 0 pages skipped.

        ``skipped`` means the page was NOT checked (no OCR engine); ``empty``
        means it was checked and found blank.  The LV docs must lose no page.
        """
        directory = Path("docs/rag_corpus/lv_docs")
        if not directory.exists():
            pytest.skip("Directory not available")
        _require_pdf_reader()
        from src.ocr_backends import get_ocr_backend

        backend = get_ocr_backend()
        report: list[tuple[str, int, str, str]] = []
        ingest_pdf_directory(directory, ocr_fallback=backend.parse_page, page_report=report)
        skipped = [(src, page, reason) for src, page, outcome, reason in report if outcome == "skipped"]
        assert skipped == [], f"LV docs skipped pages (not checked — regression): {skipped}"
        assert len(report) > 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        assert ingest_pdf_directory(tmp_path) == []

    def test_threads_ocr_fallback_through(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """ingest_pdf_directory passes ocr_fallback to each file's ingest_pdf."""
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4 fake")
        seen: list[bool] = []

        def fake_ingest(
            path: Path,
            *,
            ocr_fallback: Callable[[Path, int], str] | None = None,
            page_report: list[tuple[int, str, str]] | None = None,
        ) -> list[DocChunk]:
            seen.append(ocr_fallback is not None)
            return []

        monkeypatch.setattr("src.pdf_ingest.ingest_pdf", fake_ingest)
        ingest_pdf_directory(tmp_path, ocr_fallback=lambda _p, _n: "")
        assert seen == [True]


# ---------------------------------------------------------------------------
# Dedup key
# ---------------------------------------------------------------------------


class TestDocChunkKey:
    """The dedup key ``sha256(source \\x00 heading_path \\x00 normalised text)``."""

    def test_same_chunk_same_key(self) -> None:
        from src.pdf_ingest import doc_chunk_key

        a = DocChunk(text="Cover section", source="a.pdf", heading_path="Cover")
        b = DocChunk(text="Cover section", source="a.pdf", heading_path="Cover")
        assert doc_chunk_key(a) == doc_chunk_key(b)
        assert doc_chunk_key(a) != ""

    def test_different_source_different_key_even_with_identical_text(self) -> None:
        from src.pdf_ingest import doc_chunk_key

        a = DocChunk(text="Same body text here", source="35880-2023-car-tc.pdf", heading_path="Cover")
        b = DocChunk(text="Same body text here", source="40383-2025-Cover-and-limits-v4-1.pdf", heading_path="Cover")
        assert doc_chunk_key(a) != doc_chunk_key(b)

    def test_different_text_different_key_same_source(self) -> None:
        from src.pdf_ingest import doc_chunk_key

        a = DocChunk(text="Section one", source="a.pdf", heading_path="One")
        b = DocChunk(text="Section two", source="a.pdf", heading_path="One")
        assert doc_chunk_key(a) != doc_chunk_key(b)

    def test_different_heading_path_different_key(self) -> None:
        from src.pdf_ingest import doc_chunk_key

        a = DocChunk(text="Body", source="a.pdf", heading_path="Intro")
        b = DocChunk(text="Body", source="a.pdf", heading_path="Conclusion")
        assert doc_chunk_key(a) != doc_chunk_key(b)

    def test_normalisation_ignores_whitespace(self) -> None:
        from src.pdf_ingest import doc_chunk_key

        a = DocChunk(text="same   text", source="a.pdf", heading_path="H")
        b = DocChunk(text="same text", source="a.pdf", heading_path="H")
        assert doc_chunk_key(a) == doc_chunk_key(b)

    def test_field_boundary_separators_prevent_collision(self) -> None:
        from src.pdf_ingest import doc_chunk_key

        a = DocChunk(text="T", source="x ", heading_path="y")
        b = DocChunk(text="T", source="x", heading_path=" y")
        assert doc_chunk_key(a) != doc_chunk_key(b)

    def test_dedup_key_set_on_ingested_chunks(self, tmp_path: Path) -> None:
        """ingest_pdf_directory produces chunks with a non-empty dedup key set."""
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4 fake")
        doc = _fake_doc([_fake_page("This is a real text page with enough characters.")])
        with _patch_reader(doc):
            chunks = ingest_pdf_directory(tmp_path)
        assert chunks
        for c in chunks:
            assert c.dedup_key != ""


# ---------------------------------------------------------------------------
# OCR fallback wiring (image-only pages are empty extract_text, no PDF writer)
# ---------------------------------------------------------------------------


def _ingest_pages(pages: list[str], **kwargs: Any) -> list[DocChunk]:
    """Run ingest_pdf against a fake document whose pages have *pages* text."""
    doc = _fake_doc([_fake_page(text) for text in pages])
    with _patch_reader(doc):
        return ingest_pdf(Path("scanned.pdf"), **kwargs)


class TestIngestPdfOcrFallback:
    """Page-scoped OCR fallback for image-only pages (fake reader, plain hook)."""

    def test_fallback_called_for_image_only_page(self) -> None:
        calls: list[tuple[Path, int]] = []

        def fallback(path: Path, pageno: int) -> str:
            calls.append((path, pageno))
            return "OCR EXTRACTED TEXT here"

        chunks = _ingest_pages([""], ocr_fallback=fallback)
        assert calls == [(Path("scanned.pdf"), 1)]
        assert any("OCR EXTRACTED TEXT" in c.text for c in chunks)

    def test_no_fallback_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING", logger="src.pdf_ingest"):
            chunks = _ingest_pages([""])  # no fallback
        assert any(
            "[ocr]" in rec.message or "OCR_BACKEND=cpu" in rec.message
            for rec in caplog.records
            if rec.levelname == "WARNING"
        )
        assert chunks == []

    def test_page_report_records_outcomes(self) -> None:
        report: list[tuple[int, str, str]] = []
        _ingest_pages(["This is a real text page with enough characters to be kept."], page_report=report)
        assert report == [(1, "text", "")]

    def test_page_report_ocr_outcome(self) -> None:
        report: list[tuple[int, str, str]] = []
        _ingest_pages([""], ocr_fallback=lambda _p, _n: "OCR TEXT", page_report=report)
        assert report == [(1, "ocr", "")]

    def test_page_report_empty_ocr_no_text_reason(self) -> None:
        report: list[tuple[int, str, str]] = []
        _ingest_pages([""], ocr_fallback=lambda _p, _n: "", page_report=report)
        assert report == [(1, "empty", "ocr_no_text")]

    def test_page_report_skipped_no_engine_reason(self) -> None:
        report: list[tuple[int, str, str]] = []
        _ingest_pages([""], page_report=report)
        assert report == [(1, "skipped", "no_engine")]

    def test_page_report_optional_none(self) -> None:
        chunks = _ingest_pages(["This is a real text page with enough characters to be kept."])
        assert any("enough characters" in c.text for c in chunks)

    def test_fallback_returns_empty_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING", logger="src.pdf_ingest"):
            _ingest_pages([""], ocr_fallback=lambda _p, _n: "")
        assert any("OCR returned no text" in rec.message for rec in caplog.records if rec.levelname == "WARNING")

    def test_fallback_exception_skips_page(self, caplog: pytest.LogCaptureFixture) -> None:
        def boom(path: Path, pageno: int) -> str:
            raise RuntimeError("GPU oom")

        with caplog.at_level("WARNING", logger="src.pdf_ingest"):
            chunks = _ingest_pages([""], ocr_fallback=boom)
        assert chunks == []
        assert any("OCR fallback failed" in rec.message for rec in caplog.records if rec.levelname == "WARNING")

    def test_text_page_not_ocrd(self) -> None:
        calls: list[int] = []

        def record(n: int) -> str:
            calls.append(n)
            return "X"

        chunks = _ingest_pages(
            ["This is a real text page with enough characters to be kept."],
            ocr_fallback=lambda _p, n: record(n),
        )
        assert calls == []
        assert any("enough characters" in c.text for c in chunks)


class TestIngestPdfDirectoryPageReport:
    """AI-055: ingest_pdf_directory threads page_report (source, page, outcome, reason)."""

    def _patch_doc(self, tmp_path: Path, pages: list[str], name: str) -> Any:
        (tmp_path / name).write_bytes(b"%PDF-1.4 fake")
        doc = _fake_doc([_fake_page(text) for text in pages])
        return _patch_reader(doc)

    def test_directory_page_report_includes_source(self, tmp_path: Path) -> None:
        report: list[tuple[str, int, str, str]] = []
        with self._patch_doc(tmp_path, ["This is a real text page with enough characters to be kept."], "a.pdf"):
            ingest_pdf_directory(tmp_path, page_report=report)
        assert report == [("a.pdf", 1, "text", "")]

    def test_directory_page_report_carries_skip_reason(self, tmp_path: Path) -> None:
        report: list[tuple[str, int, str, str]] = []
        with self._patch_doc(tmp_path, [""], "scan.pdf"):
            ingest_pdf_directory(tmp_path, page_report=report)  # no ocr_fallback → no_engine
        assert report == [("scan.pdf", 1, "skipped", "no_engine")]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_constants_sane(self) -> None:
        assert HEADING_MIN_SIZE > 10
        assert CHUNK_TARGET_CHARS > 500
        assert CHUNK_OVERLAP_CHARS > 0
        assert MIN_PAGE_CHARS > 0

    def test_chunk_text_preserves_heading_path_hierarchy(self) -> None:
        text = """\
# Root Doc

## Parent Section

### Child Section

Child content here.
"""
        chunks = _chunk_text(text, "test.md", "Root")
        parent_chunks = [c for c in chunks if "Parent Section" in c.heading_path]
        assert len(parent_chunks) >= 1

    def test_md_cell_multiple_pipes(self) -> None:
        assert _md_cell("a|b|c") == "a\\|b\\|c"

    def test_is_table_section_single_row(self) -> None:
        assert _is_table_section("| a | b |") is True

    def test_estimate_tokens_single_char(self) -> None:
        assert _estimate_tokens("a") == 1
