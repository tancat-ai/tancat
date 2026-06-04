"""Tests for B-014 — ASSERT tokens resolving to wrong elements.

Validates the intent-aware scoring improvements:
- _assert_action_penalty penalises interactive elements for message assertions
- _assert_message_bonus rewards display/alert roles for message assertions
- SuccessAssertStrategy expanded terms match message-like descriptions
"""

from __future__ import annotations

from src.intent_matcher import SuccessAssertStrategy
from src.placeholder_scorers import PlaceholderScorer

# ------------------------------------------------------------------
# Fixtures: element dicts
# ------------------------------------------------------------------


def _make_delete_button() -> dict:
    """Element that looks like a cart delete button (the B-014 bug target)."""
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
    """Element that is the correct target for confirmation assertions."""
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


def _make_confirmation_span_with_text() -> dict:
    """A span with confirmation-like text."""
    return {
        "role": "",
        "tag": "span",
        "text": "Order complete - success!",
        "href": "",
        "id": "order-status",
        "data_test": "",
        "name": "",
        "aria_label": "",
        "aria_role": "",
        "classes": "success-message",
        "selector": "span#order-status",
    }


def _make_alert_role_element() -> dict:
    """Element with ARIA alert role."""
    return {
        "role": "alert",
        "tag": "div",
        "text": "Payment successful",
        "href": "",
        "id": "payment-alert",
        "data_test": "",
        "name": "",
        "aria_label": "",
        "aria_role": "",
        "classes": "alert",
        "selector": "div#payment-alert",
    }


def _make_action_link() -> dict:
    """A link with action-oriented href (should be penalised for ASSERT)."""
    return {
        "role": "link",
        "tag": "a",
        "text": "Remove",
        "href": "/cart?action=delete&item=123",
        "id": "remove-item-123",
        "data_test": "",
        "name": "",
        "aria_label": "",
        "aria_role": "",
        "classes": "",
        "selector": "a#remove-item-123",
    }


def _make_aria_alertdialog() -> dict:
    """Element with aria_role=alertdialog."""
    return {
        "role": "",
        "tag": "div",
        "text": "Order confirmed",
        "href": "",
        "id": "modal-confirmation",
        "data_test": "",
        "name": "",
        "aria_label": "",
        "aria_role": "alertdialog",
        "classes": "modal-content",
        "selector": "div#modal-confirmation",
    }


def _make_aria_label_confirmation() -> dict:
    """Element with confirmation text in aria_label."""
    return {
        "role": "",
        "tag": "div",
        "text": "",
        "href": "",
        "id": "notification-area",
        "data_test": "",
        "name": "",
        "aria_label": "Order success confirmation",
        "aria_role": "",
        "classes": "",
        "selector": "div#notification-area",
    }


# ------------------------------------------------------------------
# Test _is_message_like_assertion
# ------------------------------------------------------------------


class TestIsMessageLikeAssertion:
    def test_confirmation_message(self) -> None:
        assert PlaceholderScorer._is_message_like_assertion("confirmation message") is True

    def test_success_alert(self) -> None:
        assert PlaceholderScorer._is_message_like_assertion("success alert") is True

    def test_success_message(self) -> None:
        assert PlaceholderScorer._is_message_like_assertion("success message") is True

    def test_popup_notification(self) -> None:
        assert PlaceholderScorer._is_message_like_assertion("popup notification") is True

    def test_alert_message(self) -> None:
        assert PlaceholderScorer._is_message_like_assertion("alert message") is True

    def test_non_message_assertion(self) -> None:
        assert PlaceholderScorer._is_message_like_assertion("cart contains item") is False

    def test_product_visible(self) -> None:
        assert PlaceholderScorer._is_message_like_assertion("product is visible") is False

    def test_empty_description(self) -> None:
        assert PlaceholderScorer._is_message_like_assertion("") is False


# ------------------------------------------------------------------
# Test _assert_action_penalty
# ------------------------------------------------------------------


class TestAssertActionPenalty:
    def test_button_penalised_for_message_assertion(self) -> None:
        penalty = PlaceholderScorer._assert_action_penalty("ASSERT", "confirmation message", _make_delete_button())
        assert penalty < 0
        assert penalty == -15

    def test_submit_button_penalised(self) -> None:
        penalty = PlaceholderScorer._assert_action_penalty(
            "ASSERT", "success message", {"role": "submit", "tag": "button", "text": "Submit", "href": ""}
        )
        assert penalty == -15

    def test_action_link_penalised(self) -> None:
        penalty = PlaceholderScorer._assert_action_penalty("ASSERT", "confirmation message", _make_action_link())
        assert penalty < 0
        assert penalty == -10

    def test_no_penalty_for_non_message_assertion(self) -> None:
        penalty = PlaceholderScorer._assert_action_penalty("ASSERT", "cart contains item", _make_delete_button())
        assert penalty == 0

    def test_no_penalty_for_click_action(self) -> None:
        penalty = PlaceholderScorer._assert_action_penalty("CLICK", "confirmation message", _make_delete_button())
        assert penalty == 0

    def test_no_penalty_for_display_element(self) -> None:
        penalty = PlaceholderScorer._assert_action_penalty(
            "ASSERT", "confirmation message", _make_confirmation_dialog()
        )
        assert penalty == 0


# ------------------------------------------------------------------
# Test _assert_message_bonus
# ------------------------------------------------------------------


class TestAssertMessageBonus:
    def test_dialog_role_bonus(self) -> None:
        bonus = PlaceholderScorer._assert_message_bonus("ASSERT", "confirmation message", _make_confirmation_dialog())
        assert bonus == 15

    def test_alert_role_bonus(self) -> None:
        bonus = PlaceholderScorer._assert_message_bonus("ASSERT", "success message", _make_alert_role_element())
        assert bonus == 15

    def test_aria_alertdialog_bonus(self) -> None:
        bonus = PlaceholderScorer._assert_message_bonus("ASSERT", "confirmation message", _make_aria_alertdialog())
        assert bonus == 12

    def test_confirmation_text_bonus(self) -> None:
        bonus = PlaceholderScorer._assert_message_bonus(
            "ASSERT", "confirmation message", _make_confirmation_span_with_text()
        )
        assert bonus == 10

    def test_aria_label_confirmation_bonus(self) -> None:
        bonus = PlaceholderScorer._assert_message_bonus("ASSERT", "success message", _make_aria_label_confirmation())
        assert bonus == 8

    def test_no_bonus_for_non_message_assertion(self) -> None:
        bonus = PlaceholderScorer._assert_message_bonus("ASSERT", "cart contains item", _make_confirmation_dialog())
        assert bonus == 0

    def test_no_bonus_for_click_action(self) -> None:
        bonus = PlaceholderScorer._assert_message_bonus("CLICK", "confirmation message", _make_confirmation_dialog())
        assert bonus == 0

    def test_no_bonus_for_button_element(self) -> None:
        bonus = PlaceholderScorer._assert_message_bonus("ASSERT", "confirmation message", _make_delete_button())
        assert bonus == 0


# ------------------------------------------------------------------
# Integration: delete button scores lower than confirmation dialog
# ------------------------------------------------------------------


class TestAssertResolutionIntegration:
    def test_confirmation_dialog_beats_delete_button(self) -> None:
        """The core B-014 fix: confirmation dialog should score higher than
        a delete button for ASSERT targeting 'confirmation message'.

        The delete button may either be scored lower than the dialog, or
        filtered out entirely (score=None). Either outcome is acceptable.
        """
        description = "confirmation message"
        delete_score = PlaceholderScorer.compute_element_score(
            "ASSERT", description, _make_delete_button(), ".cart_quantity_delete", 0
        )
        dialog_score = PlaceholderScorer.compute_element_score(
            "ASSERT", description, _make_confirmation_dialog(), "div#confirmation-popup", 0
        )
        # Dialog must have a valid score
        assert dialog_score is not None, "Dialog should have a score"
        # Delete button is either filtered out (None) or scored lower than dialog
        if delete_score is not None:
            assert dialog_score > delete_score, (
                f"Dialog ({dialog_score}) must score higher than delete button ({delete_score}) "
                f"for ASSERT '{description}'"
            )

    def test_alert_element_beats_delete_button(self) -> None:
        alert_score = PlaceholderScorer.compute_element_score(
            "ASSERT", "success alert", _make_alert_role_element(), "div#payment-alert", 0
        )
        delete_score = PlaceholderScorer.compute_element_score(
            "ASSERT", "success alert", _make_delete_button(), ".cart_quantity_delete", 0
        )
        assert alert_score is not None
        if delete_score is not None:
            assert alert_score > delete_score

    def test_span_with_confirmation_text_beats_delete_button(self) -> None:
        span_score = PlaceholderScorer.compute_element_score(
            "ASSERT", "confirmation message", _make_confirmation_span_with_text(), "span#order-status", 0
        )
        delete_score = PlaceholderScorer.compute_element_score(
            "ASSERT", "confirmation message", _make_delete_button(), ".cart_quantity_delete", 0
        )
        assert span_score is not None
        if delete_score is not None:
            assert span_score > delete_score

    def test_delete_button_filtered_out_for_message_assertion(self) -> None:
        """Delete button should be filtered out (score=None) for message assertions
        due to combined penalty from _assert_action_penalty and visibility penalty."""
        delete_score = PlaceholderScorer.compute_element_score(
            "ASSERT", "confirmation message", _make_delete_button(), ".cart_quantity_delete", 0
        )
        # The button gets penalised: -15 (button role) and other penalties
        # With threshold=0, it should be filtered out
        assert delete_score is None or delete_score < 0


# ------------------------------------------------------------------
# Test SuccessAssertStrategy expanded terms
# ------------------------------------------------------------------


class TestSuccessAssertStrategyExpanded:
    """SuccessAssertStrategy requires BOTH success AND message keywords.

    This prevents over-claiming generic "confirmation message" assertions
    that should fall through to scoring-based resolution.
    """

    def test_matches_when_both_success_and_message_keywords(self) -> None:
        """'success confirmation message' has success + message -> claimed."""
        strategy = SuccessAssertStrategy()
        result = strategy.match("ASSERT", "success confirmation message", _make_confirmation_dialog())
        assert result is True

    def test_matches_success_alert_description(self) -> None:
        """'success alert' has success keyword + alert message keyword -> claimed."""
        strategy = SuccessAssertStrategy()
        result = strategy.match("ASSERT", "success alert", _make_alert_role_element())
        assert result is True

    def test_falls_through_for_confirmation_message_alone(self) -> None:
        """'confirmation message' alone has NO success keyword -> falls through to scoring.

        This is the key B-014 fix: generic 'confirmation message' assertions
        should be resolved by scoring (which now has assert penalties/bonuses),
        not by the intent matcher.
        """
        strategy = SuccessAssertStrategy()
        result = strategy.match("ASSERT", "confirmation message", _make_confirmation_dialog())
        assert result is None

    def test_falls_through_for_popup_alone(self) -> None:
        """'popup message' has NO success keyword -> falls through to scoring."""
        strategy = SuccessAssertStrategy()
        popup_element = {
            "role": "",
            "tag": "div",
            "text": "popup success",
            "href": "",
            "id": "popup",
            "data_test": "",
            "name": "",
            "aria_label": "",
            "aria_role": "",
            "classes": "",
            "selector": "div#popup",
        }
        result = strategy.match("ASSERT", "popup message", popup_element)
        assert result is None

    def test_no_match_for_non_assert_action(self) -> None:
        strategy = SuccessAssertStrategy()
        result = strategy.match("CLICK", "success confirmation message", _make_confirmation_dialog())
        assert result is None

    def test_no_match_for_unrelated_description(self) -> None:
        strategy = SuccessAssertStrategy()
        result = strategy.match("ASSERT", "cart contains item", _make_confirmation_dialog())
        assert result is None


# ------------------------------------------------------------------
# Regression: non-message ASSERT should not be affected
# ------------------------------------------------------------------


class TestNonMessageAssertUnaffected:
    def test_cart_assert_still_works(self) -> None:
        """ASSERT for cart items should not be penalised for buttons."""
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
        score = PlaceholderScorer.compute_element_score(
            "ASSERT", "cart contains product", cart_element, "div#cart-summary", 0
        )
        assert score is not None
        # Should not have assertion penalty (not message-like)
        penalty = PlaceholderScorer._assert_action_penalty("ASSERT", "cart contains product", cart_element)
        bonus = PlaceholderScorer._assert_message_bonus("ASSERT", "cart contains product", cart_element)
        assert penalty == 0
        assert bonus == 0

    def test_click_action_unaffected(self) -> None:
        """CLICK actions should not get assertion penalties or bonuses."""
        button = _make_delete_button()
        penalty = PlaceholderScorer._assert_action_penalty("CLICK", "delete item", button)
        bonus = PlaceholderScorer._assert_message_bonus("CLICK", "delete item", button)
        assert penalty == 0
        assert bonus == 0
