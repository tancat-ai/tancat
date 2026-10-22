"""t-0847: the known navigation target (the human-practice link).

The cursor may only move to a page whose identity is KNOWN. When the
current page carries a hyperlink that names the destination, that link is
the target: the human clicks it, the browser lands where the site sends
it, and the resolver follows the observation.

These tests pin the rules that decide which element is that link:

- only an anchor counts (a button with the same words is a different act);
- the link must cover every identity word of the description;
- grammar words ("go to the ... page") do not name the target.
"""

from __future__ import annotations

from typing import Any

from src.navigation_target import (
    anchor_href_target,
    find_navigation_anchor,
    identity_words,
    is_anchor,
    start_page_url,
    target_words,
)

CART_LINK: dict[str, Any] = {
    "selector": '[data-test="shopping-cart-link"]',
    "text": "",
    "tag": "a",
    "role": "button",
    "aria_label": "Cart, empty",
    "accessible_name": "Cart, empty",
    "data_test": "shopping-cart-link",
    "classes": "shopping_cart_link",
    "href": "",
    "is_visible": True,
}

ADD_TO_CART_BUTTON: dict[str, Any] = {
    "selector": "#add-to-cart-sauce-labs-backpack",
    "text": "Add to cart",
    "tag": "button",
    "role": "button",
    "href": "",
    "is_visible": True,
}

TRANSFER_LINK: dict[str, Any] = {
    "selector": 'a[href="/transfer.html"]',
    "text": "Transfer",
    "tag": "a",
    "role": "link",
    "href": "http://localhost:8781/transfer.html",
    "is_visible": True,
}

BILL_LINK: dict[str, Any] = {
    "selector": 'a[href="/payments.html"]',
    "text": "Bill Payments",
    "tag": "a",
    "role": "link",
    "href": "http://localhost:8781/payments.html",
    "is_visible": True,
}


def test_target_words_drops_grammar() -> None:
    """'go to the transfer page' names 'transfer'; the rest is grammar."""
    assert target_words("go to the transfer page") == {"transfer"}
    assert target_words("navigate to bill payments") == {"bill", "payments"}
    # Nothing but grammar: keep the raw words rather than an empty set.
    assert target_words("the page") == {"page", "the"}


def test_is_anchor_accepts_anchors_only() -> None:
    """A button is not a link, even when it carries the same words."""
    assert is_anchor(CART_LINK)
    assert is_anchor(TRANSFER_LINK)
    assert not is_anchor(ADD_TO_CART_BUTTON)


def test_identity_words_reads_the_accessible_name_and_the_href() -> None:
    """An icon link with no text is still named by its label and its href."""
    assert "cart" in identity_words(CART_LINK)
    assert "transfer" in identity_words(TRANSFER_LINK)
    assert "html" not in identity_words(CART_LINK)


def test_find_navigation_anchor_picks_the_cart_link_not_the_add_to_cart_button() -> None:
    """'cart' names the cart link. 'Add to cart' is a different action."""
    elements = [ADD_TO_CART_BUTTON, CART_LINK]
    found = find_navigation_anchor("cart", elements)
    assert found is not None
    assert found["selector"] == '[data-test="shopping-cart-link"]'


def test_find_navigation_anchor_accepts_a_navigation_phrase() -> None:
    """'go to the transfer page' still finds the Transfer link."""
    found = find_navigation_anchor("go to the transfer page", [TRANSFER_LINK, BILL_LINK])
    assert found is not None
    assert found["selector"] == 'a[href="/transfer.html"]'


def test_find_navigation_anchor_rejects_a_partial_match() -> None:
    """A link that covers only part of the description names another thing."""
    assert find_navigation_anchor("bill payments", [TRANSFER_LINK]) is None
    assert find_navigation_anchor("cart", [TRANSFER_LINK]) is None


def test_find_navigation_anchor_ignores_hidden_elements() -> None:
    """A hidden link is not a click target."""
    hidden = dict(CART_LINK, is_visible=False)
    assert find_navigation_anchor("cart", [hidden]) is None


def test_anchor_href_target_is_the_real_href() -> None:
    """The href is the only proof of a link's destination."""
    assert anchor_href_target(TRANSFER_LINK, "http://localhost:8781/dashboard.html") == (
        "http://localhost:8781/transfer.html"
    )
    # A JS-driven link carries no href: its destination is not knowable here.
    assert anchor_href_target(CART_LINK, "http://localhost:8781/dashboard.html") is None


def test_start_page_url_names_the_entry_page() -> None:
    """The word "home" is the URL the human gave us - even at /index.html."""
    mock_home = "http://localhost:8781/index.html"
    assert start_page_url("home", mock_home) == mock_home
    assert start_page_url("homepage", mock_home) == mock_home
    assert start_page_url("https://www.saucedemo.com", None) is None
    assert start_page_url("cart", mock_home) is None
    assert start_page_url("home", "https://www.saucedemo.com") == "https://www.saucedemo.com"
