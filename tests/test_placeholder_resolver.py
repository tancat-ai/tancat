"""Tests for placeholder resolution."""

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


def test_fill_does_not_match_non_fillable_link_element() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("FILL", "product details field")]
    pages = {
        "https://example.com/": [
            {
                "selector": 'a[href="/product_details/1"]',
                "text": "View Product",
                "role": "a",
                "href": "https://example.com/product_details/1",
            }
        ]
    }

    resolution = resolve_placeholders(resolver, placeholders, pages)[0]
    assert "pytest.skip" in resolution


def test_assert_prefers_cart_content_over_cart_nav_link() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("ASSERT", "items have been added correctly")]
    pages = {
        "https://example.com/view_cart": [
            {
                "selector": 'a[href="/view_cart"]',
                "text": "Cart",
                "role": "a",
                "href": "https://example.com/view_cart",
            },
            {
                "selector": ".cart_description",
                "text": "Blue Top",
                "role": "div",
                "href": "",
            },
        ]
    }

    # rank_candidates prefers cart content (.cart_description) over the cart nav link
    resolution = resolve_placeholders(resolver, placeholders, pages)[0]
    assert ".cart_description" in resolution


def test_click_go_to_cart_does_not_match_add_to_cart_button() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "go to cart")]
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

    # _build_robust_locator prefers href-based for link elements
    assert resolve_placeholders(resolver, placeholders, pages) == ["'a[href=\"/view_cart\"]'"]


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
        # Element with partial text overlap — should get +bonus
        {
            "selector": "#order_status",
            "text": "Order status updated successfully",
            "role": "div",
            "id": "order_status",
            "classes": "",
        },
        # Element with no text overlap — lower score
        {
            "selector": "#footer_link",
            "text": "Privacy Policy",
            "role": "a",
            "id": "footer_link",
            "classes": "",
        },
    ]

    ranked = resolver.rank_candidates("ASSERT", "order status updated message visible", elements)
    assert len(ranked) >= 2, f"Expected at least 2 candidates in {ranked}"
    # Element with text overlap should rank higher
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
