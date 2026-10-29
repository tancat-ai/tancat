"""Tests for placeholder resolution."""

import pytest

from src.placeholder_resolver import PlaceholderResolver
from tests.resolver_test_helpers import best_ranked_element, resolve_placeholders


def test_resolve_all_returns_real_selector_for_matching_placeholder() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "login button")]
    pages = {"https://example.com": [{"selector": "#login", "text": "Login Button", "role": "button"}]}

    # _build_robust_locator prefers ID-based (#login) over text-based locators
    assert resolve_placeholders(resolver, placeholders, pages) == ["'#login'"]


def test_resolve_all_returns_pytest_skip_when_no_match_found() -> None:
    resolver = PlaceholderResolver(match_threshold=2)
    placeholders = [("CLICK", "checkout button")]
    pages = {"https://example.com": [{"selector": "#login", "text": "Login", "role": "button"}]}

    resolution = resolve_placeholders(resolver, placeholders, pages)[0]
    assert "pytest.skip" in resolution
    assert "checkout button" in resolution


def test_resolve_all_matches_cart_link_using_href_and_synonyms() -> None:
    resolver = PlaceholderResolver(match_threshold=2)
    placeholders = [("CLICK", "cart icon or link")]
    pages = {
        "https://example.com/": [
            {
                "selector": 'a[href="/view_cart"]',
                "text": "Cart",
                "role": "a",
                "href": "https://example.com/view_cart",
            }
        ]
    }

    # _build_robust_locator prefers href-based for link elements
    assert resolve_placeholders(resolver, placeholders, pages) == ["'a[href=\"/view_cart\"]'"]


def test_resolve_all_maps_navigation_placeholders_to_matching_urls() -> None:
    resolver = PlaceholderResolver(match_threshold=2)
    placeholders = [
        ("GOTO", "ecommerce_store_home"),
        ("URL", "cart page"),
        ("GOTO", "checkout page"),
    ]
    pages: dict[str, list[dict[str, str]]] = {
        "https://example.com/": [],
        "https://example.com/view_cart": [],
        "https://example.com/checkout": [],
    }

    assert resolve_placeholders(resolver, placeholders, pages) == [
        "'https://example.com/'",
        "'https://example.com/view_cart'",
        "'https://example.com/checkout'",
    ]


def test_click_add_to_cart_does_not_match_cart_navigation_link() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "add items to cart")]
    pages = {
        "https://example.com/": [
            {
                "selector": '[data-product-id="11"]',
                "text": "Add to cart",
                "role": "a",
                "href": "",
                "classes": "btn btn-default add-to-cart",
            },
            {
                "selector": 'a[href="/view_cart"]',
                "text": "Cart",
                "role": "a",
                "href": "https://example.com/view_cart",
                "classes": "",
            },
        ]
    }

    # _build_robust_locator prefers data-attribute with class prefix
    assert resolve_placeholders(resolver, placeholders, pages) == ["'.add-to-cart.btn[data-product-id=\"11\"]'"]


def test_click_checkout_prefers_checkout_over_payment() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "proceed to checkout button")]
    pages = {
        "https://example.com/view_cart": [
            {
                "selector": 'a[href="/payment"]',
                "text": "Payment",
                "role": "a",
                "href": "https://example.com/payment",
                "classes": "",
            },
            {
                "selector": 'a[href="/checkout"]',
                "text": "Proceed To Checkout",
                "role": "a",
                "href": "https://example.com/checkout",
                "classes": "btn btn-default check_out",
            },
        ]
    }

    # _build_robust_locator prefers href-based for link elements
    assert resolve_placeholders(resolver, placeholders, pages) == ["'a[href=\"/checkout\"]'"]


def test_assert_generic_home_page_skips_instead_of_guessing_weak_match() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("ASSERT", "home page")]
    pages = {
        "https://example.com/": [
            {
                "selector": ".fc-vendor-policy-link",
                "text": "Vendor policy",
                "role": "a",
                "href": "https://example.com/policy",
                "classes": "fc-vendor-policy-link",
            }
        ]
    }

    resolution = resolve_placeholders(resolver, placeholders, pages)[0]
    assert "pytest.skip" in resolution


def test_click_two_word_description_skips_when_only_one_word_matches() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "product card")]
    pages = {
        "https://example.com/products": [
            {
                "selector": 'a[href="/brand_products/example"]',
                "text": "Products",
                "role": "a",
                "href": "https://example.com/brand_products/example",
                "classes": "",
            }
        ]
    }

    resolution = resolve_placeholders(resolver, placeholders, pages)[0]
    assert "pytest.skip" in resolution


# --------------------------------------------------------------------------
# Tests for enhanced subscribe/newsletter guard (Fix #1)
# --------------------------------------------------------------------------


def test_subscribe_guard_rejects_empty_subscribe_input_for_continue_shopping_click() -> None:
    """A CLICK for "Continue Shopping" should NOT match an empty newsletter input.

    This was the root cause of the automationexercise.com failure where #subscribe
    (an email input with no visible text) kept winning over actual clickable buttons.
    """
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "Continue Shopping button")]
    pages = {
        "https://example.com/": [
            # The problematic element — empty newsletter input
            {
                "selector": "#subscribe",
                "text": "",
                "role": "input",
                "id": "subscribe",
                "classes": "form-control",
            },
            # A better match — button with actual text
            {
                "selector": ".btn.btn-default",
                "text": "Continue Shopping",
                "role": "button",
                "id": "",
                "classes": "btn btn-default",
            },
        ]
    }

    result = resolve_placeholders(resolver, placeholders, pages)
    # Should match the button with text, NOT the subscribe input
    assert "pytest.skip" not in result[0]
    assert "#subscribe" not in result[0]


def test_subscribe_guard_rejects_subscribe_element_for_cart_checkout_actions() -> None:
    """Cart/checkout actions should never match subscribe/newsletter elements."""
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "cart icon")]
    pages = {
        "https://example.com/": [
            {
                "selector": "#susbscribe_email",
                "text": "",
                "role": "input",
                "id": "susbscribe_email",
                "classes": "form-control newsletter",
            },
            {
                "selector": 'a[href="/view_cart"]',
                "text": "Cart",
                "role": "a",
                "href": "https://example.com/view_cart",
                "id": "",
                "classes": "",
            },
        ]
    }

    result = resolve_placeholders(resolver, placeholders, pages)
    assert "pytest.skip" not in result[0]
    assert "#susbscribe_email" not in result[0]


def test_subscribe_guard_rejects_subscribe_for_popup_modal_actions() -> None:
    """Popup/modal related clicks should never match subscribe elements."""
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "close popup button")]
    pages = {
        "https://example.com/": [
            {
                "selector": "#newsletter_email",
                "text": "",
                "role": "input",
                "id": "newsletter_email",
                "classes": "form-control",
            },
            {
                "selector": ".modal-close",
                "text": "Close",
                "role": "button",
                "id": "",
                "classes": "modal-close",
            },
        ]
    }

    result = resolve_placeholders(resolver, placeholders, pages)
    assert "pytest.skip" not in result[0]
    assert "#newsletter_email" not in result[0]


def test_text_content_penalty_favors_element_with_text_for_click_actions() -> None:
    """CLICK actions should penalize elements with no visible text when description has content words."""
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "Add to cart button")]
    pages = {
        "https://example.com/": [
            # Empty element — should be penalized
            {
                "selector": "#some_empty_div",
                "text": "",
                "role": "div",
                "id": "some_empty_div",
                "classes": "",
            },
            # Element with matching text — should win
            {
                "selector": ".btn.add-to-cart",
                "text": "Add to cart",
                "role": "button",
                "id": "",
                "classes": "btn add-to-cart",
            },
        ]
    }

    result = resolve_placeholders(resolver, placeholders, pages)
    assert "pytest.skip" not in result[0]
    assert "#some_empty_div" not in result[0]


# ---------------------------------------------------------------------------
# Session 1 (May 2026) — Visibility filtering + generic selector penalties
# ---------------------------------------------------------------------------


def test_rank_candidates_skips_hidden_role_elements() -> None:
    """Elements with role='hidden' must be excluded from ranked candidates."""
    resolver = PlaceholderResolver(match_threshold=1)
    elements = [
        {
            "selector": "#csrf_token",
            "text": "",
            "role": "hidden",
            "id": "csrf_token",
            "classes": "",
        },
        {
            "selector": "#visible_btn",
            "text": "Submit",
            "role": "button",
            "id": "visible_btn",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "submit button", elements)
    # Hidden element must not appear in results
    selectors = [el["selector"] for _, el in ranked]
    assert "#csrf_token" not in selectors
    assert "#visible_btn" in selectors


def test_rank_candidates_penalizes_click_on_no_text_elements() -> None:
    """CLICK actions on elements with no visible text should be penalized (-10)."""
    resolver = PlaceholderResolver(match_threshold=1)
    elements = [
        # No-text element — should be heavily penalized for CLICK
        {
            "selector": "#empty_btn",
            "text": "",
            "role": "button",
            "id": "empty_btn",
            "classes": "",
        },
        # Element with matching text — should rank higher
        {
            "selector": "#labeled_btn",
            "text": "Add to cart",
            "role": "button",
            "id": "labeled_btn",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "add to cart button", elements)
    # The element with text should rank first (higher score due to no penalty + word match)
    assert len(ranked) >= 1
    top_selector = ranked[0][1]["selector"]
    assert top_selector == "#labeled_btn"


def test_rank_candidates_penalizes_generic_assert_selectors() -> None:
    """ASSERT actions with single-class selectors and no text should be penalized."""
    resolver = PlaceholderResolver(match_threshold=1)
    elements = [
        # Generic single-class selector, no text — should be penalized for ASSERT
        {
            "selector": ".btn",
            "text": "",
            "role": "button",
            "id": "",
            "classes": "btn",
        },
        # Specific element with descriptive text — should rank higher
        {
            "selector": "#confirmation_msg",
            "text": "Product added to cart!",
            "role": "div",
            "id": "confirmation_msg",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("ASSERT", "product added confirmation message", elements)
    # The specific element with matching text should rank first
    assert len(ranked) >= 1
    top_selector = ranked[0][1]["selector"]
    assert top_selector == "#confirmation_msg"


def test_rank_candidates_prefers_more_descriptive_text() -> None:
    """When multiple candidates have the same score, prefer elements with longer text."""
    resolver = PlaceholderResolver(match_threshold=1)
    elements = [
        {
            "selector": "#short",
            "text": "OK",
            "role": "button",
            "id": "short",
            "classes": "",
        },
        {
            "selector": "#descriptive",
            "text": "Continue Shopping",
            "role": "button",
            "id": "descriptive",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "continue shopping button", elements)
    # Both have text, but 'descriptive' has more matching words so should rank higher
    assert len(ranked) >= 1
    top_selector = ranked[0][1]["selector"]
    assert top_selector == "#descriptive"


def test_find_best_element_skips_hidden_role() -> None:
    """find_best_element must never return a hidden-role element."""
    resolver = PlaceholderResolver(match_threshold=1)
    elements = [
        {
            "selector": "#hidden_input",
            "text": "",
            "role": "hidden",
            "id": "hidden_input",
            "classes": "",
        },
    ]

    result = best_ranked_element(resolver, "FILL", "some field", elements)
    assert result is None


def test_find_best_element_prefers_text_matching_for_assert() -> None:
    """ASSERT should prefer elements where text matches description over generic selectors."""
    resolver = PlaceholderResolver(match_threshold=1)
    elements = [
        # Generic class, no text — penalized for ASSERT
        {
            "selector": ".btn",
            "text": "",
            "role": "button",
            "id": "",
            "classes": "btn",
        },
        # Specific element with matching text
        {
            "selector": "h2.product-title",
            "text": "Product added to cart!",
            "role": "heading",
            "id": "",
            "classes": "product-title",
        },
    ]

    result = best_ranked_element(resolver, "ASSERT", "product added confirmation message", elements)
    assert result is not None
    assert result["selector"] == "h2.product-title"


# --------------------------------------------------------------------------
# Session 3 (May 2026) — ASSERT Specificity: text content overlap bonus
# --------------------------------------------------------------------------


def test_rank_candidates_adds_text_overlap_bonus_for_assert() -> None:
    """ASSERT actions should get a scoring bonus when element text overlaps with description."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        {
            "selector": "#order_status",
            "text": "Order status updated successfully",
            "role": "div",
            "id": "order_status",
            "classes": "",
        },
    ]
    ranked = resolver.rank_candidates("ASSERT", "order status updated message visible", elements)
    assert len(ranked) >= 1
    top_selector = ranked[0][1]["selector"]
    assert top_selector == "#order_status", f"Text-overlap element should rank first, got {top_selector}"


def test_rank_candidates_text_overlap_bonus_for_click() -> None:
    """CLICK actions should also get text overlap bonus when description matches element text."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        # Element with matching text — gets bonus
        {
            "selector": "#add_to_cart_btn",
            "text": "Add to Cart - Red Widget",
            "role": "button",
            "id": "add_to_cart_btn",
            "classes": "",
        },
        # Element with no text match — lower score
        {
            "selector": "#remove_item_btn",
            "text": "Remove Item",
            "role": "button",
            "id": "remove_item_btn",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "add to cart button for red widget", elements)
    assert len(ranked) >= 1, f"Expected at least one candidate in {ranked}"
    top_selector = ranked[0][1]["selector"]
    assert top_selector == "#add_to_cart_btn", f"Text-matching element should rank first, got {top_selector}"


def test_find_best_element_prefers_text_overlap_for_assert() -> None:
    """find_best_element should return the element with better text overlap for ASSERT."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        # Weak text match — no overlap with description
        {
            "selector": "#close_modal",
            "text": "X",
            "role": "button",
            "id": "close_modal",
            "classes": "",
        },
        # Strong text match — key words overlap
        {
            "selector": "#success_msg",
            "text": "Your order has been placed successfully",
            "role": "div",
            "id": "success_msg",
            "classes": "",
        },
    ]

    result = best_ranked_element(resolver, "ASSERT", "order placed successfully message visible", elements)
    assert result is not None, f"Expected a match, got {result}"
    assert result["selector"] == "#success_msg", f"Text-overlap element should win, got {result['selector']}"


def test_rank_candidates_no_false_bonus_for_non_matching_text() -> None:
    """Text overlap bonus should NOT trigger when there's no meaningful word overlap."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        # No meaningful overlap with "checkout confirmation"
        {
            "selector": "#login_form",
            "text": "Enter your username and password to log in",
            "role": "form",
            "id": "login_form",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("ASSERT", "checkout confirmation visible", elements)
    # Should have very low or no score since there's no meaningful overlap
    if len(ranked) > 0:
        top_score = ranked[0][0]
        assert top_score < 50, f"Non-matching text should not get high bonus, got score {top_score}"


def test_text_matches_description_with_overlap() -> None:
    """text_matches_description should return True when significant words overlap."""
    # Full description matches part of element text
    assert (
        PlaceholderResolver.text_matches_description(
            "Order status updated successfully",
            "order status updated message visible",
        )
        is True
    )

    # Partial overlap — at least half the content words match
    assert (
        PlaceholderResolver.text_matches_description(
            "Add to cart for red widget",
            "add to cart button for red product",
        )
        is True
    )

    # No meaningful overlap
    assert (
        PlaceholderResolver.text_matches_description(
            "Privacy Policy",
            "checkout confirmation visible",
        )
        is False
    )

    # Single word match (not enough)
    assert (
        PlaceholderResolver.text_matches_description(
            "Log in",
            "order placed successfully message",
        )
        is False
    )


def test_text_matches_description_handles_underscores() -> None:
    """text_matches_description should normalize underscores to spaces."""
    assert (
        PlaceholderResolver.text_matches_description(
            "Add to cart button",
            "add_to_cart_button_for_red_widget",
        )
        is True
    )

    assert (
        PlaceholderResolver.text_matches_description(
            "Order confirmation message",
            "order_confirmation_message_visible",
        )
        is True
    )


def test_find_best_element_rejects_low_confidence_text_overlap() -> None:
    """When text overlap gives marginal score, confidence threshold should reject it."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.5)  # High threshold
    elements = [
        # Weak match — only one shared word "page"
        {
            "selector": "#footer",
            "text": "Footer navigation page",
            "role": "div",
            "id": "footer",
            "classes": "",
        },
    ]

    result = best_ranked_element(resolver, "ASSERT", "checkout confirmation message visible", elements)
    # Should be rejected due to low confidence (no meaningful overlap)
    assert result is None, f"Low-confidence match should be rejected, got {result}"


def test_rank_candidates_text_bonus_with_long_description() -> None:
    """Text overlap bonus should work correctly with longer descriptions."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        # Element text contains multiple keywords from long description
        {
            "selector": "#order_summary",
            "text": "Your order summary: 2 items totaling $49.99",
            "role": "div",
            "id": "order_summary",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates(
        "ASSERT",
        "order summary showing items and total amount visible on page",
        elements,
    )
    assert len(ranked) >= 1, f"Expected at least one candidate in {ranked}"
    top_selector = ranked[0][1]["selector"]
    assert top_selector == "#order_summary"


def test_rank_candidates_text_bonus_prefers_specific_product() -> None:
    """Text overlap should help differentiate between similar product actions."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        # Has "backpack" keyword — matches description better
        {
            "selector": "#add-to-cart-backpack",
            "text": "Add to cart - Classic Backpack",
            "role": "button",
            "id": "add-to-cart-backpack",
            "classes": "",
        },
        # No "backpack" keyword — less overlap with description
        {
            "selector": "#add-to-cart-fleece",
            "text": "Add to cart - Winter Fleece Jacket",
            "role": "button",
            "id": "add-to-cart-fleece",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "add to cart button for classic backpack", elements)
    assert len(ranked) >= 2, f"Expected at least 2 candidates in {ranked}"
    # Backpack element should rank higher due to text overlap bonus
    top_selector = ranked[0][1]["selector"]
    assert top_selector == "#add-to-cart-backpack", f"Product-matching element should rank first, got {top_selector}"


def test_find_best_element_assert_text_bonus_beats_generic() -> None:
    """For ASSERT actions, text overlap bonus should beat generic structural matches."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        # Generic element — good structural match but poor text overlap
        {
            "selector": "#modal_close",
            "text": "X",
            "role": "button",
            "id": "modal_close",
            "classes": "",
        },
        # Specific element — strong text overlap with description
        {
            "selector": "#success_notification",
            "text": "Your changes have been saved successfully",
            "role": "div",
            "id": "success_notification",
            "classes": "",
        },
    ]

    result = best_ranked_element(resolver, "ASSERT", "changes saved successfully notification visible", elements)
    assert result is not None, f"Expected a match, got {result}"
    assert result["selector"] == "#success_notification", (
        "Text-overlap element should win over generic structural match"
    )


def test_rank_candidates_text_bonus_does_not_break_existing_product_id_logic() -> None:
    """Product-ID matching logic should still work alongside text overlap bonus."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        # Exact product ID match — gets +20 product bonus
        {
            "selector": "#add-to-cart-sauce-labs-backpack",
            "text": "Add to cart",
            "role": "button",
            "id": "add-to-cart-sauce-labs-backpack",
            "classes": "",
        },
        # Wrong product — no ID match, minimal text overlap bonus
        {
            "selector": "#add-to-cart-sauce-labs-fleece-jacket",
            "text": "Add to cart",
            "role": "button",
            "id": "add-to-cart-sauce-labs-fleece-jacket",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "add to cart button for sauce labs backpack", elements)
    assert len(ranked) >= 2, f"Expected at least 2 candidates in {ranked}"
    # Product-ID match should still win (has both +20 product bonus and any text overlap)
    top_selector = ranked[0][1]["selector"]
    assert "backpack" in top_selector, f"Product-ID match should rank first, got {top_selector}"


# --------------------------------------------------------------------------
# Session 4 (May 2026) — Visibility Capture integration tests
# --------------------------------------------------------------------------


def test_rank_candidates_skips_invisible_elements_for_click() -> None:
    """Invisible elements (is_visible=False) must be excluded from CLICK candidates."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        {
            "selector": "#visible_submit",
            "text": "Submit Order",
            "role": "button",
            "id": "visible_submit",
            "classes": "",
            "is_visible": True,
        },
        {
            "selector": "#hidden_confirm",
            "text": "Confirm Purchase",
            "role": "button",
            "id": "hidden_confirm",
            "classes": "",
            "is_visible": False,  # Simulates element hidden behind overlay
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "submit order button", elements)
    selectors = [el["selector"] for _, el in ranked]
    assert "#visible_submit" in selectors, f"Visible element should be ranked: {selectors}"
    assert "#hidden_confirm" not in selectors, f"Invisible element must NOT be ranked: {selectors}"


def test_rank_candidates_penalizes_invisible_elements_for_assert() -> None:
    """Invisible elements get a penalty for ASSERT but are not skipped."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        {
            "selector": "#success_msg",
            "text": "Order confirmed!",
            "role": "div",
            "id": "success_msg",
            "classes": "",
            "is_visible": True,
        },
        {
            "selector": "#old_order_history",
            "text": "Previous order history",
            "role": "div",
            "id": "old_order_history",
            "classes": "",
            "is_visible": False,  # Simulates element hidden by modal
        },
    ]

    ranked = resolver.rank_candidates("ASSERT", "order confirmation message visible", elements)
    assert len(ranked) >= 1, f"Expected at least one candidate: {ranked}"
    top_selector = ranked[0][1]["selector"]
    assert top_selector == "#success_msg", f"Visible element should rank first: {top_selector}"


def test_find_best_element_prefers_visible_over_invisible() -> None:
    """find_best_element should return visible candidate when both could match."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        {
            "selector": "#continue_shopping",
            "text": "Continue Shopping",
            "role": "button",
            "id": "continue_shopping",
            "classes": "",
            "is_visible": True,
        },
        {
            "selector": "#newsletter_subscribe",
            "text": "Subscribe to Newsletter",
            "role": "input",
            "id": "subscribe",
            "classes": "form-control",
            "is_visible": False,  # Hidden newsletter input
        },
    ]

    result = best_ranked_element(resolver, "CLICK", "continue shopping button", elements)
    assert result is not None, f"Expected a match: {result}"
    assert result["selector"] == "#continue_shopping", f"Should prefer visible element: {result['selector']}"


def test_rank_candidates_invisible_with_no_text_heavily_penalized() -> None:
    """Invisible elements with no text should be heavily penalized for CLICK."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        {
            "selector": "#continue_btn",
            "text": "Continue Shopping",
            "role": "button",
            "id": "continue_btn",
            "classes": "",
            "is_visible": True,
        },
        {
            "selector": "#empty_hidden_div",
            "text": "",
            "role": "div",
            "id": "empty_hidden_div",
            "classes": "",
            "is_visible": False,  # Hidden + empty text = double penalty
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "continue shopping button", elements)
    selectors = [el["selector"] for _, el in ranked]
    assert "#continue_btn" in selectors, f"Visible element should be ranked: {selectors}"
    # Hidden empty element should NOT appear (skipped due to is_visible=False for non-ASSERT)


def test_find_best_element_invisible_assert_returns_none_if_no_confidence() -> None:
    """When only invisible elements match ASSERT and confidence threshold rejects them, return None."""
    resolver = PlaceholderResolver(match_threshold=1, min_confidence=0.3)
    elements = [
        {
            "selector": "#hidden_success",
            "text": "Order placed!",
            "role": "div",
            "id": "hidden_success",
            "classes": "",
            "is_visible": False,  # Only candidate is invisible
        },
    ]

    result = best_ranked_element(resolver, "ASSERT", "order placed success message visible", elements)
    # Hidden element gets -40 penalty, reducing confidence below threshold → None
    assert result is None or result.get("selector") == "#hidden_success"  # May still return if only candidate


# --------------------------------------------------------------------------
# URL validation tests (July 2026) — validate URLs exist in scraped data
# --------------------------------------------------------------------------


def test_resolve_url_validates_against_scraped_data() -> None:
    """Test that resolve_url validates URLs exist in scraped data before returning them.

    This prevents the LLM from generating non-existent URLs that cause 404 errors,
    and (t-0877) it no longer substitutes an arbitrary scraped page when the
    description matches nothing.
    """
    resolver = PlaceholderResolver()

    # Simulate scraped data - only the home page was scraped
    scraped_data = {
        "https://automationexercise.com/": [
            {"selector": "a[href='/']", "text": "Home", "role": "link"},
        ],
        "https://automationexercise.com/products": [
            {"selector": "a[href='/products']", "text": "Products", "role": "link"},
        ],
    }

    # URL that exists in scraped data should be returned
    result = resolver.resolve_url("https://automationexercise.com/", scraped_data)
    assert result == "https://automationexercise.com/", f"Expected home URL, got {result}"

    # URL that does NOT exist in scraped data should NOT be returned directly
    # This is the bug fix - the LLM generated a URL that doesn't exist
    result = resolver.resolve_url(
        "https://automationexercise.com/category_product.php?id=3",
        scraped_data,
    )
    # Should NOT return the non-existent URL
    assert result != "https://automationexercise.com/category_product.php?id=3", (
        f"URL validation failed: returned non-existent URL {result}"
    )
    # t-0877: and no arbitrary page either. This used to assert a fallback to
    # "a known URL"; that fallback was "whichever page is first", a guess at a
    # destination nobody named. The answer is now an honest None.
    assert result is None, f"Expected an honest unresolved, got {result}"


def test_resolve_url_validates_relative_urls_against_scraped_data() -> None:
    """Test that relative URLs are also validated against scraped data."""
    resolver = PlaceholderResolver()

    scraped_data = {
        "https://example.com/": [
            {"selector": "#home", "text": "Home", "role": "link"},
        ],
    }

    # Relative URL that doesn't exist should not be returned
    result = resolver.resolve_url("/nonexistent-page", scraped_data)
    assert result != "/nonexistent-page", f"URL validation failed: returned non-existent URL {result}"
    # t-0877: no fallback to "whichever page is first" - an honest None.
    assert result is None, f"Expected an honest unresolved, got {result}"


# --------------------------------------------------------------------------
# Root-path guard (2026-08-03) — a bare root URL must not substring-match
# multi-word descriptions when the base URL comes first in known_urls.
# --------------------------------------------------------------------------


def _three_page_fixture() -> tuple[PlaceholderResolver, dict[str, list[dict[str, str]]], list[str]]:
    """Return resolver + scraped pages with the base URL FIRST in known_urls (production order)."""
    resolver = PlaceholderResolver()
    pages: dict[str, list[dict[str, str]]] = {
        "https://automationexercise.com": [
            {
                "selector": "body",
                "text": "Home with cart link",
                "tag": "body",
                "href": "https://automationexercise.com/view_cart",
            },
        ],
        "https://automationexercise.com/products": [
            {"selector": "body", "text": "Products list", "tag": "body"},
        ],
        "https://automationexercise.com/view_cart": [
            {"selector": "body", "text": "Cart contents", "tag": "body"},
        ],
    }
    return resolver, pages, list(pages.keys())


def test_resolve_url_cart_page_loaded_does_not_hit_root() -> None:
    """Multi-word page-state descriptions must not resolve to the base URL.

    Regression: ``(parsed.path or "/").replace("/", " ")`` normalizes the
    root path to a single space, which substring-matches ANY multi-word
    description — so "cart page loaded" resolved to the home URL when the
    base URL came first in known_urls.
    """
    resolver, pages, known = _three_page_fixture()
    for desc, expected in (
        ("cart page loaded", "https://automationexercise.com/view_cart"),
        ("cart page title", "https://automationexercise.com/view_cart"),
        ("go to cart page", "https://automationexercise.com/view_cart"),
        ("products page title", "https://automationexercise.com/products"),
    ):
        result = resolver.resolve_url(desc, pages, known_urls=known)
        assert result == expected, f"{desc!r} → {result}, expected {expected}"


def test_resolve_url_home_keywords_still_hit_root() -> None:
    """Home/start/landing descriptions still resolve to the root URL."""
    resolver, pages, known = _three_page_fixture()
    for desc in ("home", "home page loaded", "home page title", "landing page"):
        result = resolver.resolve_url(desc, pages, known_urls=known)
        assert result == "https://automationexercise.com", f"{desc!r} → {result}, expected home"


def test_resolve_url_single_word_keywords_unchanged() -> None:
    """Existing single-word GOTO keyword behavior is preserved."""
    resolver, pages, known = _three_page_fixture()
    assert resolver.resolve_url("cart", pages, known_urls=known) == "https://automationexercise.com/view_cart"
    assert resolver.resolve_url("products", pages, known_urls=known) == "https://automationexercise.com/products"


# ---------------------------------------------------------------------------
# Page arrival: the page's own URL beats another page's body text
# ---------------------------------------------------------------------------


def _banking_pages() -> dict[str, list[dict[str, str]]]:
    """The banking mock's shape: dashboard and sign-in both name the destination."""
    return {
        "http://localhost:8781/index.html": [
            {
                "selector": "p",
                "text": "Sign in to view your accounts, transfer money, and pay bills.",
                "tag": "p",
                "role": "",
            }
        ],
        "http://localhost:8781/dashboard.html": [
            {
                "selector": "#pay-bill-link",
                "text": "Bill Payments",
                "tag": "a",
                "role": "link",
            },
            {
                "selector": 'a[href="/transfer.html"]',
                "text": "Transfer",
                "tag": "a",
                "role": "link",
            },
        ],
        "http://localhost:8781/transfer.html": [
            {"selector": "#amount", "text": "amount", "tag": "input", "role": "textbox"}
        ],
        "http://localhost:8781/payments.html": [
            {"selector": "#payment-amount", "text": "payment amount", "tag": "input", "role": "textbox"}
        ],
        "http://localhost:8781/transfer_success.html?amount=100": [
            {"selector": "#transfer-success-title", "text": "Transfer successful", "tag": "h2", "role": ""}
        ],
        "http://localhost:8781/payment_success.html?amount=50": [
            {"selector": "#payment-success-title", "text": "Payment successful", "tag": "h2", "role": ""}
        ],
    }


def test_page_arrival_prefers_its_own_path_over_other_page_text() -> None:
    """t-0961: 'transfer page loaded' is transfer.html, not index.html.

    The sign-in page says 'transfer money' and the dashboard links to
    'Transfer'/'Bill Payments'. Body text on another page must not beat the
    destination page's own path.
    """
    resolver = PlaceholderResolver(match_threshold=1)
    pages = _banking_pages()

    assert (
        resolver.resolve_url("transfer page loaded", pages, known_urls=list(pages.keys()))
        == "http://localhost:8781/transfer.html"
    )
    assert (
        resolver.resolve_url("bill payments page loaded", pages, known_urls=list(pages.keys()))
        == "http://localhost:8781/payments.html"
    )


def test_goto_prefers_its_own_path_over_other_page_text() -> None:
    """The GOTO forms used by eval-008 name the landed page, not the dashboard."""
    resolver = PlaceholderResolver(match_threshold=1)
    pages = _banking_pages()

    assert (
        resolver.resolve_url("go to the transfer page", pages, known_urls=list(pages.keys()))
        == "http://localhost:8781/transfer.html"
    )
    assert (
        resolver.resolve_url("navigate to bill payments", pages, known_urls=list(pages.keys()))
        == "http://localhost:8781/payments.html"
    )


def test_landing_that_really_is_the_index_page_still_resolves_index() -> None:
    """The fix must not push every page arrival off the entry page."""
    resolver = PlaceholderResolver(match_threshold=1)
    pages = _banking_pages()

    assert (
        resolver.resolve_url("home page loaded", pages, known_urls=list(pages.keys()))
        == "http://localhost:8781/index.html"
    )
    assert (
        resolver.resolve_url("bank sign-in page loaded", pages, known_urls=list(pages.keys()))
        == "http://localhost:8781/index.html"
    )


def test_success_pages_are_not_confused_with_their_parent_page() -> None:
    """A success arrival must name the success page, not transfer/payments."""
    resolver = PlaceholderResolver(match_threshold=1)
    pages = _banking_pages()

    assert (
        resolver.resolve_url("transfer success message", pages, known_urls=list(pages.keys()))
        == "http://localhost:8781/transfer_success.html?amount=100"
    )
    assert (
        resolver.resolve_url("payment success message", pages, known_urls=list(pages.keys()))
        == "http://localhost:8781/payment_success.html?amount=50"
    )


# ---------------------------------------------------------------------------
# t-0998 — a CLICK target is the element that names itself
# ---------------------------------------------------------------------------


def _insurance_product_page() -> list[dict]:
    """The lv_insurance product section: wrapper, card, and the card's heading.

    Shapes copied from the real scrape (see tests). The wrapper's haystack is
    the merged text of both product cards, so it ties the card for a
    "Car Insurance" click; the ``h4`` label inside the card ties too.
    """
    return [
        {
            "selector": "#page-product",
            "text": (
                "Select a Product Car Insurance Comprehensive cover for your vehicle "
                "Home Insurance Buildings contents cover Please select a product Back Next"
            ),
            "tag": "div",
            "role": "heading",
            "id": "page-product",
            "classes": "page",
            "is_visible": True,
        },
        {
            "selector": "#productCar",
            "text": "Car Insurance Comprehensive cover for your vehicle",
            "tag": "div",
            "role": "heading",
            "id": "productCar",
            "classes": "card-option",
            "is_visible": True,
        },
        {
            "selector": "h4",
            "text": "Car Insurance",
            "tag": "h4",
            "role": "statictext",
            "id": "",
            "classes": "",
            "is_visible": True,
        },
    ]


def test_click_tie_prefers_the_named_card_over_its_page_section_wrapper() -> None:
    """eval-005 crit 1: a section wrapper must not beat the card it contains.

    The wrapper and the card score the same (both are div containers that match
    on merged text). Before t-0998 the tie was broken by text length, so the
    wrapper - whose text is the whole section - won, and the emitted test
    clicked the section instead of the Car Insurance card.
    """
    resolver = PlaceholderResolver(match_threshold=1)

    ranked = resolver.rank_candidates("CLICK", "Car Insurance", _insurance_product_page())

    assert ranked[0][1]["selector"] == "#productCar"
    # The wrapper is still a candidate, just no longer the winner.
    assert "#page-product" in [element["selector"] for _score, element in ranked]


# ---------------------------------------------------------------------------
# t-1004 — text evidence outranks every bonus
# ---------------------------------------------------------------------------


def _payment_options_page() -> list[dict]:
    """The lv_insurance extras state, shapes copied from the real scrape.

    The payment options sit in a section that is display:none until the user is
    on it, so the two visible controls on the page are "Back" and "Next". Both
    share no word with "Pay in Full" but collect +10 role and +15 commit on the
    submit verb "pay" (31 each). The hidden option is an exact text match that
    pays -30 hidden and -40 container and lands at 30.
    """
    return [
        {
            "selector": "#paymentFull",
            "text": "Pay in Full One card payment today",
            "tag": "div",
            "role": "div",
            "id": "paymentFull",
            "classes": "card-option",
            "is_visible": False,
        },
        {
            "selector": "#extrasBack",
            "text": "\u2190 Back",
            "tag": "button",
            "role": "button",
            "id": "extrasBack",
            "classes": "btn-secondary",
            "is_visible": True,
        },
        {
            "selector": "#extrasNext",
            "text": "Next \u2192",
            "tag": "button",
            "role": "button",
            "id": "extrasNext",
            "classes": "",
            "is_visible": True,
        },
    ]


def test_exact_text_match_beats_visible_controls_with_no_shared_word() -> None:
    """eval-005: the hidden "Pay in Full" option must beat "Back" and "Next".

    Before t-1004 the ranking was #extrasBack 31, #extrasNext 31, #paymentFull
    30: a role and commit bonus with zero word overlap outranked the element
    whose own text is the step.
    """
    resolver = PlaceholderResolver()

    ranked = resolver.rank_candidates("CLICK", "Pay in Full", _payment_options_page())

    assert ranked[0][1]["selector"] == "#paymentFull"
    # The bonuses still count; they just cannot outrank text evidence.
    assert {"#extrasBack", "#extrasNext"} <= {element["selector"] for _score, element in ranked}


def test_a_page_with_no_text_match_still_returns_its_local_candidate() -> None:
    """The tier orders ONE page's list; it never reaches across pages.

    The same step on a page that does not hold the option (the pool the picker
    is scoped to) must still resolve to what that page has, not to nothing and
    not to another page's element.
    """
    resolver = PlaceholderResolver()
    this_page = [element for element in _payment_options_page() if element["selector"] != "#paymentFull"]

    ranked = resolver.rank_candidates("CLICK", "Pay in Full", this_page)

    assert ranked, "a zero-overlap page must still offer its best local candidate"
    assert ranked[0][1]["selector"] in {"#extrasBack", "#extrasNext"}


def test_the_text_tier_never_resurrects_a_dropped_candidate() -> None:
    """A hidden element with no literal text match stays dropped by the pool gate."""
    resolver = PlaceholderResolver()
    page = [
        {
            "selector": "#extrasBack",
            "text": "\u2190 Back",
            "tag": "button",
            "role": "button",
            "id": "extrasBack",
            "classes": "btn-secondary",
            "is_visible": True,
        },
        {
            # Shares "payment" with the step, so the text tier would rank it -
            # but the hidden gate drops it first and the tier must not bring it
            # back.
            "selector": "#paymentDetails",
            "text": "Payment details",
            "tag": "div",
            "role": "div",
            "id": "paymentDetails",
            "classes": "",
            "is_visible": False,
        },
    ]

    ranked = resolver.rank_candidates("CLICK", "Pay in Full payment option", page)

    assert "#paymentDetails" not in [element["selector"] for _score, element in ranked]
    assert ranked and ranked[0][1]["selector"] == "#extrasBack"


def test_a_word_form_is_not_dom_nesting(monkeypatch: pytest.MonkeyPatch) -> None:
    """t-1011: "Pay Bills" does not contain the submit control "Pay Bill".

    The CLICK tie-break demotes a candidate whose text contains another tied
    candidate's text, because a wrapper's text is the merged text of its
    children. A word form is not that: the banking nav link "Pay Bills" holds
    the STRING "Pay Bill" but not the button, and reading it as nesting
    silently replaced the pre-t-0572 tie that tests/test_submit_preference.py
    pins. With the commit bonus removed the two still tie at 100 and the nav
    link still wins on the longest-text tie-break.
    """
    from src.placeholder_scorers import PlaceholderScorer

    monkeypatch.setattr(PlaceholderScorer, "_commit_control_bonus", staticmethod(lambda *a, **k: 0))
    nav = {
        "selector": 'a[href="/payments.html"]',
        "text": "Pay Bills",
        "role": "a",
        "tag": "a",
        "href": "/payments.html",
        "is_visible": True,
    }
    submit = {
        "selector": "#pay-bill",
        "text": "Pay Bill",
        "role": "button",
        "tag": "button",
        "id": "pay-bill",
        "type": "submit",
        "is_visible": True,
    }

    assert PlaceholderResolver._is_embedded_text("pay bill", "pay bills") is False
    assert PlaceholderResolver._is_embedded_text("pay bill", "pay bill now") is True

    ranked = PlaceholderResolver().rank_candidates("CLICK", "Pay", [nav, submit])

    assert [score for score, _element in ranked] == [100, 100]
    assert ranked[0][1]["selector"] == 'a[href="/payments.html"]'
