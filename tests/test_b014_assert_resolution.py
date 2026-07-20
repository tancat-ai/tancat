"""Tests for B-014 — ASSERT tokens resolving to wrong elements.

Covers two mechanisms:

1. **Step-context exclusion** (current fix) — ASSERT excludes the selector
   from the immediately preceding CLICK/FILL step unless descriptions
   reference the same element. Lives in PlaceholderOrchestrator.

2. **Message-aware scoring** (legacy, kept for message-like ASSERTs) —
   penalises interactive elements and rewards display elements when the
   ASSERT description contains message-like terms. Lives in
   PlaceholderScorer / SuccessAssertStrategy.
"""

from __future__ import annotations

from src.element_matcher import _is_excluded
from src.intent_matcher import SuccessAssertStrategy
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_scorers import PlaceholderScorer

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_delete_button() -> dict:
    return {
        "role": "button",
        "tag": "button",
        "text": "",
        "href": "",
        "id": "cart_quantity_delete",
        "data_test": "",
        "name": "",
        "aria_label": "",
        "aria_role": "",
        "classes": "fa fa-trash",
        "selector": "button.cart_quantity_delete",
    }


def _make_confirmation_dialog() -> dict:
    return {
        "role": "dialog",
        "tag": "div",
        "text": "Your order has been confirmed! Thank you for your purchase.",
        "href": "",
        "id": "confirmation-popup",
        "data_test": "confirmation-message",
        "name": "",
        "aria_label": "",
        "aria_role": "",
        "classes": "alert-success",
        "selector": "div#confirmation-popup",
    }


# ------------------------------------------------------------------
# 1. Step-context exclusion — the active B-014 fix
# ------------------------------------------------------------------


class TestBuildExcludedSelectors:
    """_build_excluded_selectors is a deterministic gate, not a scorer."""

    def _orch(self) -> PlaceholderOrchestrator:
        return PlaceholderOrchestrator()

    def test_empty_for_non_assert_action(self) -> None:
        excluded = self._orch()._build_excluded_selectors(
            action="CLICK",
            description="login button",
            previous_selector="#login-button",
            previous_description="login button",
            pages_data={},
        )
        assert excluded == set()

    def test_empty_when_no_previous_selector(self) -> None:
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="page title",
            previous_selector=None,
            previous_description=None,
            pages_data={},
        )
        assert excluded == set()

    def test_empty_when_descriptions_match(self) -> None:
        """Same element, same concept → allow reuse."""
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="login button is disabled",
            previous_selector="#login-button",
            previous_description="login button",
            pages_data={},
        )
        assert excluded == set()

    def test_excludes_when_descriptions_differ(self) -> None:
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="inventory page title",
            previous_selector="#login-button",
            previous_description="login button",
            pages_data={},
        )
        assert "#login-button" in excluded

    def test_includes_raw_and_robust_selector_forms(self) -> None:
        pages_data = {
            "https://example.com": [
                {
                    "id": "login-button",
                    "selector": "input#login-button",
                    "tag": "input",
                    "text": "",
                    "role": "button",
                },
            ],
        }
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="page title",
            previous_selector="#login-button",
            previous_description="login button",
            pages_data=pages_data,
        )
        assert "#login-button" in excluded
        assert "input#login-button" in excluded

    def test_fill_sets_exclusion_bar(self) -> None:
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="thank you message",
            previous_selector="#user-name",
            previous_description="username input",
            pages_data={},
        )
        assert "#user-name" in excluded


class TestIsExcluded:
    def test_excluded_by_raw_selector(self) -> None:
        assert _is_excluded({"selector": "#login-button"}, {"#login-button"}) is True

    def test_excluded_by_robust_locator(self) -> None:
        element = {
            "selector": "input#login-button",
            "id": "login-button",
            "tag": "input",
            "text": "",
        }
        assert _is_excluded(element, {"#login-button"}) is True

    def test_not_excluded_when_different(self) -> None:
        assert _is_excluded({"selector": "#other"}, {"#login-button"}) is False

    def test_not_excluded_when_empty_set(self) -> None:
        assert _is_excluded({"selector": "#login-button"}, set()) is False


class TestSaucedemoStepContextScenarios:
    """Real-world scenarios from saucedemo UAT failures."""

    def _orch(self) -> PlaceholderOrchestrator:
        return PlaceholderOrchestrator()

    def test_login_then_assert_inventory_excludes_login_button(self) -> None:
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="inventory page title",
            previous_selector="#login-button",
            previous_description="login button",
            pages_data={},
        )
        assert "#login-button" in excluded

    def test_add_to_cart_then_assert_badge_excludes_add_button(self) -> None:
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="cart badge with count 1",
            previous_selector="#add-to-cart-sauce-labs-backpack",
            previous_description="add to cart button for Sauce Labs Backpack",
            pages_data={},
        )
        assert "#add-to-cart-sauce-labs-backpack" in excluded

    def test_backpack_add_then_assert_in_cart_excludes_remove_button(self) -> None:
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="Sauce Labs Backpack name in cart",
            previous_selector="#remove-sauce-labs-backpack",
            previous_description="add to cart button for Sauce Labs Backpack",
            pages_data={
                "https://example.com": [
                    {
                        "selector": "#remove-sauce-labs-backpack",
                        "id": "remove-sauce-labs-backpack",
                        "tag": "button",
                        "text": "",
                        "role": "button",
                        "href": "",
                        "data_test": "",
                        "classes": "",
                    },
                ]
            },
        )
        assert "#remove-sauce-labs-backpack" in excluded

    def test_checkout_button_then_assert_form_excludes_checkout(self) -> None:
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="checkout information form",
            previous_selector="#checkout",
            previous_description="checkout button",
            pages_data={},
        )
        assert "#checkout" in excluded

    def test_same_description_allows_reuse(self) -> None:
        """ASSERT for same element as previous step — allowed."""
        excluded = self._orch()._build_excluded_selectors(
            action="ASSERT",
            description="login button is disabled",
            previous_selector="#login-button",
            previous_description="login button",
            pages_data={},
        )
        assert excluded == set()


# ------------------------------------------------------------------
# 2. Message-aware scoring — legacy, kept for message-like ASSERTs
# ------------------------------------------------------------------


class TestAssertScoringRegression:
    """Ensure message-aware scoring still works and doesn't break non-message ASSERTs."""

    def test_dialog_beats_delete_button_for_message_assertion(self) -> None:
        """Core: confirmation dialog must score higher than a delete button."""
        dialog_score = PlaceholderScorer.compute_element_score(
            "ASSERT",
            "confirmation message",
            _make_confirmation_dialog(),
            "div#confirmation-popup",
            0,
        )
        delete_score = PlaceholderScorer.compute_element_score(
            "ASSERT",
            "confirmation message",
            _make_delete_button(),
            ".cart_quantity_delete",
            0,
        )
        assert dialog_score is not None
        if delete_score is not None:
            assert dialog_score > delete_score

    def test_non_message_assert_not_penalised(self) -> None:
        """ASSERT for cart items should not trigger message penalties/bonuses."""
        cart_element = {
            "role": "",
            "tag": "div",
            "text": "Product Name - Quantity: 1",
            "href": "",
            "id": "cart-summary",
            "data_test": "cart_description",
            "name": "",
            "aria_label": "",
            "aria_role": "",
            "classes": "",
            "selector": "div#cart-summary",
        }
        assert PlaceholderScorer._assert_action_penalty("ASSERT", "cart contains product", cart_element) == 0
        assert PlaceholderScorer._assert_message_bonus("ASSERT", "cart contains product", cart_element) == 0

    def test_click_actions_not_affected(self) -> None:
        assert PlaceholderScorer._assert_action_penalty("CLICK", "delete item", _make_delete_button()) == 0
        assert PlaceholderScorer._assert_message_bonus("CLICK", "delete item", _make_delete_button()) == 0

    def test_success_strategy_requires_both_keywords(self) -> None:
        """SuccessAssertStrategy needs BOTH success + message keyword."""
        strategy = SuccessAssertStrategy()
        # Has both → matches
        assert strategy.match("ASSERT", "success confirmation message", _make_confirmation_dialog()) is True
        # Missing success keyword → falls through
        assert strategy.match("ASSERT", "confirmation message", _make_confirmation_dialog()) is None
        # Missing message keyword → falls through
        assert strategy.match("ASSERT", "order complete", _make_confirmation_dialog()) is None
