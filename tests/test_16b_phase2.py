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

    @staticmethod
    def _make_fake_doc(pages: list[tuple[str, str]]) -> Any:
        """A fake pdfplumber document with the given (text, label) pages."""
        doc = MagicMock()
        fake_pages = []
        for text, _label in pages:
            page = MagicMock()
            page.extract_text.return_value = text
            page.extract_text_lines.return_value = []
            page.extract_tables.return_value = []
            fake_pages.append(page)
        doc.pages = fake_pages
        doc.close.return_value = None
        return doc

    def _run(self, pages: list[tuple[str, str]], **kwargs: Any) -> list[Any]:
        """Run ingest_pdf_page_aware against a fake document."""
        from src.pdf_ingest import ingest_pdf_page_aware

        doc = self._make_fake_doc(pages)
        labels = [label for _text, label in pages]
        with (
            patch("src.pdf_ingest._require_pdfplumber") as mock_plumber,
            patch("src.pdf_ingest._page_labels", return_value=labels),
        ):
            mock_plumber.return_value.open.return_value = doc
            return ingest_pdf_page_aware(Path("test.pdf"), **kwargs)

    def test_page_aware_returns_tagged_chunks(self) -> None:
        """ingest_pdf_page_aware returns chunks with page numbers."""
        pages = [
            ("## Section A\n\nSome text about section A", "1"),
            ("## Section B\n\nSome text about section B", "2"),
            ("## Section C\n\nSome text about section C", "3"),
        ]
        chunks = self._run(pages)

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.page > 0  # Every chunk has a page number
            assert chunk.route == "text"  # All text route (no OCR)
            assert chunk.page_label != ""  # All pages have labels

    def test_page_aware_ocr_route(self) -> None:
        """ingest_pdf_page_aware tags OCR chunks with route='ocr'."""
        pages = [
            ("## Section A\n\nText content here", "1"),
            ("", "2"),  # Empty = image-only, will use OCR
        ]

        def ocr_hook(path: Path, page_num: int) -> str:
            if page_num == 2:
                return "## Scanned Section\n\nOCR extracted text"
            return ""

        chunks = self._run(pages, ocr_fallback=ocr_hook)

        ocr_chunks = [c for c in chunks if c.route == "ocr"]
        assert len(ocr_chunks) > 0
        assert ocr_chunks[0].page == 2
        assert ocr_chunks[0].page_label == "2"

    def test_page_aware_skips_empty_pages(self) -> None:
        """ingest_pdf_page_aware skips image-only pages without OCR."""
        pages = [
            ("## Section A\n\nText content", "1"),
            ("", "2"),  # Empty = image-only
        ]
        chunks = self._run(pages)

        # Only page 1 chunks (page 2 skipped, no OCR)
        assert all(c.page == 1 for c in chunks)

    def test_page_aware_dedup_keys(self) -> None:
        """ingest_pdf_page_aware computes dedup keys for all chunks."""
        pages = [
            ("## Section A\n\nText content here", "1"),
        ]
        chunks = self._run(pages)

        for chunk in chunks:
            assert chunk.dedup_key != ""  # Every chunk has a dedup key

    def test_page_aware_page_numbers_sequential(self) -> None:
        """Page numbers are sequential and match the PDF page order."""
        pages = [
            ("## A\n\nText A content here", "1"),
            ("## B\n\nText B content here", "2"),
            ("## C\n\nText C content here", "3"),
        ]
        chunks = self._run(pages)

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
