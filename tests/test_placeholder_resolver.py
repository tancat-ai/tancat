"""Tests for placeholder resolution."""

from src.placeholder_resolver import PlaceholderResolver


def test_resolve_all_returns_real_selector_for_matching_placeholder() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "login button")]
    pages = {"https://example.com": [{"selector": "#login", "text": "Login Button", "role": "button"}]}

    # _build_robust_locator prefers ID-based (#login) over text-based locators
    assert resolver.resolve_all(placeholders, pages) == ["'#login'"]


def test_resolve_all_returns_pytest_skip_when_no_match_found() -> None:
    resolver = PlaceholderResolver(match_threshold=2)
    placeholders = [("CLICK", "checkout button")]
    pages = {"https://example.com": [{"selector": "#login", "text": "Login", "role": "button"}]}

    resolution = resolver.resolve_all(placeholders, pages)[0]
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
    assert resolver.resolve_all(placeholders, pages) == ["'a[href=\"/view_cart\"]'"]


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

    assert resolver.resolve_all(placeholders, pages) == [
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

    resolution = resolver.resolve_all(placeholders, pages)[0]
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

    # Text validation: "Blue Top" doesn't match "items have been added correctly"
    # so the resolver correctly skips (B1 text-content validation)
    resolution = resolver.resolve_all(placeholders, pages)[0]
    assert "pytest.skip" in resolution


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
    assert resolver.resolve_all(placeholders, pages) == ["'a[href=\"/view_cart\"]'"]


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
    assert resolver.resolve_all(placeholders, pages) == ["'.add-to-cart.btn[data-product-id=\"11\"]'"]


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
    assert resolver.resolve_all(placeholders, pages) == ["'a[href=\"/checkout\"]'"]


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

    resolution = resolver.resolve_all(placeholders, pages)[0]
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

    resolution = resolver.resolve_all(placeholders, pages)[0]
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

    result = resolver.resolve_all(placeholders, pages)
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

    result = resolver.resolve_all(placeholders, pages)
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

    result = resolver.resolve_all(placeholders, pages)
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

    result = resolver.resolve_all(placeholders, pages)
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

    result = resolver.find_best_element("FILL", "some field", elements)
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

    result = resolver.find_best_element("ASSERT", "product added confirmation message", elements)
    assert result is not None
    assert result["selector"] == "h2.product-title"
