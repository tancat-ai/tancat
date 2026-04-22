"""Tests for placeholder resolution."""

from src.placeholder_resolver import PlaceholderResolver


def test_resolve_all_returns_real_selector_for_matching_placeholder() -> None:
    resolver = PlaceholderResolver(match_threshold=1)
    placeholders = [("CLICK", "login button")]
    pages = {"https://example.com": [{"selector": "#login", "text": "Login Button", "role": "button"}]}

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

    assert resolver.resolve_all(placeholders, pages) == ["'.cart_description'"]


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

    assert resolver.resolve_all(placeholders, pages) == ["'[data-product-id=\"11\"]'"]


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

    assert resolver.resolve_all(placeholders, pages) == ["'a[href=\"/checkout\"]'"]
