"""Unit tests for 16b Phase 4 — Citation surfaces and rendering.

Tests:
    - render_source_comments: test-file # Source: comments
    - render_source_comments: privacy_mode (pointer-only)
    - render_source_comments: unresolved ⚠ always visible
    - render_citation_cards: structured data for Living Test Plan
    - render_cli_debug: single criterion citation dump
    - render_cli_debug: criterion not found
    - render_export_note: self-documenting note
"""

from __future__ import annotations

from src.agents.pipeline_state import Criterion
from src.source_refs import SourceRef


def _make_criteria() -> list[Criterion]:
    """Create test criteria with varied citation states."""
    cited_ref = SourceRef(
        doc="policy.pdf",
        page_pdf=9,
        page_label="5",
        heading="Limits",
        quote="The maximum claim is five thousand pounds",
        route="ocr",
        dedup_key="abc123",
        kind="cited",
    )
    unresolved_ref = SourceRef(
        doc="policy.pdf",
        page_pdf=0,
        kind="unresolved",
    )
    no_refs_criterion = Criterion(
        ref="TC01.01",
        description="No document provenance",
        condition_type="happy_path",
        priority="medium",
    )

    return [
        no_refs_criterion,
        Criterion(
            ref="TC01.02",
            description="Max claim boundary",
            condition_type="boundary",
            priority="high",
            source_refs=[cited_ref],
            justification="Doc p.9 states max £5,000",
        ),
        Criterion(
            ref="TC01.03",
            description="Unknown increment",
            condition_type="boundary",
            priority="medium",
            source_refs=[unresolved_ref],
            justification="",
        ),
    ]


class TestRenderSourceComments:
    """Tests for the test-file # Source: comment surface."""

    def test_cited_criterion_renders(self) -> None:
        """A cited criterion produces a # Source: comment block."""
        from src.citation_surfaces import render_source_comments

        criteria = _make_criteria()
        result = render_source_comments(criteria)

        assert "# TC01.02" in result
        assert "policy.pdf" in result
        assert "PDF p.9" in result
        assert "printed '5'" in result
        assert "[ocr]" in result
        assert "The maximum claim is five thousand pounds" in result
        assert "Because:" in result

    def test_unresolved_criterion_renders_warning(self) -> None:
        """An unresolved criterion renders ⚠ (never silently omitted)."""
        from src.citation_surfaces import render_source_comments

        criteria = _make_criteria()
        result = render_source_comments(criteria)

        assert "# TC01.03" in result
        assert "⚠" in result
        assert "no source found" in result

    def test_no_refs_criterion_skipped(self) -> None:
        """A criterion without source_refs produces no comments."""
        from src.citation_surfaces import render_source_comments

        criteria = _make_criteria()
        result = render_source_comments(criteria)

        # TC01.01 has no source_refs → not in output
        assert "# TC01.01" not in result

    def test_empty_criteria_returns_empty(self) -> None:
        """Empty criteria list returns empty string."""
        from src.citation_surfaces import render_source_comments

        result = render_source_comments([])
        assert result == ""

    def test_privacy_mode_omits_quotes(self) -> None:
        """PRIVACY_MODE omits quote text from comments (D7)."""
        from src.citation_surfaces import render_source_comments

        criteria = _make_criteria()
        result = render_source_comments(criteria, privacy_mode=True)

        # Quote text should NOT be present
        assert "The maximum claim is five thousand pounds" not in result
        # Pointer info should still be present
        assert "policy.pdf" in result
        assert "PDF p.9" in result
        # PRIVACY_MODE note
        assert "PRIVACY_MODE" in result
        # Justification should also be omitted in privacy mode
        assert "Because:" not in result

    def test_multiple_citations_renders_all(self) -> None:
        """Criterion with multiple citations renders all of them."""
        from src.citation_surfaces import render_source_comments

        ref1 = SourceRef(
            doc="policy.pdf",
            page_pdf=1,
            quote="First citation text",
            kind="cited",
        )
        ref2 = SourceRef(
            doc="policy.pdf",
            page_pdf=2,
            quote="Second citation text",
            kind="cited",
        )
        criteria = [
            Criterion(
                ref="TC01.01",
                description="Multi-citation test",
                condition_type="boundary",
                priority="high",
                source_refs=[ref1, ref2],
                justification="Two sources combined",
            ),
        ]

        result = render_source_comments(criteria)
        assert "First citation text" in result
        assert "Second citation text" in result
        assert "PDF p.1" in result
        assert "PDF p.2" in result


class TestRenderCitationCards:
    """Tests for the Living Test Plan citation card surface."""

    def test_cards_structure(self) -> None:
        """Cards have the expected structure."""
        from src.citation_surfaces import render_citation_cards

        criteria = _make_criteria()
        cards = render_citation_cards(criteria)

        # TC01.01 (no refs) is excluded
        assert len(cards) == 2

        # First card: TC01.02 (cited)
        card = cards[0]
        assert card["ref"] == "TC01.02"
        assert card["description"] == "Max claim boundary"
        assert len(card["citations"]) == 1
        assert "policy.pdf" in card["citations"][0]
        assert card["has_unresolved"] is False
        assert card["justification"] == "Doc p.9 states max £5,000"

        # Second card: TC01.03 (unresolved)
        card = cards[1]
        assert card["ref"] == "TC01.03"
        assert card["has_unresolved"] is True
        assert card["justification"] == ""

    def test_cards_privacy_mode(self) -> None:
        """PRIVACY_MODE cards omit quotes and justification."""
        from src.citation_surfaces import render_citation_cards

        criteria = _make_criteria()
        cards = render_citation_cards(criteria, privacy_mode=True)

        for card in cards:
            assert card["privacy_mode"] is True
            # Justification omitted in privacy mode
            assert card["justification"] == ""
            # Citations should be pointer-only
            for citation in card["citations"]:
                assert "The maximum claim" not in citation

    def test_empty_criteria_no_cards(self) -> None:
        """Empty criteria produces no cards."""
        from src.citation_surfaces import render_citation_cards

        cards = render_citation_cards([])
        assert cards == []


class TestRenderCliDebug:
    """Tests for the CLI debug query surface."""

    def test_found_criterion(self) -> None:
        """CLI debug renders full citation details for a found criterion."""
        from src.citation_surfaces import render_cli_debug

        criteria = _make_criteria()
        result = render_cli_debug(criteria, "TC01.02")

        assert "=== Citations for TC01.02 ===" in result
        assert "Max claim boundary" in result
        assert "✓ CITED" in result
        assert "policy.pdf" in result
        assert "p.9" in result
        assert "printed '5'" in result
        assert "The maximum claim is five thousand pounds" in result
        assert "Route: ocr" in result
        assert "Dedup:" in result
        assert "Justification" in result
        assert "Trust boundary:" in result
        assert "Evidence (verified)" in result

    def test_unresolved_criterion(self) -> None:
        """CLI debug renders ⚠ for unresolved citations."""
        from src.citation_surfaces import render_cli_debug

        criteria = _make_criteria()
        result = render_cli_debug(criteria, "TC01.03")

        assert "⚠ UNRESOLVED" in result
        assert "policy.pdf" in result

    def test_criterion_not_found(self) -> None:
        """CLI debug returns error for unknown criterion ref."""
        from src.citation_surfaces import render_cli_debug

        criteria = _make_criteria()
        result = render_cli_debug(criteria, "TC99.99")

        assert "Error" in result
        assert "not found" in result

    def test_no_refs_criterion(self) -> None:
        """CLI debug handles criterion without source_refs."""
        from src.citation_surfaces import render_cli_debug

        criteria = _make_criteria()
        result = render_cli_debug(criteria, "TC01.01")

        assert "no source references" in result

    def test_privacy_mode_cli(self) -> None:
        """PRIVACY_MODE CLI debug omits quote text."""
        from src.citation_surfaces import render_cli_debug

        criteria = _make_criteria()
        result = render_cli_debug(criteria, "TC01.02", privacy_mode=True)

        # Quote should not be present
        assert "The maximum claim is five thousand pounds" not in result
        # Pointer info still present
        assert "policy.pdf" in result
        # Justification omitted
        assert "Doc p.9 states max" not in result


class TestRenderExportNote:
    """Tests for the self-documenting export note."""

    def test_quotes_included_note(self) -> None:
        """Default mode note says quotes are included."""
        from src.citation_surfaces import render_export_note

        note = render_export_note()
        assert "Source quotes included" in note
        assert "PRIVACY_MODE=1" in note

    def test_privacy_mode_note(self) -> None:
        """PRIVACY_MODE note says quotes are omitted."""
        from src.citation_surfaces import render_export_note

        note = render_export_note(privacy_mode=True)
        assert "quotes omitted" in note
        assert "PRIVACY_MODE=1" in note
