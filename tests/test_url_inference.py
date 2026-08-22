"""Unit tests for src/url_inference.py — evidence-only URL transitions.

AI-052 Session 4: the keyword branches (login/checkout/continue/finish/
transfer/pay description keywords → discovered-URL lookup) were DELETED.
A URL transition is derived only from the clicked element's own ``href`` —
a fact. Description-to-URL fabrication ("description says login, so probably
/dashboard.html") is banned; trail-driven callers never consult this module.

These tests pin the no-guessing contract: a keyword-rich CLICK without an
href returns None, NOT a discovered URL.
"""

from __future__ import annotations

from src.url_inference import infer_next_page_url


def _scrape(urls: list[str]) -> dict[str, list[dict[str, str]]]:
    """Build a minimal scraped-data map for the given URLs."""
    return {url: [{"selector": "body"}] for url in urls}


# ── The no-guessing contract ─────────────────────────────────────────────


def test_login_click_without_href_returns_none() -> None:
    """A 'login' click with NO href must return None — even when a dashboard
    page sits in scraped_data begging to be guessed."""
    scraped = _scrape(
        [
            "http://localhost:8781/index.html",
            "http://localhost:8781/dashboard.html",
        ]
    )
    url = infer_next_page_url(
        action="CLICK",
        description="sign in button",
        matched_element={"selector": "#login-button", "id": "login-button", "text": "Sign In"},
        scraped_data=scraped,
        current_url="http://localhost:8781/index.html",
    )
    assert url is None


def test_checkout_click_without_href_returns_none() -> None:
    scraped = _scrape(["https://x/cart.html", "https://x/checkout-step-one.html"])
    url = infer_next_page_url(
        action="CLICK",
        description="checkout button",
        matched_element={"selector": "#checkout", "id": "checkout"},
        scraped_data=scraped,
        current_url="https://x/cart.html",
    )
    assert url is None


def test_transfer_submit_without_href_returns_none() -> None:
    """Banking mock shape: href-less submit buttons no longer fabricate a
    success-page transition — the trail (or nothing) provides it."""
    scraped = _scrape(
        [
            "http://localhost:8781/transfer.html",
            "http://localhost:8781/transfer_success.html?amount=100.00",
        ]
    )
    url = infer_next_page_url(
        action="CLICK",
        description="Submit Transfer",
        matched_element={"selector": "#transfer-submit", "id": "transfer-submit"},
        scraped_data=scraped,
        current_url="http://localhost:8781/transfer.html",
    )
    assert url is None


def test_navigation_wording_without_href_returns_none() -> None:
    """'cart link'-style descriptions don't trigger a scraped-URL lookup
    without an href on the element itself."""
    url = infer_next_page_url(
        action="CLICK",
        description="go to cart icon",
        matched_element={"selector": ".shopping_cart_link", "class": "shopping_cart_link"},
        scraped_data=_scrape(["https://www.saucedemo.com/cart.html"]),
        current_url="https://www.saucedemo.com/inventory.html",
    )
    assert url is None


# ── Evidence that IS honoured ────────────────────────────────────────────


def test_click_with_absolute_href_uses_href() -> None:
    url = infer_next_page_url(
        action="CLICK",
        description="Transfer Money link",
        matched_element={
            "selector": "#transfer-link",
            "href": "http://localhost:8781/transfer.html",
        },
        scraped_data=_scrape(["http://localhost:8781/dashboard.html"]),
        current_url="http://localhost:8781/dashboard.html",
    )
    assert url == "http://localhost:8781/transfer.html"


def test_click_with_relative_href_resolves_against_current_page() -> None:
    url = infer_next_page_url(
        action="CLICK",
        description="view product",
        matched_element={"selector": "a[href='/product_details/2']", "href": "/product_details/2"},
        scraped_data=_scrape(["https://automationexercise.com/product_details/2"]),
        current_url="https://automationexercise.com/products",
    )
    assert url == "https://automationexercise.com/product_details/2"


def test_fragment_and_javascript_hrefs_return_none() -> None:
    """SPA-style anchors (#, javascript:) carry no navigation evidence."""
    for href in ("#", "javascript:void(0)", "mailto:x@y.z", "", "   "):
        url = infer_next_page_url(
            action="CLICK",
            description="title link",
            matched_element={"selector": "#t", "href": href},
            scraped_data={},
            current_url="https://www.saucedemo.com/inventory.html",
        )
        assert url is None, f"href={href!r} should not transition"


def test_fill_never_advances() -> None:
    """A FILL step must never advance the page (only CLICK can)."""
    url = infer_next_page_url(
        action="FILL",
        description="Payee",
        matched_element={"selector": "#payee", "href": "/somewhere"},
        scraped_data=_scrape(["http://localhost:8781/payments.html"]),
        current_url="http://localhost:8781/payments.html",
    )
    assert url is None
