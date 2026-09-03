"""Unit tests for 16b Phase 3 — Citation attachment and verification.

Tests:
    - attach_paste_citations: deterministic paste path (no LLM)
    - verify_document_citations: hybrid LLM-proposes/code-verifies
    - Quote verification: found on cited page, found on other page, not found
    - Unresolved handling: no LLM citation, empty quote, not found anywhere
    - Justification: generated only when citations verify, capped at 400 chars
    - build_llm_citation_prompt: prompt structure
"""

from __future__ import annotations

from typing import Any

from src.agents.pipeline_state import Criterion
from src.rag_store import DocChunk


class TestAttachPasteCitations:
    """Tests for the deterministic paste path (no LLM)."""

    def test_paste_citations_auto_generated(self) -> None:
        """Each criterion gets a SourceRef with the verbatim line as quote."""
        from src.citation_verifier import attach_paste_citations

        source_text = (
            "1. User can log in with valid credentials\n"
            "2. User sees error with invalid credentials\n"
            "3. Password must be at least 8 characters"
        )
        criteria = [
            Criterion(
                ref="TC01.01",
                description="User can log in with valid credentials",
                condition_type="happy_path",
                priority="medium",
                source_text="User can log in with valid credentials",
            ),
            Criterion(
                ref="TC01.02",
                description="User sees error with invalid credentials",
                condition_type="negative",
                priority="medium",
                source_text="User sees error with invalid credentials",
            ),
        ]

        result = attach_paste_citations(criteria, source_text)

        assert len(result) == 2
        for crit in result:
            assert len(crit.source_refs) == 1
            ref = crit.source_refs[0]
            assert ref.kind == "cited"
            assert ref.doc == "user-input"
            assert ref.route == "text"
            assert ref.quote != ""
            assert not ref.is_unresolved

    def test_paste_citations_quote_truncated(self) -> None:
        """Quotes are truncated to MAX_QUOTE_CHARS."""
        from src.citation_verifier import attach_paste_citations
        from src.source_refs import MAX_QUOTE_CHARS

        long_line = "A" * (MAX_QUOTE_CHARS + 100)
        criteria = [
            Criterion(
                ref="TC01.01",
                description=long_line,
                condition_type="happy_path",
                priority="medium",
                source_text=long_line,
            ),
        ]

        result = attach_paste_citations(criteria, long_line)
        assert len(result[0].source_refs[0].quote) <= MAX_QUOTE_CHARS

    def test_paste_citations_preserves_criteria(self) -> None:
        """The criteria list is not modified in unexpected ways."""
        from src.citation_verifier import attach_paste_citations

        criteria = [
            Criterion(
                ref="TC01.01",
                description="test",
                condition_type="happy_path",
                priority="high",
                source_text="test",
            ),
        ]

        result = attach_paste_citations(criteria, "test")
        assert result[0].ref == "TC01.01"
        assert result[0].description == "test"
        assert result[0].priority == "high"


class TestVerifyDocumentCitations:
    """Tests for the hybrid LLM-proposes/code-verifies mechanism."""

    def _make_chunks(self) -> list[DocChunk]:
        """Create page-tagged chunks for testing."""
        return [
            DocChunk(
                text="The maximum claim amount is five thousand pounds per incident.",
                source="policy.pdf",
                page=1,
                page_label="1",
                route="text",
                dedup_key="key1",
            ),
            DocChunk(
                text="The deductible applies to each claim and is non-refundable.",
                source="policy.pdf",
                page=2,
                page_label="2",
                route="text",
                dedup_key="key2",
            ),
            DocChunk(
                text="Premium is calculated based on vehicle value and driver age.",
                source="underwriting.pdf",
                page=1,
                page_label="1",
                route="text",
                dedup_key="key3",
            ),
        ]

    def test_citation_found_on_cited_page(self) -> None:
        """Quote found on the cited page → citation stands."""
        from src.citation_verifier import verify_document_citations

        chunks = self._make_chunks()
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Max claim amount boundary",
                condition_type="boundary",
                priority="high",
            ),
        ]
        llm_citations = {
            "TC01.01": [
                {
                    "doc": "policy.pdf",
                    "page": 1,
                    "quote": "The maximum claim amount is five thousand pounds per incident.",
                    "heading": "Limits",
                    "route": "text",
                },
            ],
        }

        result = verify_document_citations(criteria, chunks, llm_citations)
        assert len(result[0].source_refs) == 1
        ref = result[0].source_refs[0]
        assert ref.kind == "cited"
        assert ref.page_pdf == 1
        assert ref.doc == "policy.pdf"
        assert ref.quote != ""
        assert not ref.is_unresolved
        # Justification should be generated
        assert result[0].justification != ""

    def test_citation_found_on_other_page_correction(self) -> None:
        """Quote not on cited page but found on another → page corrected."""
        from src.citation_verifier import verify_document_citations

        chunks = self._make_chunks()
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Deductible rule",
                condition_type="boundary",
                priority="medium",
            ),
        ]
        # LLM says page 1, but the quote is actually on page 2
        llm_citations = {
            "TC01.01": [
                {
                    "doc": "policy.pdf",
                    "page": 1,  # Wrong page
                    "quote": "The deductible applies to each claim and is non-refundable.",
                    "heading": "",
                    "route": "text",
                },
            ],
        }

        result = verify_document_citations(criteria, chunks, llm_citations)
        assert len(result[0].source_refs) == 1
        ref = result[0].source_refs[0]
        assert ref.kind == "cited"
        # Page should be corrected to 2
        assert ref.page_pdf == 2

    def test_citation_not_found_unresolved(self) -> None:
        """Quote not found anywhere → unresolved ⚠."""
        from src.citation_verifier import verify_document_citations

        chunks = self._make_chunks()
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Some unknown boundary",
                condition_type="boundary",
                priority="medium",
            ),
        ]
        llm_citations = {
            "TC01.01": [
                {
                    "doc": "policy.pdf",
                    "page": 1,
                    "quote": "This text does not exist in any page",
                    "heading": "",
                    "route": "text",
                },
            ],
        }

        result = verify_document_citations(criteria, chunks, llm_citations)
        assert len(result[0].source_refs) == 1
        ref = result[0].source_refs[0]
        assert ref.kind == "unresolved"
        assert ref.is_unresolved
        # No justification for unresolved
        assert result[0].justification == ""

    def test_no_llm_citation_unresolved(self) -> None:
        """No citation emitted by LLM → unresolved."""
        from src.citation_verifier import verify_document_citations

        chunks = self._make_chunks()
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Test without citation",
                condition_type="happy_path",
                priority="medium",
            ),
        ]
        # Empty citations dict (no entry for TC01.01)
        llm_citations: dict[str, list[dict[str, Any]]] = {}

        result = verify_document_citations(criteria, chunks, llm_citations)
        assert len(result[0].source_refs) == 1
        assert result[0].source_refs[0].is_unresolved

    def test_empty_quote_unresolved(self) -> None:
        """Empty quote in LLM citation → unresolved."""
        from src.citation_verifier import verify_document_citations

        chunks = self._make_chunks()
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Test with empty quote",
                condition_type="happy_path",
                priority="medium",
            ),
        ]
        llm_citations = {
            "TC01.01": [
                {"doc": "policy.pdf", "page": 1, "quote": "", "heading": "", "route": "text"},
            ],
        }

        result = verify_document_citations(criteria, chunks, llm_citations)
        assert result[0].source_refs[0].is_unresolved

    def test_multiple_citations(self) -> None:
        """Criterion with multiple verified citations."""
        from src.citation_verifier import verify_document_citations

        chunks = self._make_chunks()
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Combined boundary",
                condition_type="boundary",
                priority="high",
            ),
        ]
        llm_citations = {
            "TC01.01": [
                {
                    "doc": "policy.pdf",
                    "page": 1,
                    "quote": "The maximum claim amount is five thousand pounds per incident.",
                    "heading": "Limits",
                    "route": "text",
                },
                {
                    "doc": "policy.pdf",
                    "page": 2,
                    "quote": "The deductible applies to each claim and is non-refundable.",
                    "heading": "Deductibles",
                    "route": "text",
                },
            ],
        }

        result = verify_document_citations(criteria, chunks, llm_citations)
        assert len(result[0].source_refs) == 2
        assert all(not r.is_unresolved for r in result[0].source_refs)

    def test_justification_capped(self) -> None:
        """Justification is capped at MAX_JUSTIFICATION_CHARS."""
        from src.citation_verifier import verify_document_citations
        from src.source_refs import MAX_JUSTIFICATION_CHARS

        # Create a chunk with a very long text
        long_text = "A" * 1000
        chunks = [
            DocChunk(
                text=long_text,
                source="big.pdf",
                page=1,
                route="text",
                dedup_key="key1",
            ),
        ]
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Test",
                condition_type="boundary",
                priority="medium",
            ),
        ]
        llm_citations = {
            "TC01.01": [
                {"doc": "big.pdf", "page": 1, "quote": long_text[:100], "heading": "", "route": "text"},
            ],
        }

        result = verify_document_citations(criteria, chunks, llm_citations)
        assert len(result[0].justification) <= MAX_JUSTIFICATION_CHARS

    def test_dedup_key_stored(self) -> None:
        """Verified citations store the chunk's dedup_key (D6)."""
        from src.citation_verifier import verify_document_citations

        chunks = self._make_chunks()
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Test",
                condition_type="boundary",
                priority="medium",
            ),
        ]
        llm_citations = {
            "TC01.01": [
                {
                    "doc": "policy.pdf",
                    "page": 1,
                    "quote": "The maximum claim amount is five thousand pounds per incident.",
                    "heading": "",
                    "route": "text",
                },
            ],
        }

        result = verify_document_citations(criteria, chunks, llm_citations)
        ref = result[0].source_refs[0]
        assert ref.dedup_key == "key1"  # The dedup_key from the chunk

    def test_cross_doc_citation(self) -> None:
        """Citation from a different document."""
        from src.citation_verifier import verify_document_citations

        chunks = self._make_chunks()
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Premium calculation",
                condition_type="boundary",
                priority="medium",
            ),
        ]
        llm_citations = {
            "TC01.01": [
                {
                    "doc": "underwriting.pdf",
                    "page": 1,
                    "quote": "Premium is calculated based on vehicle value and driver age.",
                    "heading": "Premium",
                    "route": "text",
                },
            ],
        }

        result = verify_document_citations(criteria, chunks, llm_citations)
        ref = result[0].source_refs[0]
        assert ref.doc == "underwriting.pdf"
        assert ref.kind == "cited"


class TestBuildLlmCitationPrompt:
    """Tests for the LLM citation prompt builder."""

    def test_prompt_contains_criterion(self) -> None:
        """Prompt includes the criterion description."""
        from src.citation_verifier import build_llm_citation_prompt

        chunks = [
            DocChunk(text="Some page text", source="doc.pdf", page=1, route="text"),
        ]
        criterion = Criterion(
            ref="TC01.01",
            description="Max claim boundary",
            condition_type="boundary",
            priority="high",
        )

        prompt = build_llm_citation_prompt(criterion, chunks)
        assert "Max claim boundary" in prompt

    def test_prompt_contains_page_snippets(self) -> None:
        """Prompt includes page snippets."""
        from src.citation_verifier import build_llm_citation_prompt

        chunks = [
            DocChunk(text="The maximum is five thousand.", source="doc.pdf", page=1, route="text"),
        ]
        criterion = Criterion(
            ref="TC01.01",
            description="test",
            condition_type="boundary",
            priority="medium",
        )

        prompt = build_llm_citation_prompt(criterion, chunks)
        assert "doc.pdf" in prompt
        assert "The maximum is five thousand." in prompt

    def test_prompt_requests_verbatim_quote(self) -> None:
        """Prompt explicitly requests verbatim quotes (D3)."""
        from src.citation_verifier import build_llm_citation_prompt

        chunks = [
            DocChunk(text="text", source="doc.pdf", page=1, route="text"),
        ]
        criterion = Criterion(
            ref="TC01.01",
            description="test",
            condition_type="boundary",
            priority="medium",
        )

        prompt = build_llm_citation_prompt(criterion, chunks)
        assert "VERBATIM" in prompt
        assert "do not paraphrase" in prompt
