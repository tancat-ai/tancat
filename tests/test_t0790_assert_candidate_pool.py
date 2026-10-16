"""t-0790 - the ASSERT candidate-pool filters (the held-out ``wrong_element`` class).

The held-out gate's 14 ``wrong_element`` misses are the t-0749 Class C
residual: a wrong element wins the ASSERT semantic pool because it shares only
generic words, or because it is an interactive control that merely sits beside
the message. ``filter_assert_candidates`` drops those candidates before the LLM
chooses, so the criterion's own element (or an honest skip) wins instead.

Every test here fails without the change in ``src/element_matcher.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.element_matcher import ElementMatcher, filter_assert_candidates
from src.placeholder_resolver import PlaceholderResolver


def _element(**overrides: Any) -> dict[str, Any]:
    element: dict[str, Any] = {
        "selector": "",
        "id": "",
        "text": "",
        "role": "",
        "tag": "",
        "classes": "",
        "href": "",
        "name": "",
        "aria_label": "",
        "accessible_name": "",
        "data_test": "",
        "value": "",
    }
    element.update(overrides)
    return element


def _selectors(candidates: list[dict[str, Any]]) -> list[str]:
    return [str(c.get("selector", "")) for c in candidates]


# ---------------------------------------------------------------------------
# Stage 2 - a message ASSERT must not resolve to a bare control
# ---------------------------------------------------------------------------


def test_add_to_cart_control_is_dropped_for_the_confirmation() -> None:
    """eval-002 c3: "add to cart confirmation" is the message, not the button."""
    control = _element(selector='a.add-to-cart[data-product-id="11"]', role="link", tag="a", text="Add to cart")
    message = _element(selector=".text-center", role="paragraph", tag="p", text="Your product has been added to cart.")

    filtered = filter_assert_candidates("add to cart confirmation", [control, message])

    assert _selectors(filtered) == [".text-center"]


def test_place_order_control_is_dropped_for_the_success_message() -> None:
    """eval-006 c7: ``#place-order`` sits beside the success title but is not it."""
    control = _element(selector="#place-order", id="place-order", role="button", tag="button", text="Place Order")
    title = _element(
        selector="#success-title",
        id="success-title",
        role="heading",
        tag="h1",
        text="Order placed successfully",
    )

    filtered = filter_assert_candidates("order success message", [control, title])

    assert _selectors(filtered) == ["#success-title"]


def test_confirm_button_that_names_the_outcome_is_kept() -> None:
    """A control whose own text names the outcome is a legitimate target."""
    button = _element(selector="#confirm-order", id="confirm-order", role="button", tag="button", text="Confirm order")

    filtered = filter_assert_candidates("order confirmation message", [button])

    assert _selectors(filtered) == ["#confirm-order"]


# ---------------------------------------------------------------------------
# Stage 3 - identity floor
# ---------------------------------------------------------------------------


def test_zero_identity_candidate_is_dropped_when_a_named_one_exists() -> None:
    """eval-002 c5: "product name and price" names price; "Blue Top" does not."""
    heading = _element(selector='h4:has-text("Blue Top")', role="heading", tag="h4", text="Blue Top")
    price = _element(
        selector=".cart_total_price", role="paragraph", tag="p", classes="cart_total_price", text="Rs. 499"
    )

    filtered = filter_assert_candidates("product name and price", [heading, price])

    assert _selectors(filtered) == [".cart_total_price"]


def test_identity_floor_keeps_the_pool_when_nothing_bears_identity() -> None:
    """No over-filtering: when no candidate shares a token, the pool survives."""
    heading = _element(
        selector="h5:has-text('Student Registration Form')", role="heading", tag="h5", text="Student Registration Form"
    )
    header = _element(selector=".group-header", role="heading", tag="h4", text="Thanks for submitting the form")

    filtered = filter_assert_candidates("submission success message", [heading, header])

    assert _selectors(filtered) == ["h5:has-text('Student Registration Form')", ".group-header"]


# ---------------------------------------------------------------------------
# Stage 1 - polarity conflict
# ---------------------------------------------------------------------------


def test_error_sibling_is_dropped_for_a_success_message() -> None:
    """eval-010 c3: the success message must not accept ``#order-error``."""
    error = _element(selector="#order-error", id="order-error", role="paragraph", tag="p", text="Order failed")
    success = _element(
        selector="#order-success-title",
        id="order-success-title",
        role="heading",
        tag="h1",
        text="Order placed successfully",
    )

    filtered = filter_assert_candidates("order success message", [error, success])

    assert _selectors(filtered) == ["#order-success-title"]


# ---------------------------------------------------------------------------
# Wiring - the semantic pass must choose from the filtered pool
# ---------------------------------------------------------------------------


def test_resolve_assert_semantically_ignores_the_control() -> None:
    """The B-020 pool the semantic ranker sees excludes the control.

    Without the fix the pool is [control, message]; the default ranker has no
    generator and falls back to ``all_ranked[0]`` (the control).
    """
    matcher = ElementMatcher(PlaceholderResolver(), generator=None)
    control = _element(
        selector='a.add-to-cart[data-product-id="11"]',
        role="link",
        tag="a",
        text="Add to cart",
        is_visible=True,
    )
    message = _element(
        selector=".text-center",
        role="paragraph",
        tag="p",
        text="Your product has been added to cart.",
        is_visible=True,
    )

    result = asyncio.run(
        matcher._resolve_assert_semantically(
            all_ranked=[(100, control), (8, message)],
            description="add to cart confirmation",
            current_url="https://automationexercise.com/products",
        )
    )

    assert result is not None
    assert result["selector"] == ".text-center"


def test_filter_is_a_no_op_for_a_non_message_assert() -> None:
    """A normal ASSERT pool is untouched by the message-control rule."""
    item = _element(
        selector='[data-test="remove-sauce-labs-backpack"]',
        role="link",
        tag="a",
        text="Remove",
    )

    filtered = filter_assert_candidates("backpack item in cart", [item])

    assert _selectors(filtered) == ['[data-test="remove-sauce-labs-backpack"]']


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
