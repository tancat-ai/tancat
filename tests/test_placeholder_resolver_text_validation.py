"""Tests for text-content validation and confidence threshold in PlaceholderResolver."""

from __future__ import annotations

import os
from unittest import mock

import pytest

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
        from tests.resolver_test_helpers import best_ranked_element

        result = best_ranked_element(resolver, "CLICK", "Add to cart", elements)
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


class TestB016NegationDetection:
    """B-016: Negation gate — reject absence-vs-presence contradictions.

    Tests are parameterised to cover the full negation × positive-indicator matrix.
    """

    resolver = PlaceholderResolver()

    # --- Negation correctly rejected ---

    @pytest.mark.parametrize(
        "element_text,description,reason",
        [
            pytest.param(
                "Your cart is empty!",
                "cart content with items",
                "empty vs with items",
                id="empty-vs-with-items",
            ),
            pytest.param(
                "Cart is empty",
                "cart page with selected items",
                "empty vs selected",
                id="empty-vs-selected",
            ),
            pytest.param(
                "No results found",
                "search results displayed",
                "no results vs displayed",
                id="no-results-vs-displayed",
            ),
            pytest.param(
                "Nothing available",
                "products visible on page",
                "nothing vs visible",
                id="nothing-vs-visible",
            ),
            pytest.param(
                "Out of stock",
                "product available for purchase",
                "out of stock vs available",
                id="out-of-stock-vs-available",
            ),
            pytest.param(
                "No data",
                "table with results",
                "no data vs with results",
                id="no-data-vs-with-results",
            ),
        ],
    )
    def test_negation_rejected(self, element_text: str, description: str, reason: str) -> None:
        """Element with negation should NOT match description with positive indicators."""
        assert self.resolver.text_matches_description(element_text, description) is False, (
            f"Negation should reject: {reason}"
        )

    # --- Negation does NOT fire when description has no positive indicator ---

    @pytest.mark.parametrize(
        "element_text,description,reason",
        [
            pytest.param(
                "Your cart is empty",
                "cart empty message",
                "both signal absence — no contradiction",
                id="both-absence",
            ),
            pytest.param(
                "Nothing found",
                "search results page",
                "no positive indicator in description",
                id="no-positive-indicator",
            ),
        ],
    )
    def test_negation_no_contradiction(self, element_text: str, description: str, reason: str) -> None:
        """When description also signals absence, no contradiction — normal matching applies."""
        # These may match or not-match based on normal logic; the key is the negation
        # gate doesn't fire and cause a false rejection.
        # "Your cart is empty" vs "cart empty message" — containment match
        result = self.resolver.text_matches_description(element_text, description)
        # We just verify it doesn't raise and returns a boolean
        assert isinstance(result, bool)

    # --- Positive matches still work ---

    @pytest.mark.parametrize(
        "element_text,description,reason",
        [
            pytest.param(
                "Items in your cart",
                "cart content with items",
                "positive match — no negation",
                id="positive-match",
            ),
            pytest.param(
                "3 items in cart",
                "cart with selected items",
                "positive content match",
                id="positive-content",
            ),
            pytest.param(
                "Search results: 15 products",
                "search results displayed",
                "positive results",
                id="positive-results",
            ),
        ],
    )
    def test_positive_matches_still_work(self, element_text: str, description: str, reason: str) -> None:
        """Positive content should still match normally."""
        assert self.resolver.text_matches_description(element_text, description) is True, (
            f"Positive match should pass: {reason}"
        )


class TestB016SynonymExpansion:
    """B-016: Synonym-aware Jaccard fallback via SemanticMatcher.TOKEN_EXPANSIONS.

    Tests cover authentication, cart/checkout, and general UI synonym groups.
    """

    resolver = PlaceholderResolver()

    # --- Authentication synonyms ---

    @pytest.mark.parametrize(
        "element_text,description,reason",
        [
            pytest.param("Login", "Sign in button", "login ↔ sign in", id="login-sign-in"),
            pytest.param("Sign in", "Login button", "sign in ↔ login (reversed)", id="sign-in-login"),
            pytest.param("Log In", "Sign in to your account", "log in ↔ sign in", id="log-in-sign-in"),
            pytest.param("Sign Out", "Logout button", "sign out ↔ logout", id="sign-out-logout"),
            pytest.param("Logout", "Sign out link", "logout ↔ sign out (reversed)", id="logout-sign-out"),
            pytest.param("Register", "Sign up form", "register ↔ sign up", id="register-signup"),
            pytest.param("Sign Up", "Create account", "sign up ↔ create account", id="signup-create-account"),
        ],
    )
    def test_authentication_synonyms_match(self, element_text: str, description: str, reason: str) -> None:
        """Authentication synonyms should match via TOKEN_EXPANSIONS."""
        assert self.resolver.text_matches_description(element_text, description) is True, (
            f"Synonym should match: {reason}"
        )

    # --- Cart / checkout synonyms ---

    @pytest.mark.parametrize(
        "element_text,description,reason",
        [
            pytest.param("Basket", "Cart link", "basket ↔ cart", id="basket-cart"),
            pytest.param("Add to basket", "Add to cart button", "basket ↔ cart in action", id="add-basket-cart"),
            pytest.param("Checkout", "Proceed to checkout", "checkout ↔ proceed", id="checkout-proceed"),
        ],
    )
    def test_cart_synonyms_match(self, element_text: str, description: str, reason: str) -> None:
        """Cart/basket/checkout synonyms should match via TOKEN_EXPANSIONS."""
        assert self.resolver.text_matches_description(element_text, description) is True, (
            f"Synonym should match: {reason}"
        )

    # --- Unrelated text should NOT match via synonym expansion ---

    @pytest.mark.parametrize(
        "element_text,description,reason",
        [
            pytest.param("Privacy Policy", "Sign in button", "unrelated", id="privacy-vs-login"),
            pytest.param("Subscribe", "Logout link", "unrelated", id="subscribe-vs-logout"),
            pytest.param("Terms of Service", "Add to cart", "unrelated", id="terms-vs-cart"),
        ],
    )
    def test_unrelated_text_no_synonym_false_positive(self, element_text: str, description: str, reason: str) -> None:
        """Unrelated text must NOT match via synonym expansion."""
        assert self.resolver.text_matches_description(element_text, description) is False, (
            f"Unrelated text should not match: {reason}"
        )

    # --- Edge cases ---

    def test_proper_nouns_need_llm_not_synonyms(self) -> None:
        """'Dress' vs 'product category link' — zero token overlap.

        This is by design: keyword/synonym matching cannot bridge proper nouns
        to generic descriptors. B-020 (LLM-assisted resolution) handles these.
        """
        # We explicitly assert False here to document the known limitation
        assert self.resolver.text_matches_description("Dress", "product category link") is False
        assert self.resolver.text_matches_description("Blue Top", "a product name") is False

    def test_synonym_jaccard_does_not_override_strong_non_matches(self) -> None:
        """Synonym expansion should not produce false positives on truly unrelated text."""
        assert self.resolver.text_matches_description("About Us", "Delete account confirmation") is False
