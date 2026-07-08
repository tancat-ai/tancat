"""Tests for page object generation from scraped pages."""

from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import ScrapedPage


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
    # Generic click() fallback uses page.locator with text matching for fast-fail
    assert "self.page.locator('text=' + description).first.click(timeout=3000)" in page_object.module_source


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

    assert "self.tracker.navigate(self.URL)" in page_object.module_source
    assert "self.page.goto" not in page_object.module_source


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

    assert "self.tracker.navigate(self.URL)" in page_object.module_source


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
