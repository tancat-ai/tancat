"""Unit tests for src/pdf_ingest.py — PDF text extraction and chunking.

Tests are structured to cover:
- Heading detection and deduplication
- Text extraction with heading markers
- Table extraction and sanitisation
- Chunking logic (split on headings, paragraph splitting, table preservation)
- Full pipeline (ingest_pdf with mocked documents)
- Edge cases (empty pages, image-only pages, garbled text)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fitz", reason="PyMuPDF (fitz) not installed — skipping PDF tests")

from collections.abc import Callable

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
    _is_table_section,
    _md_cell,
    ingest_pdf,
    ingest_pdf_directory,
)
from src.rag_store import DocChunk

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
        # 3 of 4 non-empty lines are table lines — crosses the 50% threshold
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
        # preamble + 3 sections = 4 chunks
        assert len(chunks) == 4
        assert all(isinstance(c, DocChunk) for c in chunks)

    def test_heading_paths(self, sample_text_simple: str) -> None:
        chunks = _chunk_text(sample_text_simple, "test.md", "Test Doc")
        heading_paths = [c.heading_path for c in chunks]
        # Title is extracted from the # heading, not the passed doc_title
        assert "Document Title > Section One" in heading_paths
        assert "Document Title > Section Two" in heading_paths
        assert "Document Title > Section Three" in heading_paths

    def test_source_preserved(self, sample_text_simple: str) -> None:
        chunks = _chunk_text(sample_text_simple, "test.pdf", "Test")
        assert all(c.source == "test.pdf" for c in chunks)

    def test_table_not_split(self, sample_text_with_table: str) -> None:
        chunks = _chunk_text(sample_text_with_table, "test.md", "Test")
        # Table section stays as one chunk
        table_chunks = [c for c in chunks if "Coverage Limits" in c.heading_path]
        assert len(table_chunks) == 1
        assert "|" in table_chunks[0].text

    def test_large_section_split(self, sample_text_large_section: str) -> None:
        chunks = _chunk_text(sample_text_large_section, "test.md", "Test")
        # Should have: small section + at least 2 large-section sub-chunks
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
# _extract_headings (mocked fitz.Page)
# ---------------------------------------------------------------------------


class TestExtractHeadings:
    def _make_page(self, spans: list[dict]) -> MagicMock:
        """Build a mock fitz.Page from span dicts."""
        page = MagicMock()
        blocks = []
        for span in spans:
            blocks.append(
                {
                    "lines": [
                        {
                            "spans": [span],
                        }
                    ]
                }
            )
        page.get_text.return_value = "\n".join(s.get("text", "") for s in spans)
        page.get_text.side_effect = [
            {"blocks": blocks},  # "dict" call
            "\n".join(s.get("text", "") for s in spans),  # plain call
        ]
        return page

    def test_detects_large_spans(self) -> None:
        page = self._make_page(
            [
                {"text": "Hello", "size": 10.0, "bbox": (0, 0, 100, 20)},
                {"text": "Chapter 1", "size": 14.0, "bbox": (0, 30, 200, 50)},
            ]
        )
        headings = _extract_headings(page)
        assert len(headings) == 1
        assert headings[0][1] == "Chapter 1"

    def test_collapses_same_line(self) -> None:
        page = self._make_page(
            [
                {"text": "Chapter", "size": 14.0, "bbox": (0, 30, 100, 45)},
                {"text": "Chapter 1", "size": 14.0, "bbox": (0, 30, 200, 46)},
            ]
        )
        headings = _extract_headings(page)
        # Should deduplicate — keep longer text
        assert len(headings) == 1
        assert headings[0][1] == "Chapter 1"

    def test_empty_page(self) -> None:
        page = self._make_page([])
        headings = _extract_headings(page)
        assert headings == []

    def test_threshold_boundary(self) -> None:
        page = self._make_page(
            [
                {"text": "Small", "size": 11.4, "bbox": (0, 0, 50, 10)},
                {"text": "Heading", "size": 11.5, "bbox": (0, 20, 100, 30)},
            ]
        )
        headings = _extract_headings(page)
        assert len(headings) == 1
        assert headings[0][1] == "Heading"


# ---------------------------------------------------------------------------
# _extract_page_text_with_headings (mocked)
# ---------------------------------------------------------------------------


class TestExtractPageTextWithHeadings:
    def _make_page(self, plain_text: str, spans: list[dict]) -> MagicMock:
        page = MagicMock()
        blocks = []
        for span in spans:
            blocks.append({"lines": [{"spans": [span]}]})
        page.get_text.return_value = plain_text
        page.get_text.side_effect = [
            {"blocks": blocks},
            plain_text,
        ]
        return page

    def test_injects_heading_markers(self) -> None:
        page = self._make_page(
            plain_text="Hello\nWelcome to LV=\nSome content",
            spans=[
                {"text": "Welcome to LV=", "size": 13.0, "bbox": (0, 10, 200, 25)},
            ],
        )
        result = _extract_page_text_with_headings(page)
        assert "## Welcome to LV=" in result


# ---------------------------------------------------------------------------
# ingest_pdf (integration with real PDFs)
# ---------------------------------------------------------------------------


class TestIngestPdf:
    def test_real_tcs_pdf(self) -> None:
        path = Path("docs/rag_corpus/lv_docs/35880-2023-car-tc.pdf")
        if not path.exists():
            pytest.skip("PDF not available")
        chunks = ingest_pdf(path)
        assert len(chunks) > 0
        assert all(isinstance(c, DocChunk) for c in chunks)
        assert all(c.source == "35880-2023-car-tc.pdf" for c in chunks)
        # Should have heading paths
        assert any("Your insurance policy" in c.heading_path for c in chunks)

    def test_real_ipid_pdf(self) -> None:
        path = Path("docs/rag_corpus/lv_docs/0042748-2025-car-ipid.pdf")
        if not path.exists():
            pytest.skip("PDF not available")
        chunks = ingest_pdf(path)
        assert len(chunks) > 0
        assert any("What is this type of insurance" in c.heading_path for c in chunks)

    def test_real_cover_limits_pdf(self) -> None:
        path = Path("docs/rag_corpus/lv_docs/40383-2025-Cover-and-limits-v4-1.pdf")
        if not path.exists():
            pytest.skip("PDF not available")
        chunks = ingest_pdf(path)
        assert len(chunks) > 0

    def test_nonexistent_file(self) -> None:
        chunks = ingest_pdf(Path("/nonexistent/file.pdf"))
        assert chunks == []

    def test_contains_insurance_terms(self) -> None:
        path = Path("docs/rag_corpus/lv_docs/35880-2023-car-tc.pdf")
        if not path.exists():
            pytest.skip("PDF not available")
        chunks = ingest_pdf(path)
        all_text = " ".join(c.text for c in chunks)
        # Verify key insurance terms are extracted
        assert "insurance" in all_text.lower()
        assert "claim" in all_text.lower()


# ---------------------------------------------------------------------------
# ingest_pdf_directory
# ---------------------------------------------------------------------------


class TestIngestPdfDirectory:
    def test_all_pdfs(self) -> None:
        directory = Path("docs/rag_corpus/lv_docs")
        if not directory.exists():
            pytest.skip("Directory not available")
        chunks = ingest_pdf_directory(directory)
        assert len(chunks) > 0
        # Should include all 3 PDFs
        sources = {c.source for c in chunks}
        assert "35880-2023-car-tc.pdf" in sources
        assert "0042748-2025-car-ipid.pdf" in sources
        assert "40383-2025-Cover-and-limits-v4-1.pdf" in sources

    def test_empty_directory(self, tmp_path: Path) -> None:
        chunks = ingest_pdf_directory(tmp_path)
        assert chunks == []

    def test_threads_ocr_fallback_through(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """ingest_pdf_directory passes ocr_fallback to each file's ingest_pdf."""
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4 fake")
        seen: list[bool] = []

        def fake_ingest(path: Path, *, ocr_fallback: Callable[[Path, int], str] | None = None) -> list[DocChunk]:
            seen.append(ocr_fallback is not None)
            return []

        monkeypatch.setattr("src.pdf_ingest.ingest_pdf", fake_ingest)
        ingest_pdf_directory(tmp_path, ocr_fallback=lambda _p, _n: "")
        # The fallback closure was provided (not None) and threaded through.
        assert seen == [True]


# ---------------------------------------------------------------------------
# OCR fallback wiring (AI-045 #4) — real PyMuPDF-generated PDFs, no GPU
#
# These use *real* one-page PDFs built with fitz (installed via the ``[pdf]``
# extra; CI runs ``uv sync --all-extras``) rather than mocking fitz — mocking
# fitz's ``Page``/``Document`` magic methods is brittle and environment-
# dependent. The OCR hook itself is a plain callable, so no GPU/model is
# needed: we only assert the ingest path routes image-only pages to it.
# ---------------------------------------------------------------------------


def _write_image_only_pdf(path: Path) -> None:
    """Write a real one-page PDF with a drawing but no text (image-only)."""
    import fitz  # PyMuPDF (already importorskip'd at module top)

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(0, 0, 50, 50), color=(1, 0, 0))  # shape only → get_text() == ""
    doc.save(str(path))
    doc.close()


def _write_text_pdf(path: Path, body: str) -> None:
    """Write a real one-page PDF whose text is *body* (>= MIN_PAGE_CHARS)."""
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(72, 72), body, fontsize=12)
    doc.save(str(path))
    doc.close()


class TestIngestPdfOcrFallback:
    """Page-scoped OCR fallback for image-only pages (real PDFs, mocked OCR hook)."""

    def test_fallback_called_for_image_only_page(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scanned.pdf"
        _write_image_only_pdf(pdf)

        calls: list[tuple[Path, int]] = []

        def fallback(path: Path, pageno: int) -> str:
            calls.append((path, pageno))
            return "OCR EXTRACTED TEXT here"

        chunks = ingest_pdf(pdf, ocr_fallback=fallback)
        assert calls == [(pdf, 1)]
        assert any("OCR EXTRACTED TEXT" in c.text for c in chunks)

    def test_no_fallback_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        pdf = tmp_path / "scanned.pdf"
        _write_image_only_pdf(pdf)

        with caplog.at_level("WARNING", logger="src.pdf_ingest"):
            chunks = ingest_pdf(pdf)  # no fallback

        assert any("unlimited-ocr" in rec.message for rec in caplog.records if rec.levelname == "WARNING")
        assert chunks == []

    def test_fallback_returns_empty_warns(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        pdf = tmp_path / "scanned.pdf"
        _write_image_only_pdf(pdf)

        with caplog.at_level("WARNING", logger="src.pdf_ingest"):
            ingest_pdf(pdf, ocr_fallback=lambda _p, _n: "")

        assert any("OCR returned no text" in rec.message for rec in caplog.records if rec.levelname == "WARNING")

    def test_fallback_exception_skips_page(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        pdf = tmp_path / "scanned.pdf"
        _write_image_only_pdf(pdf)

        def boom(path: Path, pageno: int) -> str:
            raise RuntimeError("GPU oom")

        with caplog.at_level("WARNING", logger="src.pdf_ingest"):
            chunks = ingest_pdf(pdf, ocr_fallback=boom)

        assert chunks == []
        assert any("OCR fallback failed" in rec.message for rec in caplog.records if rec.levelname == "WARNING")

    def test_text_page_not_ocrd(self, tmp_path: Path) -> None:
        """A page with enough text is not sent to the OCR fallback."""
        pdf = tmp_path / "text.pdf"
        _write_text_pdf(pdf, "This is a real text page with enough characters to be kept.")

        calls: list[int] = []

        def record(n: int) -> str:
            calls.append(n)
            return "X"

        chunks = ingest_pdf(pdf, ocr_fallback=lambda _p, n: record(n))
        assert calls == []  # fallback never invoked for a text page
        assert any("enough characters" in c.text for c in chunks)  # real text path used


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
        # Should have at least one chunk with parent heading
        parent_chunks = [c for c in chunks if "Parent Section" in c.heading_path]
        assert len(parent_chunks) >= 1

    def test_md_cell_multiple_pipes(self) -> None:
        assert _md_cell("a|b|c") == "a\\|b\\|c"

    def test_is_table_section_single_row(self) -> None:
        assert _is_table_section("| a | b |") is True

    def test_estimate_tokens_single_char(self) -> None:
        assert _estimate_tokens("a") == 1
