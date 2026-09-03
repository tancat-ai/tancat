"""Unit tests for src/source_refs.py — 16b Phase 1 (SourceRef data model).

Tests:
    - SourceRef dataclass construction and properties
    - SourceRef.display() in all modes (cited, unresolved, privacy_mode)
    - SourceRef.to_dict() / from_dict() round-trip
    - normalize_for_quote_match() normalizations
    - verify_quote() verification logic
    - DocChunk provenance fields (page, page_label, route)
    - RetrievedPattern provenance fields (doc_source, doc_page, etc.)
    - Criterion source_refs / justification fields
    - PipelineState from_dict() deserialization of source_refs
"""

from __future__ import annotations

# ── SourceRef tests ─────────────────────────────────────────────────


class TestSourceRef:
    """Tests for the SourceRef dataclass."""

    def test_default_construction(self) -> None:
        """SourceRef with all defaults is valid."""
        from src.source_refs import SourceRef

        ref = SourceRef()
        assert ref.doc == ""
        assert ref.page_pdf == 0
        assert ref.page_label == ""
        assert ref.heading == ""
        assert ref.quote == ""
        assert ref.route == "text"
        assert ref.dedup_key == ""
        assert ref.kind == "cited"
        assert not ref.is_unresolved

    def test_cited_construction(self) -> None:
        """SourceRef with full citation data."""
        from src.source_refs import SourceRef

        ref = SourceRef(
            doc="policy.pdf",
            page_pdf=9,
            page_label="5",
            heading="Limits > Claim Maximum",
            quote="The maximum claim amount is £5,000",
            route="text",
            dedup_key="abc123",
            kind="cited",
        )
        assert ref.doc == "policy.pdf"
        assert ref.page_pdf == 9
        assert ref.page_label == "5"
        assert ref.heading == "Limits > Claim Maximum"
        assert ref.quote == "The maximum claim amount is £5,000"
        assert ref.route == "text"
        assert ref.dedup_key == "abc123"
        assert not ref.is_unresolved

    def test_unresolved_construction(self) -> None:
        """SourceRef with kind='unresolved' is an ⚠ signal."""
        from src.source_refs import SourceRef

        ref = SourceRef(
            doc="policy.pdf",
            page_pdf=0,
            kind="unresolved",
        )
        assert ref.is_unresolved

    def test_display_cited(self) -> None:
        """display() renders a cited SourceRef with quote."""
        from src.source_refs import SourceRef

        ref = SourceRef(
            doc="policy.pdf",
            page_pdf=9,
            page_label="5",
            quote="The maximum claim amount is £5,000",
            route="text",
            kind="cited",
        )
        result = ref.display()
        assert "policy.pdf" in result
        assert "PDF p.9" in result
        assert "printed '5'" in result
        assert "The maximum claim amount is £5,000" in result

    def test_display_cited_ocr(self) -> None:
        """display() shows OCR route tag."""
        from src.source_refs import SourceRef

        ref = SourceRef(
            doc="scanned.pdf",
            page_pdf=3,
            quote="Some text",
            route="ocr",
            kind="cited",
        )
        result = ref.display()
        assert "[ocr]" in result

    def test_display_unresolved(self) -> None:
        """display() renders an unresolved ⚠ signal."""
        from src.source_refs import SourceRef

        ref = SourceRef(
            doc="policy.pdf",
            kind="unresolved",
        )
        result = ref.display()
        assert "⚠" in result
        assert "policy.pdf" in result
        assert "no source found" in result

    def test_display_privacy_mode(self) -> None:
        """display() with privacy_mode omits quote text."""
        from src.source_refs import SourceRef

        ref = SourceRef(
            doc="policy.pdf",
            page_pdf=9,
            page_label="5",
            quote="Secret quote text",
            route="text",
            kind="cited",
        )
        result = ref.display(privacy_mode=True)
        assert "Secret quote text" not in result
        assert "PRIVACY_MODE" in result
        assert "policy.pdf" in result

    def test_display_quote_truncation(self) -> None:
        """display() truncates quotes over MAX_QUOTE_CHARS."""
        from src.source_refs import MAX_QUOTE_CHARS, SourceRef

        long_quote = "A" * (MAX_QUOTE_CHARS + 100)
        ref = SourceRef(
            doc="doc.pdf",
            page_pdf=1,
            quote=long_quote,
            kind="cited",
        )
        result = ref.display()
        # Should be truncated
        assert "…" in result
        # Original long text not fully present
        assert long_quote not in result

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict() and from_dict() round-trip preserves all fields."""
        from src.source_refs import SourceRef

        original = SourceRef(
            doc="policy.pdf",
            page_pdf=9,
            page_label="5",
            heading="Limits > Claim Maximum",
            quote="The maximum claim amount is £5,000",
            route="ocr",
            dedup_key="abc123",
            kind="cited",
        )
        d = original.to_dict()
        restored = SourceRef.from_dict(d)
        assert restored == original

    def test_from_dict_with_missing_fields(self) -> None:
        """from_dict() handles missing fields gracefully."""
        from src.source_refs import SourceRef

        ref = SourceRef.from_dict({})
        assert ref.doc == ""
        assert ref.page_pdf == 0
        assert ref.kind == "cited"


# ── normalize_for_quote_match tests ─────────────────────────────────


class TestNormalizeForQuoteMatch:
    """Tests for quote normalization."""

    def test_case_folding(self) -> None:
        """Normalization case-folds text."""
        from src.source_refs import normalize_for_quote_match

        result = normalize_for_quote_match("Hello World")
        assert result == "hello world"

    def test_whitespace_collapse(self) -> None:
        """Normalization collapses whitespace runs."""
        from src.source_refs import normalize_for_quote_match

        result = normalize_for_quote_match("Hello   World\n  Test")
        assert result == "hello world test"

    def test_curly_quotes(self) -> None:
        """Normalization converts curly quotes to straight."""
        from src.source_refs import normalize_for_quote_match

        result = normalize_for_quote_match("\u201cHello\u201d")
        assert result == '"hello"'

    def test_curly_apostrophes(self) -> None:
        """Normalization converts curly apostrophes to straight."""
        from src.source_refs import normalize_for_quote_match

        result = normalize_for_quote_match("It\u2019s a test")
        assert result == "it's a test"

    def test_dashes(self) -> None:
        """Normalization converts em/en dashes to hyphen."""
        from src.source_refs import normalize_for_quote_match

        result = normalize_for_quote_match("A\u2014B\u2013C")
        assert result == "a-b-c"

    def test_combined_normalization(self) -> None:
        """Normalization handles all transformations together."""
        from src.source_refs import normalize_for_quote_match

        result = normalize_for_quote_match("  \u201cHello\u201d   World  ")
        assert result == '"hello" world'


# ── verify_quote tests ──────────────────────────────────────────────


class TestVerifyQuote:
    """Tests for quote verification."""

    def test_exact_match(self) -> None:
        """verify_quote() returns True for exact match."""
        from src.source_refs import verify_quote

        assert verify_quote("hello world", "This is hello world right here")

    def test_case_insensitive(self) -> None:
        """verify_quote() is case-insensitive."""
        from src.source_refs import verify_quote

        assert verify_quote("Hello World", "this is hello world right here")

    def test_whitespace_insensitive(self) -> None:
        """verify_quote() ignores whitespace differences."""
        from src.source_refs import verify_quote

        assert verify_quote("hello world", "This is   hello   world   right here")

    def test_no_match(self) -> None:
        """verify_quote() returns False for no match."""
        from src.source_refs import verify_quote

        assert not verify_quote("hello world", "This is goodbye world")

    def test_empty_quote(self) -> None:
        """verify_quote() returns False for empty quote."""
        from src.source_refs import verify_quote

        assert not verify_quote("", "some text")

    def test_empty_page_text(self) -> None:
        """verify_quote() returns False for empty page text."""
        from src.source_refs import verify_quote

        assert not verify_quote("hello", "")

    def test_curly_quote_match(self) -> None:
        """verify_quote() matches across curly/straight quote differences."""
        from src.source_refs import verify_quote

        assert verify_quote("hello world", "This is \u201chello world\u201d right here")


# ── DocChunk provenance tests ───────────────────────────────────────


class TestDocChunkProvenance:
    """Tests for DocChunk provenance fields (16b Phase 1)."""

    def test_default_provenance(self) -> None:
        """DocChunk defaults have page=0, page_label='', route='text'."""
        from src.rag_store import DocChunk

        chunk = DocChunk(text="some text", source="doc.md")
        assert chunk.page == 0
        assert chunk.page_label == ""
        assert chunk.route == "text"

    def test_pdf_provenance(self) -> None:
        """DocChunk with PDF provenance data."""
        from src.rag_store import DocChunk

        chunk = DocChunk(
            text="some text",
            source="policy.pdf",
            page=9,
            page_label="5",
            route="text",
        )
        assert chunk.page == 9
        assert chunk.page_label == "5"
        assert chunk.route == "text"

    def test_ocr_provenance(self) -> None:
        """DocChunk with OCR route."""
        from src.rag_store import DocChunk

        chunk = DocChunk(
            text="scanned text",
            source="scanned.pdf",
            page=3,
            page_label="",
            route="ocr",
        )
        assert chunk.route == "ocr"


# ── RetrievedPattern provenance tests ───────────────────────────────


class TestRetrievedPatternProvenance:
    """Tests for RetrievedPattern provenance fields (16b Phase 1)."""

    def test_default_provenance(self) -> None:
        """RetrievedPattern defaults have empty doc provenance."""
        from src.rag_store import RetrievedPattern

        pattern = RetrievedPattern(
            description="desc",
            selector="#id",
            action_type="CLICK",
            confidence=0.9,
        )
        assert pattern.doc_source == ""
        assert pattern.doc_page == 0
        assert pattern.doc_page_label == ""
        assert pattern.doc_route == "text"

    def test_with_doc_provenance(self) -> None:
        """RetrievedPattern with doc provenance."""
        from src.rag_store import RetrievedPattern

        pattern = RetrievedPattern(
            description="desc",
            selector="#id",
            action_type="ASSERT",
            confidence=0.8,
            doc_source="policy.pdf",
            doc_page=9,
            doc_page_label="5",
            doc_route="ocr",
        )
        assert pattern.doc_source == "policy.pdf"
        assert pattern.doc_page == 9
        assert pattern.doc_page_label == "5"
        assert pattern.doc_route == "ocr"


# ── Criterion provenance tests ──────────────────────────────────────


class TestCriterionProvenance:
    """Tests for Criterion source_refs / justification fields (16b Phase 1)."""

    def test_default_provenance(self) -> None:
        """Criterion defaults have empty source_refs and justification."""
        from src.agents.pipeline_state import Criterion

        crit = Criterion(
            ref="TC01.01",
            description="test",
            condition_type="happy_path",
            priority="high",
        )
        assert crit.source_refs == []
        assert crit.justification == ""

    def test_with_source_refs(self) -> None:
        """Criterion with source_refs."""
        from src.agents.pipeline_state import Criterion
        from src.source_refs import SourceRef

        ref = SourceRef(
            doc="policy.pdf",
            page_pdf=9,
            quote="max £5,000",
            kind="cited",
        )
        crit = Criterion(
            ref="TC01.01",
            description="test",
            condition_type="boundary",
            priority="high",
            source_refs=[ref],
            justification="Doc p.9 states max £5,000",
        )
        assert len(crit.source_refs) == 1
        assert crit.justification == "Doc p.9 states max £5,000"

    def test_from_dict_with_source_refs(self) -> None:
        """Criterion from_dict handles source_refs deserialization."""
        from src.source_refs import SourceRef

        # Simulate what comes from checkpointing (source_refs as list of dicts)
        c_dict = {
            "ref": "TC01.01",
            "description": "test",
            "condition_type": "boundary",
            "priority": "high",
            "source_text": "",
            "needs_clarification": False,
            "clarification_question": "",
            "prerequisite_refs": [],
            "source_refs": [
                {
                    "doc": "policy.pdf",
                    "page_pdf": "9",
                    "page_label": "5",
                    "heading": "",
                    "quote": "max £5,000",
                    "route": "text",
                    "dedup_key": "abc",
                    "kind": "cited",
                }
            ],
            "justification": "Doc p.9 states max £5,000",
        }

        # Use PipelineState.from_dict which handles the deserialization
        from src.agents.pipeline_state import PipelineState

        state_dict = {
            "story_analysis": {
                "criteria": [c_dict],
                "story_text": "",
                "domain_terms": [],
                "assumptions": [],
                "boundary_values": [],
                "source_format": "",
            },
        }
        state = PipelineState.from_dict(state_dict)
        assert state.story_analysis is not None
        crit = state.story_analysis.criteria[0]
        assert len(crit.source_refs) == 1
        ref = crit.source_refs[0]
        # Should be a SourceRef instance
        assert isinstance(ref, SourceRef)
        assert ref.doc == "policy.pdf"
        assert ref.page_pdf == 9
        assert ref.quote == "max £5,000"


# ── QA Director pass-through tests ──────────────────────────────────


class TestDirectorPassThrough:
    """Tests for the QA Director carrying 16b provenance (D12)."""

    def test_director_carries_source_refs(self) -> None:
        """QA Director must carry source_refs and justification through."""
        from src.agents.director import QADirectorAgent
        from src.agents.pipeline_state import Criterion, PipelineState, StoryAnalysis
        from src.source_refs import SourceRef

        ref = SourceRef(
            doc="policy.pdf",
            page_pdf=9,
            quote="max £5,000",
            kind="cited",
        )
        criterion = Criterion(
            ref="TC01.01",
            description="Boundary test for claim max",
            condition_type="boundary",
            priority="high",
            source_refs=[ref],
            justification="Doc p.9 states max £5,000",
        )
        analysis = StoryAnalysis(
            story_text="test story",
            criteria=[criterion],
        )
        state = PipelineState(
            story_analysis=analysis,
            auto_confirm=True,
        )

        director = QADirectorAgent()
        # Call the director's __call__ (async)
        import asyncio

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(director(state))
        loop.close()
        conditions = result["test_conditions"]
        assert len(conditions) == 1
        assert len(conditions[0].source_refs) == 1
        assert conditions[0].justification == "Doc p.9 states max £5,000"
