"""Unit tests for src/locator_scorer.py — Locator scoring by type/fragility."""

from __future__ import annotations

from src.locator_scorer import LocatorScorer


class TestScoreLocator:
    """Test score_locator returns correct type, score, and confidence."""

    def test_data_testid_gets_high_score(self) -> None:
        result = LocatorScorer.score_locator('[data-testid="add-to-cart"]')
        assert result["type"] == "data-testid"
        assert result["score"] == 100
        assert result["confidence"] == "high"

    def test_id_selector_gets_high_score(self) -> None:
        result = LocatorScorer.score_locator("#addToCart")
        assert result["type"] == "id"
        assert result["score"] == 85
        assert result["confidence"] == "high"

    def test_id_with_tag_bonus(self) -> None:
        result = LocatorScorer.score_locator("button#addToCart")
        assert result["type"] == "id"
        assert result["score"] == 90  # 85 + 5 for tag+ID

    def test_name_selector_gets_medium_high_score(self) -> None:
        result = LocatorScorer.score_locator("[name='email']")
        assert result["type"] == "name"
        assert result["score"] == 70
        assert result["confidence"] == "medium-high"

    def test_aria_label_gets_medium_score(self) -> None:
        result = LocatorScorer.score_locator("[aria-label='Add to cart']")
        assert result["type"] == "aria-label"
        assert result["score"] == 60
        assert result["confidence"] == "medium"

    def test_role_selector_gets_medium_score(self) -> None:
        result = LocatorScorer.score_locator("[role='button']")
        assert result["type"] == "role"
        assert result["score"] == 55
        assert result["confidence"] == "medium"

    def test_css_class_single_gets_medium_low_score(self) -> None:
        result = LocatorScorer.score_locator(".btn-primary")
        assert result["type"] == "css-class"
        assert result["score"] == 35  # 40 - 5 for single class
        assert result["confidence"] == "medium-low"

    def test_css_class_multiple_gets_bonus(self) -> None:
        result = LocatorScorer.score_locator(".btn.btn-primary")
        assert result["type"] == "css-class"
        assert result["score"] == 45  # 40 + 5 for multiple classes
        assert result["confidence"] == "medium-low"

    def test_has_text_gets_low_score(self) -> None:
        result = LocatorScorer.score_locator(':has-text("Add to Cart")')
        assert result["type"] == "text"
        assert result["score"] == 25
        assert result["confidence"] == "low"

    def test_xpath_gets_very_low_score(self) -> None:
        result = LocatorScorer.score_locator('//button[contains(text(), "Add")]')
        assert result["type"] == "xpath-text"
        assert result["score"] == 10
        assert result["confidence"] == "very-low"

    def test_bare_tag_gets_very_low_score(self) -> None:
        result = LocatorScorer.score_locator("button")
        assert result["type"] == "tag"
        assert result["score"] == 2  # 5 - 3 for bare tag penalty
        assert result["confidence"] == "very-low"

    def test_empty_selector_gets_zero_score(self) -> None:
        result = LocatorScorer.score_locator("")
        assert result["type"] == "unknown"
        assert result["score"] == 0
        assert result["confidence"] == "very-low"

    def test_whitespace_selector_gets_zero_score(self) -> None:
        result = LocatorScorer.score_locator("   ")
        assert result["type"] == "unknown"
        assert result["score"] == 0

    def test_fragments_are_present(self) -> None:
        """All locator types should have a fragility reason."""
        for loc_type in LocatorScorer.LOCATOR_SCORES:
            assert loc_type in LocatorScorer.FRAGILITY_REASONS

    def test_all_confidence_levels_defined(self) -> None:
        """All confidence labels should have a score range."""
        assert set(LocatorScorer.CONFIDENCE_LEVELS.keys()) == {
            "high",
            "medium-high",
            "medium",
            "medium-low",
            "low",
            "very-low",
        }


class TestScoreCandidates:
    """Test score_candidates sorts by score descending."""

    def test_sorts_by_score_descending(self) -> None:
        candidates = [
            {"selector": ".btn-primary", "element": {}},
            {"selector": '[data-testid="submit"]', "element": {}},
            {"selector": "#email", "element": {}},
        ]
        scored = LocatorScorer.score_candidates(candidates)
        scores = [c["score"] for c in scored]
        assert scores == sorted(scores, reverse=True)
        # data-testid first (100), then id (85), then css-class (35)
        assert scored[0]["selector"] == '[data-testid="submit"]'
        assert scored[1]["selector"] == "#email"
        assert scored[2]["selector"] == ".btn-primary"

    def test_shorter_selector_preferred_when_scores_equal(self) -> None:
        """When scores are equal, shorter selectors come first."""
        candidates = [
            {"selector": ".btn", "element": {}},
            {"selector": ".btn-primary", "element": {}},
        ]
        scored = LocatorScorer.score_candidates(candidates)
        assert scored[0]["selector"] == ".btn"


class TestGetFallbackCandidates:
    """Test get_fallback_candidates returns higher-scoring alternatives."""

    def test_returns_higher_scoring_only(self) -> None:
        """Only candidates with higher scores than the failed locator are returned."""
        all_candidates = [
            {"selector": '[data-testid="add-to-cart"]', "element": {}},
            {"selector": "#addToCart", "element": {}},
            {"selector": ".btn", "element": {}},
            {"selector": ":has-text('Add')", "element": {}},
        ]
        fallbacks = LocatorScorer.get_fallback_candidates(".btn", all_candidates, max_fallbacks=2)
        # .btn scores 35, so data-testid (100) and id (85) should be returned
        assert len(fallbacks) == 2
        assert fallbacks[0]["score"] > fallbacks[1]["score"]

    def test_excludes_failed_locator(self) -> None:
        """The failed locator itself should not appear in fallbacks."""
        all_candidates = [
            {"selector": "#addToCart", "element": {}},
            {"selector": ".btn", "element": {}},
        ]
        fallbacks = LocatorScorer.get_fallback_candidates("#addToCart", all_candidates)
        selectors = [f["selector"] for f in fallbacks]
        assert "#addToCart" not in selectors

    def test_respects_max_fallbacks(self) -> None:
        """Should return at most max_fallbacks candidates."""
        all_candidates = [
            {"selector": '[data-testid="a"]', "element": {}},
            {"selector": '[data-testid="b"]', "element": {}},
            {"selector": "#c", "element": {}},
            {"selector": "#d", "element": {}},
        ]
        fallbacks = LocatorScorer.get_fallback_candidates(".btn", all_candidates, max_fallbacks=2)
        assert len(fallbacks) <= 2

    def test_no_fallbacks_when_failed_is_best(self) -> None:
        """If the failed locator is already the highest-scoring, return empty."""
        all_candidates = [
            {"selector": ".btn", "element": {}},
            {"selector": ":has-text('Add')", "element": {}},
        ]
        fallbacks = LocatorScorer.get_fallback_candidates('[data-testid="best"]', all_candidates)
        # data-testid scores 100, nothing else is higher
        assert len(fallbacks) == 0


class TestScoreToConfidence:
    """Test _score_to_confidence maps scores to labels correctly."""

    def test_high_range(self) -> None:
        assert LocatorScorer._score_to_confidence(85) == "high"
        assert LocatorScorer._score_to_confidence(100) == "high"

    def test_medium_high_range(self) -> None:
        assert LocatorScorer._score_to_confidence(70) == "medium-high"
        assert LocatorScorer._score_to_confidence(84) == "medium-high"

    def test_medium_range(self) -> None:
        assert LocatorScorer._score_to_confidence(50) == "medium"
        assert LocatorScorer._score_to_confidence(64) == "medium"

    def test_medium_low_range(self) -> None:
        assert LocatorScorer._score_to_confidence(30) == "medium-low"
        assert LocatorScorer._score_to_confidence(49) == "medium-low"

    def test_low_range(self) -> None:
        assert LocatorScorer._score_to_confidence(15) == "low"
        assert LocatorScorer._score_to_confidence(29) == "low"

    def test_very_low_range(self) -> None:
        assert LocatorScorer._score_to_confidence(0) == "very-low"
        assert LocatorScorer._score_to_confidence(14) == "very-low"

    def test_out_of_range_defaults_to_very_low(self) -> None:
        # Scores above 100 should not happen (clamped), but if they do:
        assert LocatorScorer._score_to_confidence(101) == "very-low"
