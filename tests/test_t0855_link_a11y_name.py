"""t-0855 (D1c): the browser-computed accessible name names a link.

The three D1 resolver cuts, of which this file covers (c). The link picker
(``JourneyScraper._discover_link_selector``, t-0847) reads the page's MARKUP:
visible text, aria-label, data attributes, the href path. That is enough when
the site labels its links well. When it does not - an icon-only anchor, or two
links that both say "Shop" - the markup cannot say which link the human means,
while the browser CAN: the accessible name is computed by the web standard
(aria-labelledby, a child ``alt``, an SVG ``<title>``).

These tests pin the addition:

* the accessible name wins a link whose visible text is absent;
* the accessible name wins a link whose visible text is ambiguous;
* the markup still wins when it names the link, so nothing existing moves;
* with no a11y snapshot the picker behaves exactly as before.

No browser: the fake page serves HTML to the real extractor and returns the
aria snapshot text the browser would return.
"""

from __future__ import annotations

from typing import Any

from src.journey_scraper import JourneyScraper

PAGE_URL = "https://shop.example.com/"

# Two links with the SAME visible text and hrefs that name neither
# destination: only the browser's accessible names tell them apart.
AMBIGUOUS_HTML = """
<html><body>
  <nav>
    <a href="/p1.html">Shop</a>
    <a href="/p2.html">Shop</a>
  </nav>
</body></html>
"""

AMBIGUOUS_ARIA = """- navigation:
  - link "Product catalogue":
    - /url: /p1.html
  - link "Shopping cart":
    - /url: /p2.html
"""

# An icon-only anchor: an image link with no text of its own. The markup
# extractor does not surface the image's alt as the anchor's name, so only the
# browser's computed accessible name identifies it.
UNLABELLED_HTML = """
<html><body>
  <nav>
    <a href="/p9.html"><img src="cart.png" alt="Shopping cart"></a>
  </nav>
</body></html>
"""

UNLABELLED_ARIA = """- navigation:
  - link "Shopping cart":
    - /url: /p9.html
"""


class _FakePage:
    """Minimal Playwright page: HTML content, a URL, visibility, aria snapshot."""

    def __init__(self, html: str, aria: str = "") -> None:
        self._html = html
        self._aria = aria
        self.url = PAGE_URL

    def wait_for_load_state(self, *args: Any, **kwargs: Any) -> None:
        pass

    def content(self) -> str:
        return self._html

    def aria_snapshot(self, boxes: bool = False) -> str:
        if not self._aria:
            raise RuntimeError("aria snapshot not available")
        return self._aria

    def locator(self, selector: str) -> Any:
        raise RuntimeError("no live browser in this test")


def _pick(html: str, aria: str, description: str) -> str | None:
    scraper = JourneyScraper(starting_url=PAGE_URL)
    return scraper._discover_link_selector(_FakePage(html, aria), description)


# ── the addition ─────────────────────────────────────────────────────────


def test_accessible_name_wins_an_ambiguous_link() -> None:
    """Two links both say "Shop"; the accessible name says which is the cart."""
    selector = _pick(AMBIGUOUS_HTML, AMBIGUOUS_ARIA, "cart")
    assert selector is not None, "the cart link was not found - the a11y name did not decide"
    assert "/p2.html" in selector, f"picked the wrong link: {selector}"


def test_accessible_name_wins_a_link_with_no_visible_text() -> None:
    """An icon-only anchor whose only identity is its computed name."""
    selector = _pick(UNLABELLED_HTML, UNLABELLED_ARIA, "cart")
    assert selector is not None, "the icon-only cart link was not found via its accessible name"
    assert "/p9.html" in selector, f"picked the wrong link: {selector}"


def test_the_same_ambiguous_page_is_unresolvable_without_the_a11y_name() -> None:
    """Control: this is the defect. Markup alone cannot tell the two apart."""
    assert _pick(AMBIGUOUS_HTML, "", "cart") is None


def test_the_same_icon_only_page_is_unresolvable_without_the_a11y_name() -> None:
    """Control: an anchor with no text and a meaningless href is invisible to markup."""
    assert _pick(UNLABELLED_HTML, "", "cart") is None


# ── nothing that already worked may move ─────────────────────────────────


def test_markup_still_wins_when_it_names_the_link() -> None:
    """A well-labelled link resolves from the markup, before the a11y pass."""
    html = """
    <html><body>
      <nav><a href="/cart.html">Cart</a></nav>
    </body></html>
    """
    aria = """- navigation:
  - link "Cart":
    - /url: /cart.html
"""
    selector = _pick(html, aria, "cart")
    assert selector is not None
    assert "/cart.html" in selector, f"picked the wrong link: {selector}"


def test_a_page_with_no_naming_link_still_resolves_to_nothing() -> None:
    """The honest skip survives: neither markup nor a11y name names a cart."""
    html = """
    <html><body>
      <nav><a href="/p1.html">Shop</a></nav>
    </body></html>
    """
    aria = """- navigation:
  - link "Product catalogue":
    - /url: /p1.html
"""
    assert _pick(html, aria, "cart") is None


def test_a_failed_aria_snapshot_leaves_the_markup_path_untouched() -> None:
    """An unavailable snapshot must never break link discovery."""
    html = """
    <html><body>
      <nav><a href="/cart.html">Cart</a></nav>
    </body></html>
    """

    class _NoSnapshotPage(_FakePage):
        def aria_snapshot(self, boxes: bool = False) -> str:
            raise RuntimeError("CDP unavailable")

    scraper = JourneyScraper(starting_url=PAGE_URL)
    selector = scraper._discover_link_selector(_NoSnapshotPage(html), "cart")
    assert selector is not None and "/cart.html" in selector
