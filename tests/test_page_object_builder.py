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
