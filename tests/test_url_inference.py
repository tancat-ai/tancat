"""Unit tests for src/url_inference.py — URL transition inference.

Extracted from placeholder_orchestrator.py; site-agnostic post-action
page-context tracking. The banking mock (eval-007) exposed that the login
transition vocabulary was ecommerce-only (inventory/products) — a banking
site lands on dashboard/accounts after auth, so the journey never advanced
past the login page and every downstream placeholder stayed scoped there.
"""

from __future__ import annotations

from src.url_inference import infer_next_page_url


def _scrape(urls: list[str]) -> dict[str, list[dict[str, str]]]:
    """Build a minimal scraped-data map for the given URLs."""
    return {url: [{"selector": "body"}] for url in urls}


def test_login_click_advances_to_ecommerce_landing() -> None:
    """Saucedemo-style: post-login page is /inventory.html — the original
    ecommerce-only vocabulary must keep working."""
    scraped = _scrape(
        [
            "https://www.saucedemo.com",
            "https://www.saucedemo.com/inventory.html",
        ]
    )
    url = infer_next_page_url(
        action="CLICK",
        description="login button",
        matched_element={"selector": "#login-button", "id": "login-button", "text": "Login"},
        scraped_data=scraped,
        current_url="https://www.saucedemo.com",
    )
    assert url == "https://www.saucedemo.com/inventory.html"


def test_login_click_advances_to_banking_dashboard() -> None:
    """Banking mock (eval-007): post-login page is /dashboard.html. The login
    transition must not be hardcoded to ecommerce vocabulary — otherwise the
    journey stays on the login page and transfer/payment placeholders never
    resolve against their pages."""
    scraped = _scrape(
        [
            "http://localhost:8781/index.html",
            "http://localhost:8781/dashboard.html",
            "http://localhost:8781/transfer.html",
            "http://localhost:8781/payments.html",
        ]
    )
    url = infer_next_page_url(
        action="CLICK",
        description="sign in button",
        matched_element={"selector": "#login-button", "id": "login-button", "text": "Sign In"},
        scraped_data=scraped,
        current_url="http://localhost:8781/index.html",
    )
    assert url == "http://localhost:8781/dashboard.html"


def test_login_click_falls_back_to_accounts_vocabulary() -> None:
    """Banking sites that name their landing page 'accounts' also advance."""
    scraped = _scrape(
        [
            "http://localhost:8781/signin.html",
            "http://localhost:8781/accounts.html",
        ]
    )
    url = infer_next_page_url(
        action="CLICK",
        description="login",
        matched_element={"selector": "#login", "id": "login", "text": "Log in"},
        scraped_data=scraped,
        current_url="http://localhost:8781/signin.html",
    )
    assert url == "http://localhost:8781/accounts.html"


def test_login_click_no_landing_page_returns_none() -> None:
    """No post-login page scraped → no transition (caller keeps current)."""
    scraped = _scrape(["http://localhost:8781/index.html"])
    url = infer_next_page_url(
        action="CLICK",
        description="sign in button",
        matched_element={"selector": "#login-button", "id": "login-button", "text": "Sign In"},
        scraped_data=scraped,
        current_url="http://localhost:8781/index.html",
    )
    assert url is None


def test_click_with_href_uses_href() -> None:
    """A plain link click with an href transitions via the href."""
    url = infer_next_page_url(
        action="CLICK",
        description="Transfer Money link",
        matched_element={"selector": "#transfer-link", "href": "/transfer.html"},
        scraped_data=_scrape(["http://localhost:8781/dashboard.html"]),
        current_url="http://localhost:8781/dashboard.html",
    )
    assert url == "http://localhost:8781/transfer.html"


def test_submit_transfer_advances_to_transfer_success() -> None:
    """Banking mock: clicking the (href-less) submit button advances to the
    success page, so the success-message ASSERT resolves there instead of
    against the form page's submit button / error paragraph."""
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
    assert url == "http://localhost:8781/transfer_success.html?amount=100.00"


def test_submit_payment_advances_to_payment_success() -> None:
    """Same for the bill-pay submit button."""
    scraped = _scrape(
        [
            "http://localhost:8781/payments.html",
            "http://localhost:8781/payment_success.html?amount=50.00",
        ]
    )
    url = infer_next_page_url(
        action="CLICK",
        description="Submit Payment",
        matched_element={"selector": "#pay-bill", "id": "pay-bill"},
        scraped_data=scraped,
        current_url="http://localhost:8781/payments.html",
    )
    assert url == "http://localhost:8781/payment_success.html?amount=50.00"


def test_payee_fill_does_not_advance() -> None:
    """A FILL step must never advance the page (only CLICK does)."""
    url = infer_next_page_url(
        action="FILL",
        description="Payee",
        matched_element={"selector": "#payee", "id": "payee"},
        scraped_data=_scrape(["http://localhost:8781/payments.html"]),
        current_url="http://localhost:8781/payments.html",
    )
    assert url is None
