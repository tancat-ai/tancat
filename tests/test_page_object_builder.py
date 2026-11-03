"""Tests for page object generation from scraped pages."""

import re

import pytest

from src.code_postprocessor import strip_evidence_from_pom
from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import ScrapedPage

# t-1211: an internal id - the letter block of one of our families, a dash, digits -
# must not reach a file that lands in the user's own repository, where such a number
# means nothing and only adds noise.
#
# t-1216: the first version matched ANY short letter block (``\b[A-Za-z]{1,5}-\d{2,5}\b``),
# so a page's own text failed the guard: a Bootstrap grid class (``#col-12``), a URL
# path segment (``p-12``), an element's own label. The pattern now names the id families
# this repo actually uses - B, AI, and the lowercase tracker families d, t, j, q - so it
# still catches every id we write and no longer reads a page as if it were one of ours.
# A real id of ours must keep firing: if a family is missing, add it here deliberately,
# never by widening the letter block back out.
_INTERNAL_ID_PATTERN = re.compile(r"\b(?:B|AI|[dtjq])-\d{3,4}\b")


def test_build_page_object_uses_home_page_defaults() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=1,
        elements=[{"selector": "#search", "role": "text", "placeholder": "Search"}],
    )

    page_object = builder.build_page_object(scraped_page)

    assert page_object.class_name == "HomePage"
    assert page_object.module_name == "home_page"
    assert "goto" in page_object.module_source
    assert "fill_search" in page_object.methods


def test_build_page_object_maps_cart_navigation_and_checkout_actions() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/products",
        element_count=3,
        elements=[
            {"selector": '[data-product-id="1"]', "role": "button", "text": "Add to Cart"},
            {"selector": 'a[href="/view_cart"]', "role": "a", "text": "Cart", "href": "https://example.com/view_cart"},
            {
                "selector": 'a[href="/checkout"]',
                "role": "a",
                "text": "Proceed To Checkout",
                "href": "https://example.com/checkout",
            },
        ],
    )

    page_object = builder.build_page_object(scraped_page, file_path="generated_tests/run_1/pages/products_page.py")

    assert page_object.class_name == "ProductsPage"
    assert page_object.file_path.endswith("products_page.py")
    assert page_object.methods == ["add_item_to_cart", "navigate_to_cart", "proceed_to_checkout"]
    assert "self.page.locator('[data-product-id=\"1\"]').click()" in page_object.module_source
    assert "def navigate_to_cart(self) -> None" in page_object.module_source
    assert "def proceed_to_checkout(self) -> None" in page_object.module_source


def test_build_page_object_creates_fallback_method_when_no_actions_exist() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(url="https://example.com/account", element_count=0, elements=[])

    page_object = builder.build_page_object(scraped_page)

    assert page_object.class_name == "AccountPage"
    assert page_object.methods == []
    assert "def page_ready(self) -> None" in page_object.module_source


def test_build_page_object_uses_first_for_duplicate_click_selectors() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/products",
        element_count=2,
        elements=[
            {"selector": '[data-product-id="1"]', "role": "button", "text": "Add to Cart"},
            {"selector": '[data-product-id="1"]', "role": "button", "text": "Add to Cart"},
        ],
    )

    page_object = builder.build_page_object(scraped_page)

    assert "self.page.locator('[data-product-id=\"1\"]').first.click()" in page_object.module_source


# ── Evidence-aware POM tests (AI-010 Phase 1) ────────────────────────────────


def test_build_evidence_aware_pom_imports_tracker() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=1,
        elements=[{"selector": "#search", "role": "text", "placeholder": "Search"}],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    assert "from src.evidence_tracker import EvidenceTracker" in page_object.module_source


def test_evidence_aware_pom_init_accepts_tracker() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=1,
        elements=[{"selector": "#search", "role": "text", "placeholder": "Search"}],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    assert "def __init__(self, page: Page, tracker: EvidenceTracker) -> None:" in page_object.module_source
    assert "self.tracker = tracker" in page_object.module_source


def test_evidence_aware_pom_click_delegates_to_tracker() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=1,
        elements=[{"selector": "#submit-btn", "role": "button", "text": "Submit"}],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    # POM methods delegate to tracker
    assert "self.tracker.click('#submit-btn', label='submit')" in page_object.module_source
    # B-028: generic click() fallback uses the DOM-existence index (scraped
    # selectors only) and pytest.skip — never a hallucinated text= locator.
    assert "self.page.locator('text=' + description)" not in page_object.module_source
    assert "_ELEMENTS: tuple = (" in page_object.module_source
    assert 'pytest.skip(f"No element matches' in page_object.module_source


def test_evidence_aware_pom_fill_delegates_to_tracker() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=1,
        elements=[{"selector": "#username", "role": "text", "placeholder": "Username"}],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    assert "self.tracker.fill('#username', value, label='username')" in page_object.module_source


def test_evidence_aware_pom_navigate_delegates_to_tracker() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=0,
        elements=[],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    # d-0043: the page object names the page it expects, so a redirect is judged
    # there exactly as a flat-mode goto is (j-0226).
    assert "self.tracker.navigate(self.URL, expected_page=self.URL)" in page_object.module_source
    assert "self.page.goto" not in page_object.module_source


def test_emitted_and_exported_pom_carry_no_internal_ids() -> None:
    """t-1211: no internal id reaches a file that lands in a user's repository.

    Covers both the emitted module source and the export copy, for both the
    evidence-aware and the plain variant, because the defect showed up in each
    path separately (B-028 in the click fallback comment and in the element index).

    The reason behind each guard belongs in this builder's own source, where it is
    read by us and never shipped - see the comments above ``navigate_code`` and
    ``_build_element_index_source``.
    """
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=2,
        elements=[
            {"selector": "#username", "role": "text", "placeholder": "Username"},
            {"selector": "#login", "role": "button", "text": "Log in"},
        ],
    )

    for use_evidence_tracker in (True, False):
        emitted = builder.build_page_object(scraped_page, use_evidence_tracker=use_evidence_tracker).module_source
        exported = strip_evidence_from_pom(emitted)
        for label, source in (("emitted", emitted), ("exported", exported)):
            found = _INTERNAL_ID_PATTERN.findall(source)
            assert not found, f"{label} page object (tracker={use_evidence_tracker}) names internal ids: {found}"


@pytest.mark.parametrize("ticket_id", ["B-028", "AI-052", "d-0043", "t-1201", "j-0226", "j-0259", "q-0007"])
def test_the_guard_catches_every_id_family_we_write(ticket_id: str) -> None:
    """t-1216: the narrow pattern must catch every id this repo actually writes.

    One case per family - B, AI, and the lowercase tracker families d/t/j/q - taken
    from ids that exist in this repo. j-0259 is included on purpose: it is the id a
    live CI run reported in emitted text, and tightening the pattern must not turn a
    real finding into a pass.
    """
    emitted_comment = "        # Name the page this object expects - see " + ticket_id + " in the builder.\n"

    assert _INTERNAL_ID_PATTERN.search(emitted_comment), f"the guard let a real id through: {ticket_id}"


def test_the_id_bearing_lines_the_builder_emitted_at_d1fbb15_are_caught() -> None:
    """The other direction, verbatim: the text that commit shipped is still caught.

    d1fbb15 is the merge before the id removal landed (bb9fa2c); its builder emitted
    ``B-028`` in two strings of the generated module - the element-index comment and
    the click fallback comment, in both the tracker and the plain variant. These are
    those strings, quoted, so a tightened pattern cannot quietly stop noticing them
    without a git checkout of an old commit.
    """
    shipped_at_d1fbb15 = (
        "    # B-028: DOM-existence index \u2014 label words -> scraped selector.\n"
        "        # Last resort: element-index lookup (B-028 DOM-existence guard).\n"
    )

    found = _INTERNAL_ID_PATTERN.findall(shipped_at_d1fbb15)

    assert found == ["B-028", "B-028"], f"the id the old builder shipped is no longer caught: {found}"


def test_a_page_that_looks_like_an_id_passes_the_guard() -> None:
    """t-1216: the guard reads our ids, not the page's own text.

    A Bootstrap grid class (``#col-12``), a URL path segment (``p-12``) and an element
    whose own label carries the same shape are a page's facts, not our tickets. The old
    letter-block pattern failed this build and listed them as if they were ours.
    """
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/order/p-12",
        element_count=2,
        elements=[
            {"selector": "#col-12", "role": "button", "text": "Continue"},
            {"selector": 'a[href="/order/p-12/next"]', "role": "a", "text": "col-12"},
        ],
    )

    for use_evidence_tracker in (True, False):
        emitted = builder.build_page_object(scraped_page, use_evidence_tracker=use_evidence_tracker).module_source
        for label, source in (("emitted", emitted), ("exported", strip_evidence_from_pom(emitted))):
            found = _INTERNAL_ID_PATTERN.findall(source)
            assert not found, f"{label} page object (tracker={use_evidence_tracker}) is failed by page text: {found}"
            assert "col-12" in source, f"{label} source no longer carries the page's own selector: {source}"


def test_evidence_aware_pom_label_derived_from_method_name() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/products",
        element_count=1,
        elements=[{"selector": "#add-to-cart", "role": "button", "text": "Add to Cart"}],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    # "add_item_to_cart" -> label "add item to cart"
    assert "label='add item to cart'" in page_object.module_source


def test_backward_compatible_no_tracker() -> None:
    """Without use_evidence_tracker, generates raw page.locator (default behaviour)."""
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=2,
        elements=[
            {"selector": "#username", "role": "text", "placeholder": "Username"},
            {"selector": "#login-btn", "role": "button", "text": "Login"},
        ],
    )

    page_object = builder.build_page_object(scraped_page)

    # Default mode uses page.locator
    assert "self.page.locator('#username').fill(value)" in page_object.module_source
    assert "self.page.locator('#login-btn').click()" in page_object.module_source
    # Default mode does NOT import EvidenceTracker
    assert "EvidenceTracker" not in page_object.module_source
    # Default mode uses simple __init__
    assert "def __init__(self, page: Page) -> None:" in page_object.module_source


def test_evidence_aware_pom_navigate_method() -> None:
    """Evidence-aware POM navigate() uses tracker.navigate instead of page.goto."""
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/products",
        element_count=1,
        elements=[{"selector": "#item", "role": "button", "text": "Item"}],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    assert "self.tracker.navigate(self.URL, expected_page=self.URL)" in page_object.module_source


def test_evidence_aware_pom_select_delegates_to_tracker() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/",
        element_count=1,
        elements=[{"selector": "#country", "role": "select", "text": "Country"}],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    assert "self.tracker.fill('#country', value, label='country')" in page_object.module_source


def test_evidence_aware_pom_cart_navigation_delegates_to_tracker() -> None:
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/products",
        element_count=1,
        elements=[
            {"selector": 'a[href="/cart"]', "role": "a", "text": "Cart", "href": "https://example.com/cart"},
        ],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    assert "self.tracker.click('a[href=\"/cart\"]', label='" in page_object.module_source
    assert "def navigate_to_cart(self) -> None" in page_object.module_source


# ── B-028: DOM-existence guard for the generic click() fallback ────────────


def test_click_fallback_uses_dom_existence_index() -> None:
    """B-028: unresolved descriptions must resolve via scraped selectors only.

    The generated click() must never emit ``text=<description>`` locators
    (hallucination). Descriptions that match a scraped element's label use its
    selector; unmatchable descriptions pytest.skip.
    """
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/products",
        element_count=2,
        elements=[
            {"selector": 'a[href="/product_details/1"]', "role": "a", "text": "View Product"},
            {"selector": 'a[href="/view_cart"]', "role": "a", "text": "View Cart"},
        ],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)
    module_source = page_object.module_source
    compile(module_source, "<generated>", "exec")

    # The index maps label words -> scraped selectors.
    assert "('view product', 'a[href=\"/product_details/1\"]')" in module_source
    assert "('view cart', 'a[href=\"/view_cart\"]')" in module_source
    # No hallucinated text locator anywhere in the generated POM.
    assert "self.page.locator('text=' + description)" not in module_source

    # Runtime behaviour: "First product link" (LLM invention) maps to the first
    # scraped product card — it is NOT emitted as text=First product link.
    namespace: dict = {}
    exec(module_source, namespace)  # noqa: S102

    class FakeTracker:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def click(self, locator: str, label: str = "", must_move: bool = False) -> None:
            self.calls.append((locator, label))

    tracker = FakeTracker()
    pom = namespace["ProductsPage"](object(), tracker)  # type: ignore[attr-defined]
    pom.click("First product link")
    assert tracker.calls == [('a[href="/product_details/1"]', "First product link")]


def test_click_fallback_skips_unmatchable_description() -> None:
    """B-028: a description with no scraped element match must pytest.skip."""
    import pytest as _pytest

    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/products",
        element_count=1,
        elements=[{"selector": 'a[href="/view_cart"]', "role": "a", "text": "View Cart"}],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)
    namespace: dict = {}
    exec(page_object.module_source, namespace)  # noqa: S102

    tracker = type("T", (), {"click": lambda self, *a, **k: None})()
    pom = namespace["ProductsPage"](object(), tracker)  # type: ignore[attr-defined]

    # "add to cart" shares only "cart" with "view cart" — below the 2-word
    # minimum, so it must skip instead of clicking the wrong element.
    with _pytest.raises(_pytest.skip.Exception):
        pom.click("add to cart button")


def test_hidden_elements_excluded_from_pom_methods() -> None:
    """B-028 follow-up: hidden/non-interactive elements (CSRF token inputs)
    must never become POM click methods — they burned ~29s of fallback
    attempts per click during live execution."""
    builder = PageObjectBuilder()
    scraped_page = ScrapedPage(
        url="https://example.com/cart",
        element_count=3,
        elements=[
            {"selector": 'input[name="csrfmiddlewaretoken"]', "role": "hidden", "name": "csrfmiddlewaretoken"},
            {"selector": 'a[href="/view_cart"]', "role": "a", "text": "Cart"},
        ],
    )

    page_object = builder.build_page_object(scraped_page, use_evidence_tracker=True)

    assert "csrf" not in " ".join(page_object.methods)
    assert "click_csrfmiddlewaretoken" not in page_object.module_source
    # The visible cart link still gets a method.
    assert "navigate_to_cart" in page_object.methods
