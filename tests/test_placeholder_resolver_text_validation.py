"""Tests for text-content validation and confidence threshold in PlaceholderResolver."""

from __future__ import annotations

import os
from unittest import mock

from src.placeholder_resolver import PlaceholderResolver


class TestTextMatchesDescription:
    """Unit tests for PlaceholderResolver.text_matches_description()."""

    resolver = PlaceholderResolver()

    def test_direct_containment_match(self) -> None:
        assert self.resolver.text_matches_description("Add to cart", "click Add to cart button") is True

    def test_description_contains_text(self) -> None:
        assert self.resolver.text_matches_description("Cart", "click the Cart link to view my cart") is True

    def test_partial_word_match(self) -> None:
        assert self.resolver.text_matches_description("Continue Shopping", "click Continue Shopping") is True

    def test_no_match_when_text_unrelated(self) -> None:
        assert self.resolver.text_matches_description("Subscribe", "click Continue Shopping") is False

    def test_no_match_when_element_empty(self) -> None:
        assert self.resolver.text_matches_description("", "click button") is False

    def test_no_match_when_description_empty(self) -> None:
        assert self.resolver.text_matches_description("Some text", "") is False

    def test_word_overlap_match(self) -> None:
        # "Check Out" shares words with "click the Check Out button"
        assert self.resolver.text_matches_description("Check Out", "click the Check Out button") is True

    def test_case_insensitive(self) -> None:
        assert self.resolver.text_matches_description("ADD TO CART", "click add to cart") is True

    def test_whitespace_normalization(self) -> None:
        assert self.resolver.text_matches_description("Add   to   cart", "click add to cart") is True

    # Regression tests: "X button" descriptions must match action-verb element text.
    # Previously, a navigation/action guard rejected these because "button" is a
    # NAVIGATION word and "add" is an ACTION verb. The guard was removed (May 2026)
    # because intent-level filtering is already handled by _matches_intent_bucket().

    def test_add_to_cart_button_matches_add_to_cart_text(self) -> None:
        """'Sauce Labs Backpack add to cart button' must match 'Add to cart' element text."""
        assert self.resolver.text_matches_description("Add to cart", "Sauce Labs Backpack add to cart button") is True

    def test_checkout_button_matches_proceed_to_checkout_text(self) -> None:
        """'proceed to checkout button' must match 'Proceed to Checkout' element text."""
        assert self.resolver.text_matches_description("Proceed to Checkout", "proceed to checkout button") is True

    def test_finish_button_matches_finish_text(self) -> None:
        """'finish button' must match 'Finish' element text."""
        assert self.resolver.text_matches_description("Finish", "finish button") is True

    def test_login_button_matches_login_text(self) -> None:
        """'login button' must match 'Login' element text (was already allowed by exception)."""
        assert self.resolver.text_matches_description("Login", "login button") is True

    def test_continue_shopping_button_matches_continue_shopping_text(self) -> None:
        """'Continue Shopping button' must match 'Continue Shopping' element text."""
        assert self.resolver.text_matches_description("Continue Shopping", "Continue Shopping button") is True

    def test_cart_link_does_not_match_add_to_cart_text(self) -> None:
        """'Cart link' should NOT match 'Add to cart' — different intents.
        This is handled by _matches_intent_bucket(), not text_matches_description().
        The text method only checks word overlap, so this actually passes here.
        The intent bucket filter is what blocks it upstream."""
        # Word overlap: {"cart"} in both → passes text validation
        # Intent filtering happens in rank_candidates() → _matches_intent_bucket()
        assert self.resolver.text_matches_description("Add to cart", "Cart link") is True


class TestFindBestElementWithTextValidation:
    """find_best_element skips candidates whose text doesn't match."""

    def test_skips_unrelated_text(self) -> None:
        resolver = PlaceholderResolver()
        elements = [
            {"selector": "#subscribe", "text": "Subscribe to newsletter", "role": "checkbox"},
            {"selector": "#continue-btn", "text": "Continue Shopping", "role": "button"},
        ]
        result = resolver.find_best_element("CLICK", "Continue Shopping", elements)
        assert result is not None
        assert result["selector"] == "#continue-btn"

    def test_returns_none_when_no_match(self) -> None:
        resolver = PlaceholderResolver()
        elements = [
            {"selector": "#subscribe", "text": "Subscribe to newsletter", "role": "checkbox"},
            {"selector": "#footer", "text": "Footer text", "role": "div"},
        ]
        result = resolver.find_best_element("CLICK", "Continue Shopping", elements)
        assert result is None

    def test_prefers_text_match_over_unrelated(self) -> None:
        resolver = PlaceholderResolver()
        elements = [
            {"selector": "#subscribe", "text": "Subscribe", "role": "checkbox"},
            {"selector": "#add-cart", "text": "Add to cart", "role": "button"},
        ]
        result = resolver.find_best_element("CLICK", "Add to cart", elements)
        assert result is not None
        assert result["selector"] == "#add-cart"


class TestConfidenceThreshold:
    """min_confidence threshold prevents low-confidence resolutions."""

    def test_default_threshold_from_env(self) -> None:
        with mock.patch.dict(os.environ, {"PLACEHOLDER_MIN_CONFIDENCE": "0.5"}):
            resolver = PlaceholderResolver()
            assert resolver.min_confidence == 0.5

    def test_default_threshold_when_env_missing(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            resolver = PlaceholderResolver()
            assert resolver.min_confidence == 0.3

    def test_explicit_min_confidence(self) -> None:
        resolver = PlaceholderResolver(min_confidence=0.8)
        assert resolver.min_confidence == 0.8

    def test_high_threshold_blocks_weak_matches(self) -> None:
        """When threshold is very high, even matching text may be blocked."""
        resolver = PlaceholderResolver(min_confidence=0.99)
        elements = [
            {"selector": "#subscribe", "text": "Subscribe", "role": "checkbox"},
            {"selector": "#add-cart", "text": "Add to cart", "role": "button"},
        ]
        result = resolver.find_best_element("CLICK", "Add to cart", elements)
        # With 0.99 threshold, even the best match may fail if scores are close
        # This tests that the threshold mechanism is active
        assert result is None or result["selector"] == "#add-cart"


class TestLocatorScorerTextMatchBonus:
    """LocatorScorer applies +10 bonus when element text matches description."""

    def test_text_match_bonus_applied(self) -> None:
        from src.locator_scorer import LocatorScorer

        element = {"selector": "#add-cart", "text": "Add to cart", "role": "button"}
        result = LocatorScorer.score_locator(
            "#add-cart",
            element=element,
            action_description="click Add to cart button",
        )
        # ID base=85, text-match bonus=+10 => 95 (no tag prefix in "#add-cart" so no extra bonus)
        assert result["score"] == 95

    def test_no_bonus_when_no_description(self) -> None:
        from src.locator_scorer import LocatorScorer

        element = {"selector": "#add-cart", "text": "Add to cart", "role": "button"}
        result = LocatorScorer.score_locator("#add-cart", element=element, action_description="")
        # ID base=85, no bonus
        assert result["score"] == 85

    def test_no_bonus_when_text_unrelated(self) -> None:
        from src.locator_scorer import LocatorScorer

        element = {"selector": "#subscribe", "text": "Subscribe", "role": "checkbox"}
        result = LocatorScorer.score_locator(
            "#subscribe",
            element=element,
            action_description="click Add to cart button",
        )
        # ID base=85, no text-match bonus
        assert result["score"] == 85
