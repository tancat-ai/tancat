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


def test_remove_consent_overlays_filters_onetrust_class_markup() -> None:
    """OneTrust consent frameworks keep hidden .fc-* / #onetrust markup in the DOM.

    Regression: consent removal previously only matched ID-based selectors, so
    class-based OneTrust preference-center elements polluted the scrape (1,448
    of 2,328 elements on automationexercise.com).
    """
    html = """
    <html><body>
      <div class="fc-consent-root"><button>Consent</button></div>
      <div class="fc-preference-container">
        <h2 class="fc-preference-slider-label">vendor a</h2>
        <p class="fc-truncated-single-line">data</p>
      </div>
      <div id="onetrust-banner-sdk"><button>Accept all</button></div>
      <a href="/products">Products</a>
      <a href="/product_details/1">View product</a>
    </body></html>
    """
    cleaned = PageScraper._remove_consent_overlays(html)

    assert "fc-consent-root" not in cleaned
    assert "fc-preference-container" not in cleaned
    assert "fc-truncated-single-line" not in cleaned
    assert "onetrust-banner-sdk" not in cleaned
    # Real page content must survive
    assert "/products" in cleaned
    assert "/product_details/1" in cleaned


def test_soft_404_detects_spa_bootstrap() -> None:
    """SPA-hosted sites rewrite the URL after a 4xx — treat as a usable page."""
    assert (
        PageScraper._is_soft_404(
            "https://www.saucedemo.com/inventory.html",
            "https://www.saucedemo.com/",
        )
        is True
    )


def test_soft_404_false_when_url_unchanged() -> None:
    """A genuine 404 keeps the requested URL — the scrape really failed."""
    assert (
        PageScraper._is_soft_404(
            "https://example.com/missing.html",
            "https://example.com/missing.html",
        )
        is False
    )


def test_soft_404_false_for_empty_final_url() -> None:
    assert PageScraper._is_soft_404("https://example.com/missing.html", "") is False


def test_soft_404_ignores_trailing_slash_differences() -> None:
    assert PageScraper._is_soft_404("https://example.com/", "https://example.com/") is False
    assert PageScraper._is_soft_404("https://example.com/foo/", "https://example.com/foo") is False


# ── B-065: Unmatchable selectors (Tailwind variants, href host) ─────────────


def test_extract_elements_keeps_absolute_href_in_link_selector() -> None:
    """Absolute hrefs must stay absolute in the selector.

    CSS attribute selectors match the literal attribute value, so the old
    behaviour (parsed path only) produced a[href="/tancat-ai/..."] which never
    matched href="https://github.com/tancat-ai/..." (B-065).
    """
    scraper = PageScraper()
    html = """
    <html><body>
      <a href="https://github.com/tancat-ai/tancat/blob/main/docs/security/egress-audit.md">Egress Audit</a>
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html, base_url="http://localhost:8079/")
    link = next(
        e
        for e in elements
        if e["href"] == "https://github.com/tancat-ai/tancat/blob/main/docs/security/egress-audit.md"
    )
    assert link["selector"] == 'a[href="https://github.com/tancat-ai/tancat/blob/main/docs/security/egress-audit.md"]'
    assert link["raw_href"] == "https://github.com/tancat-ai/tancat/blob/main/docs/security/egress-audit.md"
    from bs4 import BeautifulSoup

    assert len(BeautifulSoup(html, "html.parser").select(link["selector"])) == 1


def test_extract_elements_relative_href_selector_unchanged() -> None:
    """Relative hrefs already matched the attribute value — keep that behaviour."""
    scraper = PageScraper()
    html = """
    <html><body>
      <a href="/view_cart">Cart</a>
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html, base_url="https://example.com/")
    assert elements[0]["selector"] == 'a[href="/view_cart"]'
    assert elements[0]["raw_href"] == "/view_cart"


def test_extract_elements_mailto_link_falls_back_to_class() -> None:
    """Non-navigable hrefs (mailto/tel/fragments) keep the class fallback."""
    scraper = PageScraper()
    html = """
    <html><body>
      <a href="mailto:hello@tancat.dev" class="mail-link">hello</a>
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html)
    link = next(e for e in elements if e.get("raw_href") == "mailto:hello@tancat.dev")
    assert link["selector"] == ".mail-link"


def test_extract_elements_escapes_tailwind_variant_classes() -> None:
    """hover:/sm:/md: variant classes stay single matchable classes.

    Unescaped, .hover:text-amber-200 parses as the class .hover plus a
    pseudo-class and matches nothing (B-065).
    """
    scraper = PageScraper()
    html = """
    <html><body>
      <div class="mt-2 block font-mono hover:text-amber-200 py-3.5 w-1/2">Buy Pro</div>
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html)
    card = next(e for e in elements if e.get("classes") and "hover:text-amber-200" in e["classes"])
    assert card["selector"] == ".mt-2.block.font-mono.hover\\:text-amber-200.py-3\\.5.w-1\\/2"
    from bs4 import BeautifulSoup

    assert len(BeautifulSoup(html, "html.parser").select(card["selector"])) == 1


def test_extract_elements_escapes_leading_digit_classes() -> None:
    """Classes starting with a digit (3xl:) use the six-digit unicode escape."""
    scraper = PageScraper()
    html = """
    <html><body>
      <h2 class="3xl:flex items-center">Regulated buyer</h2>
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html)
    heading = next(e for e in elements if e.get("tag") == "h2")
    assert heading["selector"] == ".\\000033xl\\:flex.items-center"
    from bs4 import BeautifulSoup

    assert len(BeautifulSoup(html, "html.parser").select(heading["selector"])) == 1
