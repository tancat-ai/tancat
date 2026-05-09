"""Verify that _find_best_element_for_current_page returns the global best match across all pages.

Regression test: the old code returned the first match found per-page, which could
return a low-quality match from an early page when a much better match existed on
a later page (e.g., finding a cart page element for "username input" instead of
the login page element).
"""

import asyncio

from src.placeholder_orchestrator import PlaceholderOrchestrator


def make_element(selector: str, text: str = "", role: str = "", id: str = "", name: str = "") -> dict[str, str]:
    """Create a minimal scraped element dict."""
    return {
        "selector": selector,
        "text": text,
        "role": role,
        "id": id or selector.lstrip("#."),
        "name": name,
        "href": "",
        "title": "",
        "aria_label": "",
        "data_test": "",
        "classes": "",
        "value": "",
        "placeholder": "",
        "is_icon": "false",
        "parent_text": "",
        "visual_description": f"role({role}) [{id or selector}]",
        "is_visible": "true",
    }


def test_global_best_across_pages() -> None:
    """When login page has #user-name and cart page has unrelated elements,
    resolving 'username input' should return #user-name from the login page,
    NOT a weak match from the cart page."""
    cart_elements = [
        make_element("#continue-shopping", text="Continue Shopping", role="button"),
        make_element("#checkout", text="Checkout", role="button"),
        make_element("#item_4_title_link", text="Sauce Labs Backpack", role="link"),
    ]
    login_elements = [
        make_element("#user-name", role="text", name="user-name"),
        make_element("#password", role="password", name="password"),
        make_element("#login-button", role="submit", name="login-button"),
    ]

    # Cart page FIRST in dict order (simulates the bug scenario)
    pages_data = {
        "https://www.saucedemo.com/cart.html": cart_elements,
        "https://www.saucedemo.com": login_elements,
    }

    orchestrator = PlaceholderOrchestrator()
    result = asyncio.run(
        orchestrator._find_best_element_for_current_page(
            action="FILL",
            description="username input",
            current_url=None,
            pages_data=pages_data,
        )
    )

    assert result is not None, "Should find a match across pages"
    assert result["selector"] == "#user-name", (
        f"Expected #user-name from login page, got {result['selector']} from wrong page"
    )


def test_global_best_password() -> None:
    """Resolving 'password input' should find #password on login page, not cart elements."""
    cart_elements = [
        make_element("#continue-shopping", text="Continue Shopping", role="button"),
        make_element("#checkout", text="Checkout", role="button"),
    ]
    login_elements = [
        make_element("#user-name", role="text", name="user-name"),
        make_element("#password", role="password", name="password"),
        make_element("#login-button", role="submit", name="login-button"),
    ]

    pages_data = {
        "https://www.saucedemo.com/cart.html": cart_elements,
        "https://www.saucedemo.com": login_elements,
    }

    orchestrator = PlaceholderOrchestrator()
    result = asyncio.run(
        orchestrator._find_best_element_for_current_page(
            action="FILL",
            description="password input",
            current_url=None,
            pages_data=pages_data,
        )
    )

    assert result is not None
    assert result["selector"] == "#password"


def test_global_best_login_button() -> None:
    """Resolving 'login button' should find #login-button, not cart buttons."""
    cart_elements = [
        make_element("#continue-shopping", text="Continue Shopping", role="button"),
        make_element("#checkout", text="Checkout", role="button"),
    ]
    login_elements = [
        make_element("#user-name", role="text", name="user-name"),
        make_element("#password", role="password", name="password"),
        make_element("#login-button", role="submit", name="login-button"),
    ]

    pages_data = {
        "https://www.saucedemo.com/cart.html": cart_elements,
        "https://www.saucedemo.com": login_elements,
    }

    orchestrator = PlaceholderOrchestrator()
    result = asyncio.run(
        orchestrator._find_best_element_for_current_page(
            action="CLICK",
            description="login button",
            current_url=None,
            pages_data=pages_data,
        )
    )

    assert result is not None
    assert result["selector"] == "#login-button"


def test_global_best_checkout_button() -> None:
    """Resolving 'checkout button' should find #checkout on cart page, not login elements."""
    login_elements = [
        make_element("#user-name", role="text", name="user-name"),
        make_element("#password", role="password", name="password"),
        make_element("#login-button", role="submit", name="login-button"),
    ]
    cart_elements = [
        make_element("#continue-shopping", text="Continue Shopping", role="button"),
        make_element("#checkout", text="Checkout", role="button"),
        make_element("#item_4_title_link", text="Sauce Labs Backpack", role="link"),
    ]

    pages_data = {
        "https://www.saucedemo.com": login_elements,
        "https://www.saucedemo.com/cart.html": cart_elements,
    }

    orchestrator = PlaceholderOrchestrator()
    result = asyncio.run(
        orchestrator._find_best_element_for_current_page(
            action="CLICK",
            description="checkout button",
            current_url=None,
            pages_data=pages_data,
        )
    )

    assert result is not None
    assert result["selector"] == "#checkout"


def test_no_match_returns_none() -> None:
    """When no element matches any page, return None (not a wrong match)."""
    cart_elements = [
        make_element("#continue-shopping", text="Continue Shopping", role="button"),
    ]
    login_elements = [
        make_element("#user-name", role="text", name="user-name"),
    ]

    pages_data = {
        "https://www.saucedemo.com/cart.html": cart_elements,
        "https://www.saucedemo.com": login_elements,
    }

    orchestrator = PlaceholderOrchestrator()
    result = asyncio.run(
        orchestrator._find_best_element_for_current_page(
            action="CLICK",
            description="nonexistent element that does not exist anywhere",
            current_url=None,
            pages_data=pages_data,
        )
    )

    # Should return None rather than a wrong match
    assert result is None


if __name__ == "__main__":
    test_global_best_across_pages()
    test_global_best_password()
    test_global_best_login_button()
    test_global_best_checkout_button()
    test_no_match_returns_none()
    print("All tests passed!")
