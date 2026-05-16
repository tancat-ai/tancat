"""Tests for the lightweight HTML scraper."""

from src.scraper import PageScraper


def test_extract_elements_from_html_prefers_specific_selectors() -> None:
    scraper = PageScraper()
    html = """
    <html><body>
      <button id="submit-order">Submit Order</button>
      <a data-testid="view-cart">View Cart</a>
    </body></html>
    """

    elements = scraper._extract_elements_from_html(html)
    selectors = {element["selector"]: element for element in elements}

    assert selectors["#submit-order"]["text"] == "Submit Order"
    assert selectors["#submit-order"]["role"] == "button"
    assert selectors['[data-testid="view-cart"]']["text"] == "View Cart"
    assert selectors['[data-testid="view-cart"]']["role"] == "a"


def test_extract_elements_from_html_uses_href_for_links_when_available() -> None:
    scraper = PageScraper()
    html = """
    <html><body>
      <a href="/view_cart" title="Cart">Cart</a>
    </body></html>
    """

    elements = scraper._extract_elements_from_html(html, base_url="https://example.com/")

    assert elements[0]["selector"] == 'a[href="/view_cart"]'
    assert elements[0]["href"] == "https://example.com/view_cart"


# ── Session 2: Visibility Capture Tests ─────────────────────────────────────


def test_extract_elements_sets_is_visible_default_true() -> None:
    """All elements extracted from HTML should have is_visible=True as a safe default.

    The _capture_element_visibility() method overwrites this with actual Playwright
    runtime checks before the scraper returns. This test verifies the default is set.
    """
    scraper = PageScraper()
    html = """
    <html><body>
      <button id="login-btn">Login</button>
      <a href="/cart">Cart</a>
      <input type="text" name="username" />
    </body></html>
    """

    elements = scraper._extract_elements_from_html(html)

    for element in elements:
        assert element["is_visible"] is True, f"Element {element['selector']} should default to is_visible=True"


def test_extract_elements_is_visible_present_on_all_elements() -> None:
    """Every extracted element must have an is_visible key.

    Missing is_visible fields cause the placeholder resolver to skip visibility
    filtering entirely, leading to hidden elements being selected.
    """
    scraper = PageScraper()
    html = """
    <html><body>
      <button id="btn">Click</button>
      <a data-testid="nav-link" href="/page">Link</a>
      <input id="field" type="password" />
      <textarea id="notes"></textarea>
      <select id="dropdown"><option>One</option></select>
    </body></html>
    """

    elements = scraper._extract_elements_from_html(html)

    assert len(elements) == 5
    for element in elements:
        assert "is_visible" in element, f"Missing is_visible on {element['selector']}"


def test_capture_element_visibility_defaults_true_for_empty_selector() -> None:
    """Elements with no selector should default to is_visible=True (safe fallback)."""
    scraper = PageScraper()
    elements = [{"selector": "", "text": "orphan"}]

    # Simulate what _capture_element_visibility does for empty selectors
    result = scraper._capture_element_visibility(None, elements)  # type: ignore[arg-type]

    assert result[0]["is_visible"] is True


def test_capture_element_visibility_preserves_existing_elements() -> None:
    """_capture_element_visibility should return the same element dicts (mutated in-place)."""
    scraper = PageScraper()
    elements = [
        {"selector": "#btn", "text": "Click"},
        {"selector": "", "text": "no selector"},
    ]

    result = scraper._capture_element_visibility(None, elements)  # type: ignore[arg-type]

    # When page is None, visibility checks will fail and default to True
    assert len(result) == 2
    assert result[0]["selector"] == "#btn"
    assert result[1]["selector"] == ""
    assert result[0]["is_visible"] is True
    assert result[1]["is_visible"] is True
