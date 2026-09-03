"""Unit tests for 16b Phase 2 — Whole-document generation (page-aware parsing).

Tests:
    - ingest_pdf_page_aware() returns page-tagged chunks
    - Each chunk has correct page, page_label, route
    - Pipeline graph _parse_document feeds full text (not 500 chars)
    - OCR route chunks are correctly tagged
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


class TestIngestPdfPageAware:
    """Tests for the page-aware PDF ingestion function."""

    def _make_mock_doc(self, pages: list[tuple[str, str]]) -> MagicMock:
        """Create a mock fitz document with given (text, label) pages."""
        mock_doc = MagicMock()
        mock_doc.page_count = len(pages)

        mock_pages = []
        for text, label in pages:
            page = MagicMock()
            page.get_text.return_value = text
            page.get_label.return_value = label

            # _extract_headings calls page.get_text("dict") — return empty blocks
            # to skip the heading detection path (simpler mock)
            def _make_get_text(t: str) -> Any:
                def _get_text(*a: Any, **k: Any) -> Any:
                    if a and a[0] == "dict":
                        return {"blocks": []}
                    return t

                return _get_text

            page.get_text.side_effect = _make_get_text(text)
            mock_pages.append(page)

        # __getitem__ returns pages by index
        def getitem(i: int) -> MagicMock:
            return mock_pages[i]

        mock_doc.__getitem__ = MagicMock(side_effect=getitem)
        return mock_doc

    @patch("src.pdf_ingest._import_fitz")
    def test_page_aware_returns_tagged_chunks(self, mock_fitz: MagicMock) -> None:
        """ingest_pdf_page_aware returns chunks with page numbers."""
        from src.pdf_ingest import ingest_pdf_page_aware

        pages = [
            ("## Section A\n\nSome text about section A", "1"),
            ("## Section B\n\nSome text about section B", "2"),
            ("## Section C\n\nSome text about section C", "3"),
        ]
        mock_doc = self._make_mock_doc(pages)
        mock_fitz.return_value.open.return_value = mock_doc

        chunks = ingest_pdf_page_aware(Path("test.pdf"))

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.page > 0  # Every chunk has a page number
            assert chunk.route == "text"  # All text route (no OCR)
            assert chunk.page_label != ""  # All pages have labels

    @patch("src.pdf_ingest._import_fitz")
    def test_page_aware_ocr_route(self, mock_fitz: MagicMock) -> None:
        """ingest_pdf_page_aware tags OCR chunks with route='ocr'."""
        from src.pdf_ingest import ingest_pdf_page_aware

        pages = [
            ("## Section A\n\nText content here", "1"),
            ("", "2"),  # Empty = image-only, will use OCR
        ]
        mock_doc = self._make_mock_doc(pages)
        mock_fitz.return_value.open.return_value = mock_doc

        def ocr_hook(path: Path, page_num: int) -> str:
            if page_num == 2:
                return "## Scanned Section\n\nOCR extracted text"
            return ""

        chunks = ingest_pdf_page_aware(Path("test.pdf"), ocr_fallback=ocr_hook)

        ocr_chunks = [c for c in chunks if c.route == "ocr"]
        assert len(ocr_chunks) > 0
        assert ocr_chunks[0].page == 2
        assert ocr_chunks[0].page_label == "2"

    @patch("src.pdf_ingest._import_fitz")
    def test_page_aware_skips_empty_pages(self, mock_fitz: MagicMock) -> None:
        """ingest_pdf_page_aware skips image-only pages without OCR."""
        from src.pdf_ingest import ingest_pdf_page_aware

        pages = [
            ("## Section A\n\nText content", "1"),
            ("", "2"),  # Empty = image-only
        ]
        mock_doc = self._make_mock_doc(pages)
        mock_fitz.return_value.open.return_value = mock_doc

        chunks = ingest_pdf_page_aware(Path("test.pdf"))

        # Only page 1 chunks (page 2 skipped, no OCR)
        assert all(c.page == 1 for c in chunks)

    @patch("src.pdf_ingest._import_fitz")
    def test_page_aware_dedup_keys(self, mock_fitz: MagicMock) -> None:
        """ingest_pdf_page_aware computes dedup keys for all chunks."""
        from src.pdf_ingest import ingest_pdf_page_aware

        pages = [
            ("## Section A\n\nText content here", "1"),
        ]
        mock_doc = self._make_mock_doc(pages)
        mock_fitz.return_value.open.return_value = mock_doc

        chunks = ingest_pdf_page_aware(Path("test.pdf"))

        for chunk in chunks:
            assert chunk.dedup_key != ""  # Every chunk has a dedup key

    @patch("src.pdf_ingest._import_fitz")
    def test_page_aware_page_numbers_sequential(self, mock_fitz: MagicMock) -> None:
        """Page numbers are sequential and match the PDF page order."""
        from src.pdf_ingest import ingest_pdf_page_aware

        pages = [
            ("## A\n\nText A content here", "1"),
            ("## B\n\nText B content here", "2"),
            ("## C\n\nText C content here", "3"),
        ]
        mock_doc = self._make_mock_doc(pages)
        mock_fitz.return_value.open.return_value = mock_doc

        chunks = ingest_pdf_page_aware(Path("test.pdf"))

        # Group chunks by page
        page_1 = [c for c in chunks if c.page == 1]
        page_2 = [c for c in chunks if c.page == 2]
        page_3 = [c for c in chunks if c.page == 3]

        assert len(page_1) > 0
        assert len(page_2) > 0
        assert len(page_3) > 0
        # Verify page labels match
        assert all(c.page_label == "1" for c in page_1)
        assert all(c.page_label == "2" for c in page_2)
        assert all(c.page_label == "3" for c in page_3)


class TestPipelineGraphParseDocument:
    """Tests for the pipeline graph _parse_document (16b Phase 2)."""

    @pytest.mark.asyncio
    async def test_parse_document_pdf_feeds_full_text(self) -> None:
        """_parse_document feeds full text into user_story (not 500 chars)."""
        from src.agents.pipeline_graph import PipelineGraph
        from src.agents.pipeline_state import PipelineState
        from src.rag_store import DocChunk

        graph = PipelineGraph.__new__(PipelineGraph)

        chunk1 = DocChunk(
            text="Page 1: The insurance policy covers all damages including structural, mechanical, and cosmetic repairs. The premium is calculated based on the vehicle value, driver age, and territory code. Coverage includes loss of use and rental car reimbursement for up to 30 days per claim event.",
            source="policy.pdf",
            page=1,
            page_label="1",
            route="text",
        )
        chunk2 = DocChunk(
            text="Page 2: The maximum claim amount per incident is set at the upper boundary defined in Schedule A. For commercial vehicles the limit is higher than for private vehicles. The deductible applies to each claim and is non-refundable. In the event of a total loss the policy pays the market value minus the applicable deductible amount.",
            source="policy.pdf",
            page=2,
            page_label="2",
            route="text",
        )
        chunk3 = DocChunk(
            text="Page 3: Exclusions apply to all coverage lines including intentional damage, wear and tear, and mechanical failure pre-existing the policy start date. The insurer may reduce the claim amount where the policyholder failed to take reasonable steps to mitigate damage. Subrogation rights are reserved for all settled claims exceeding the threshold amount.",
            source="policy.pdf",
            page=3,
            page_label="3",
            route="text",
        )

        with (
            patch(
                "src.pdf_ingest.ingest_pdf_page_aware",
                return_value=[chunk1, chunk2, chunk3],
            ),
            patch("src.ocr_backends.get_ocr_backend") as mock_backend,
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "suffix", new_callable=PropertyMock, return_value=".pdf"),
        ):
            mock_ocr = MagicMock()
            mock_ocr.available.return_value = False
            mock_backend.return_value = mock_ocr

            state = PipelineState(
                input_mode="document",
                document_source="policy.pdf",
            )

            result = await graph._parse_document(state)

            assert "errors" not in result, f"Got errors: {result.get('errors')}"
            assert "user_story" in result
            full_text = result["user_story"]
            assert "Page 1:" in full_text
            assert "Page 2:" in full_text
            assert "Page 3:" in full_text
            # Should be longer than 500 chars (the old ceiling)
            assert len(full_text) > 500
