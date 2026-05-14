"""Tests for LLM-based disambiguation in PlaceholderResolver.

UAT Fix Series — Session 1: LLM Disambiguation for Placeholder Resolution
Created: 2026-05-13
"""

from unittest.mock import MagicMock, patch

from src.placeholder_resolver import (
    _MAX_DISAMBIGUATION_CANDIDATES,
    PlaceholderResolver,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_element(
    selector: str, text: str = "", role: str = "button", element_id: str = "", aria_label: str = ""
) -> dict:
    """Build a minimal element dict for testing."""
    return {
        "selector": selector,
        "text": text,
        "role": role,
        "id": element_id,
        "aria_label": aria_label,
        "href": "",
        "classes": "",
    }


# ── TestDisambiguationTrigger ────────────────────────────────────────────────


class TestDisambiguationTrigger:
    """Test that disambiguation triggers on near-ties."""

    def test_disambiguation_triggers_on_tie(self) -> None:
        """Top-2 candidates with same score should trigger LLM disambiguation."""
        resolver = PlaceholderResolver(
            use_llm_disambiguation=True,
            disambiguation_threshold=5,
        )
        elements = [
            _make_element(".link-a", text="Products", role="a"),
            _make_element(".link-b", text="Products", role="a"),
        ]
        with patch.object(resolver, "_disambiguate_with_llm", return_value=None) as mock_dis:
            resolver.find_best_element("CLICK", "products link", elements)
            # With identical scores (tie), disambiguation should be called
            assert mock_dis.called

    def test_disambiguation_triggers_on_near_tie(self) -> None:
        """Top-2 candidates within threshold should trigger LLM disambiguation."""
        resolver = PlaceholderResolver(
            use_llm_disambiguation=True,
            disambiguation_threshold=5,
        )
        elements = [
            _make_element(".link-a", text="Products", role="a"),
            _make_element(".link-b", text="Product", role="a"),
        ]
        with patch.object(resolver, "_disambiguate_with_llm", return_value=None) as mock_dis:
            resolver.find_best_element("CLICK", "products link", elements)
            # Scores are close (within threshold) → disambiguation called
            assert mock_dis.called

    def test_disambiguation_skipped_on_clear_winner(self) -> None:
        """Top-2 candidates far apart should NOT trigger LLM disambiguation."""
        resolver = PlaceholderResolver(
            use_llm_disambiguation=True,
            disambiguation_threshold=5,
            min_confidence=0.3,
        )
        # One element with exact match, one with no match → large score gap
        elements = [
            _make_element("#exact", text="Products Page Link", role="a"),
            _make_element(".unrelated", text="Close", role="button"),
        ]
        with patch.object(resolver, "_disambiguate_with_llm", return_value=None) as mock_dis:
            resolver.find_best_element("CLICK", "products page link", elements)
            # Clear winner → no disambiguation needed
            assert not mock_dis.called

    def test_disambiguation_skipped_when_single_candidate(self) -> None:
        """Only one candidate — no disambiguation needed."""
        resolver = PlaceholderResolver(
            use_llm_disambiguation=True,
            disambiguation_threshold=5,
        )
        elements = [_make_element("#only", text="Products", role="a")]
        with patch.object(resolver, "_disambiguate_with_llm", return_value=None) as mock_dis:
            resolver.find_best_element("CLICK", "products link", elements)
            assert not mock_dis.called


# ── TestDisambiguationLLMCall ────────────────────────────────────────────────


class TestDisambiguationLLMCall:
    """Test the LLM disambiguation method directly."""

    def test_disambiguation_returns_correct_element(self) -> None:
        """LLM picks option 2 → returns second candidate element."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True)
        candidates = [
            (50, _make_element(".link-a", text="Products", role="a")),
            (48, _make_element(".link-b", text="Products Nav", role="a", element_id="nav-products")),
        ]
        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.generate_test.return_value = "2"
            result = resolver._disambiguate_with_llm("CLICK", "products link", candidates)
            assert result is not None
            assert result["selector"] == ".link-b"

    def test_disambiguation_handles_out_of_range_response(self) -> None:
        """LLM returns invalid number → falls back to None."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True)
        candidates = [
            (50, _make_element(".link-a", text="Products", role="a")),
            (48, _make_element(".link-b", text="Products Nav", role="a")),
        ]
        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.generate_test.return_value = "99"
            result = resolver._disambiguate_with_llm("CLICK", "products link", candidates)
            assert result is None

    def test_disambiguation_handles_llm_error(self) -> None:
        """LLM call raises exception → returns None (fallback to rules)."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True)
        candidates = [
            (50, _make_element(".link-a", text="Products", role="a")),
            (48, _make_element(".link-b", text="Products Nav", role="a")),
        ]
        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.generate_test.side_effect = RuntimeError("LLM unavailable")
            result = resolver._disambiguate_with_llm("CLICK", "products link", candidates)
            assert result is None

    def test_disambiguation_prompt_includes_action_and_description(self) -> None:
        """Prompt contains the action type and description text."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True)
        candidates = [
            (50, _make_element(".a", text="X")),
            (48, _make_element(".b", text="Y")),
        ]
        captured_prompt: str | None = None

        def capture_prompt(prompt: str, timeout: int = 300) -> str:
            nonlocal captured_prompt
            captured_prompt = prompt
            return "1"

        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.generate_test.side_effect = capture_prompt
            resolver._disambiguate_with_llm("CLICK", "shopping cart icon", candidates)

        assert captured_prompt is not None
        assert "CLICK" in captured_prompt
        assert "shopping cart icon" in captured_prompt

    def test_disambiguation_prompt_includes_candidate_details(self) -> None:
        """Prompt contains text, role, selector for each candidate."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True)
        candidates = [
            (50, _make_element("#nav-link", text="Products", role="link", element_id="nav-link")),
            (48, _make_element(".brand-link", text="Products", role="a", element_id="brand-products")),
        ]
        captured_prompt: str | None = None

        def capture_prompt(prompt: str, timeout: int = 300) -> str:
            nonlocal captured_prompt
            captured_prompt = prompt
            return "1"

        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.generate_test.side_effect = capture_prompt
            resolver._disambiguate_with_llm("CLICK", "products link", candidates)

        assert captured_prompt is not None
        assert "#nav-link" in captured_prompt
        assert ".brand-link" in captured_prompt
        assert 'role="link"' in captured_prompt
        assert 'role="a"' in captured_prompt

    def test_disambiguation_with_aria_snapshot(self) -> None:
        """Aria snapshot context is included when available."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True)
        candidates = [
            (50, _make_element(".a", text="X")),
            (48, _make_element(".b", text="Y")),
        ]
        aria_snapshot = "generic: /products\n  link Products\n  link Products Brand"
        captured_prompt: str | None = None

        def capture_prompt(prompt: str, timeout: int = 300) -> str:
            nonlocal captured_prompt
            captured_prompt = prompt
            return "1"

        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.generate_test.side_effect = capture_prompt
            resolver._disambiguate_with_llm("CLICK", "products link", candidates, aria_snapshot=aria_snapshot)

        assert captured_prompt is not None
        assert "Page accessibility context:" in captured_prompt
        assert "/products" in captured_prompt


# ── TestProductsLinkScenario ─────────────────────────────────────────────────


class TestProductsLinkScenario:
    """Regression test for the 'Products link' vs brand product link scenario."""

    def test_products_link_prefers_navigation(self) -> None:
        """
        Given two 'Products' links — one in navigation, one brand marketing —
        the LLM should pick the navigation link for 'Products link'.
        """
        resolver = PlaceholderResolver(use_llm_disambiguation=True, disambiguation_threshold=5)
        candidates = [
            (55, _make_element(".nav-link", text="Products", role="a", element_id="nav-products")),
            (53, _make_element(".brand-link", text="Products", role="a", element_id="brand-products")),
        ]
        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            # LLM picks option 1 (navigation)
            mock_client.generate_test.return_value = "1"
            result = resolver._disambiguate_with_llm("CLICK", "products link", candidates)
            assert result is not None
            assert result["selector"] == ".nav-link"

    def test_products_link_fallback_to_rules(self) -> None:
        """
        When LLM unavailable, fall back to rule-based scoring.
        (May still pick wrong element — but doesn't crash.)
        """
        resolver = PlaceholderResolver(use_llm_disambiguation=True, disambiguation_threshold=5, min_confidence=0.3)
        elements = [
            _make_element(".nav-link", text="Products", role="a", element_id="nav-products"),
            _make_element(".brand-link", text="Products", role="a", element_id="brand-products"),
        ]
        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.generate_test.side_effect = RuntimeError("LLM down")
            # Should not raise — falls back to rule-based
            result = resolver.find_best_element("CLICK", "products link", elements)
            # Both have "Products" text → first ranked candidate wins
            assert result is not None


# ── TestDisambiguationConfig ─────────────────────────────────────────────────


class TestDisambiguationConfig:
    """Test environment variable configuration."""

    def test_disambiguation_disabled_via_env(self) -> None:
        """USE_LLM_DISAMBIGUATION=false skips LLM call."""
        resolver = PlaceholderResolver(
            use_llm_disambiguation=False,
            disambiguation_threshold=5,
        )
        elements = [
            _make_element(".link-a", text="Products", role="a"),
            _make_element(".link-b", text="Products", role="a"),
        ]
        with patch.object(resolver, "_disambiguate_with_llm", return_value=None) as mock_dis:
            resolver.find_best_element("CLICK", "products link", elements)
            assert not mock_dis.called

    def test_custom_threshold(self) -> None:
        """DISAMBIGUATION_THRESHOLD=10 uses custom threshold."""
        resolver = PlaceholderResolver(
            use_llm_disambiguation=True,
            disambiguation_threshold=10,
        )
        assert resolver.disambiguation_threshold == 10


# ── Additional integration tests ─────────────────────────────────────────────


class TestDisambiguationIntegration:
    """Integration tests for disambiguation in find_best_element pipeline."""

    def test_aria_snapshot_extracted_from_page_elements(self) -> None:
        """Aria snapshot stored as __meta__ element is extracted and passed to LLM."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True, disambiguation_threshold=5)
        page_elements = [
            {"__meta__": "aria_snapshot", "text": "link Products Navigation"},
            _make_element(".nav-link", text="Products", role="a"),
            _make_element(".brand-link", text="Products", role="a"),
        ]
        captured_snapshot: str | None = None

        def capture_disambiguation(
            action: str,
            description: str,
            candidates: list,
            aria_snapshot: str | None = None,
        ) -> dict:
            nonlocal captured_snapshot
            captured_snapshot = aria_snapshot
            return candidates[0][1]  # Return first candidate

        with patch.object(resolver, "_disambiguate_with_llm", side_effect=capture_disambiguation):
            resolver.find_best_element("CLICK", "products link", page_elements)

        assert captured_snapshot is not None
        assert "Navigation" in captured_snapshot

    def test_disambiguation_respects_max_candidates(self) -> None:
        """Only MAX_DISAMBIGUATION_CANDIDATES are sent to LLM."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True, disambiguation_threshold=5)
        candidates = [(50, _make_element(f".el-{i}", text="Products", role="a")) for i in range(10)]
        with patch("src.placeholder_resolver.LLMClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.generate_test.return_value = "1"
            resolver._disambiguate_with_llm("CLICK", "products link", candidates)

            # Verify the prompt was called — check that generate_test was invoked
            assert mock_client.generate_test.called
            prompt_arg = mock_client.generate_test.call_args[0][0]
            # Should have at most _MAX_DISAMBIGUATION_CANDIDATES options
            option_count = prompt_arg.count('text="')
            assert option_count <= _MAX_DISAMBIGUATION_CANDIDATES

    def test_disambiguation_single_candidate_returns_none(self) -> None:
        """_disambiguate_with_llm with only one candidate returns None."""
        resolver = PlaceholderResolver(use_llm_disambiguation=True)
        candidates = [(50, _make_element(".only", text="Products"))]
        result = resolver._disambiguate_with_llm("CLICK", "products link", candidates)
        assert result is None
