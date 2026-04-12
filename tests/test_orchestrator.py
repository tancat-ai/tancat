"""Tests for the intelligent pipeline orchestrator."""

import asyncio
from unittest.mock import AsyncMock

from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


def test_run_pipeline_replaces_placeholders_with_scraped_locators() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page, expect

def test_checkout(page: Page):
    page.locator({{CLICK:add_to_cart_button}}).click()
    page.goto({{GOTO:cart_url}})
    {{ASSERT:cart_summary}}

# PAGES_NEEDED:
# - https://example.com/products (products)
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/products": [
                {"selector": "#add-to-cart", "text": "Add To Cart Button", "role": "button"},
            ],
            "https://example.com/view_cart": [
                {
                    "selector": "#cart-summary",
                    "text": "Items in cart",
                    "role": "region",
                    "href": "https://example.com/view_cart",
                }
            ],
        }
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a customer I want to add a product to the cart",
            conditions="1. User can add an item to cart",
            target_urls=["https://example.com/"],
        )
    )

    assert "page.locator('#add-to-cart:visible').click()" in final_code
    assert "page.goto(" in final_code
    assert "https://example.com/view_cart" in final_code
    assert "expect(page.locator('#cart-summary')).to_be_visible()" in final_code
    assert orchestrator.last_result is not None
    assert [journey.test_name for journey in orchestrator.last_result.journeys] == ["test_checkout"]
    scraped_urls = [page.url for page in orchestrator.last_result.scraped_page_records]
    generated_class_names = [page_object.class_name for page_object in orchestrator.last_result.generated_page_objects]
    assert "https://example.com/" in scraped_urls
    assert "https://example.com/products" in scraped_urls
    assert "https://example.com/view_cart" in scraped_urls
    assert "HomePage" in generated_class_names
    assert "ProductsPage" in generated_class_names
    assert "CartPage" in generated_class_names
    assert any(
        page.url == "https://example.com/view_cart" and page.element_count == 1
        for page in orchestrator.last_result.scraped_page_records
    )


def test_run_pipeline_rejects_malformed_skeleton_before_resolution() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

def test_checkout(page: Page):
    {GOTO:Product Page URL}

# PAGES_NEEDED:
# - {URL:Product Page}
"""
    )

    orchestrator = TestOrchestrator(generator)

    try:
        asyncio.run(orchestrator.run_pipeline(user_story="story", conditions="1. criterion"))
        raise AssertionError("Expected malformed skeleton to raise ValueError")
    except ValueError as exc:
        assert "single-brace placeholders" in str(exc) or "invalid page entries" in str(exc)


def test_run_pipeline_normalises_page_object_output_and_pytest_imports() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page, expect

class CartPage:
    def __init__(self, page: Page):
        self.page = page

    def go_to_cart(self):
        page.locator({{CLICK:cart icon or link}})

def test_checkout(page: Page):
    cart_page = CartPage(page)
    {{GOTO:ecommerce_store_home}}
    cart_page.go_to_cart()
    {{CLICK:missing checkout button}}
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": [
                {
                    "selector": 'a[href="/view_cart"]',
                    "text": "Cart",
                    "role": "a",
                    "href": "https://example.com/view_cart",
                }
            ]
        }
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to go to cart",
            conditions="1. Go to cart",
            target_urls=["https://example.com/"],
        )
    )

    assert "import pytest" in final_code
    assert "page.goto(" in final_code
    assert "https://example.com/" in final_code
    assert "self.page.locator('a[href=\"/view_cart\"]:visible').click()" in final_code
    assert "pytest.skip" in final_code


def test_build_candidate_urls_stays_scoped_to_expected_journey_pages() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    orchestrator = TestOrchestrator(generator)
    journeys = orchestrator.parser.parse_test_journeys(
        """
from playwright.sync_api import Page

def test_01_add_to_cart(page: Page):
    {{GOTO:home page}}
    {{CLICK:add to cart}}

def test_02_go_to_cart(page: Page):
    {{GOTO:cart page}}
    {{ASSERT:items in cart}}
"""
    )

    discovered = orchestrator._build_candidate_urls(
        seed_urls=["https://example.com/"],
        page_requirements=[],
        journeys=journeys,
        user_story="As a shopper I want to add items to cart",
        conditions="1. Go to cart\n2. Check out",
    )

    assert discovered[0] == "https://example.com/"
    assert "https://example.com/products" in discovered
    assert "https://example.com/view_cart" in discovered
    assert "https://example.com/checkout" in discovered
    assert all("product_details" not in url for url in discovered)
    assert all("brand_products" not in url for url in discovered)


def test_run_pipeline_preserves_page_requirements_metadata() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

def test_checkout(page: Page):
    {{GOTO:home page}}
    {{CLICK:add to cart}}

# PAGES_NEEDED:
# - https://example.com/ (home)
# - https://example.com/products (products)
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": [{"selector": "#hero", "text": "Hero", "role": "region"}],
            "https://example.com/products": [{"selector": "#buy", "text": "Add to Cart", "role": "button"}],
        }
    )

    asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a customer I want to buy products",
            conditions="1. Add product to cart",
            target_urls=["https://example.com/"],
        )
    )

    assert orchestrator.last_result is not None
    assert [(page.url, page.description) for page in orchestrator.last_result.page_requirements] == [
        ("https://example.com/", "home"),
        ("https://example.com/products", "products"),
    ]


def test_run_pipeline_retries_when_skeleton_does_not_generate_one_test_per_criterion() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            """
from playwright.sync_api import Page

def test_combined(page: Page):
    {{CLICK:add to cart}}
    {{CLICK:go to cart}}
""",
            """
from playwright.sync_api import Page

def test_01_add_to_cart(page: Page):
    {{CLICK:add to cart}}

def test_02_go_to_cart(page: Page):
    {{CLICK:go to cart}}
""",
        ]
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={"https://example.com/": [{"selector": "#cart", "text": "Cart", "role": "button"}]}
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to add to cart and go to cart",
            conditions="1. Add to cart\n2. Go to cart",
            target_urls=["https://example.com/"],
        )
    )

    assert generator.generate_skeleton.await_count == 2  # type: ignore[attr-defined]
    assert "def test_01_add_to_cart" in final_code
    assert "def test_02_go_to_cart" in final_code


def test_run_pipeline_uses_first_for_duplicate_click_selectors() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

def test_checkout(page: Page):
    page.locator({{CLICK:add_to_cart_button}}).click()
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/products": [
                {"selector": '[data-product-id="1"]', "text": "Add To Cart Button", "role": "button"},
                {"selector": '[data-product-id="1"]', "text": "Add To Cart Button", "role": "button"},
            ]
        }
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a customer I want to add a product to the cart",
            conditions="1. Add to cart",
            target_urls=["https://example.com/products"],
        )
    )

    assert ".locator('[data-product-id=\"1\"]:visible').first.click()" in final_code


def test_run_pipeline_resolves_steps_against_the_current_journey_page() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page, expect

def test_01_go_to_cart(page: Page):
    {{GOTO:home page}}
    {{CLICK:cart link}}

def test_02_verify_cart(page: Page):
    {{GOTO:cart page}}
    {{ASSERT:cart summary}}
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": [
                {
                    "selector": 'a[href="/view_cart"]',
                    "text": "Cart",
                    "role": "a",
                    "href": "https://example.com/view_cart",
                },
                {
                    "selector": "#hero-summary",
                    "text": "Summary",
                    "role": "region",
                },
            ],
            "https://example.com/view_cart": [
                {
                    "selector": "#cart-summary",
                    "text": "Cart Summary",
                    "role": "region",
                }
            ],
        }
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to go to cart",
            conditions="1. Go to cart\n2. Verify cart",
            target_urls=["https://example.com/"],
        )
    )

    assert "page.goto('https://example.com/')" in final_code
    assert "page.locator('a[href=\"/view_cart\"]:visible').click()" in final_code
    assert "page.goto('https://example.com/view_cart')" in final_code
    assert "expect(page.locator('#cart-summary')).to_be_visible()" in final_code
    assert "#hero-summary" not in final_code


def test_run_pipeline_uses_semantic_ranker_for_ambiguous_assert_candidates() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page, expect

def test_01_verify_cart(page: Page):
    {{GOTO:cart page}}
    {{ASSERT:items added correctly}}
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/view_cart": [
                {
                    "selector": 'a[href="/view_cart"]',
                    "text": "Cart",
                    "role": "a",
                    "href": "https://example.com/view_cart",
                },
                {"selector": ".cart_description", "text": "Blue Top", "role": "div", "href": ""},
            ]
        }
    )
    orchestrator.semantic_ranker.choose_best_candidate = AsyncMock(  # type: ignore[method-assign]
        return_value={"selector": ".cart_description", "text": "Blue Top", "role": "div", "href": ""}
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to verify cart contents",
            conditions="1. Verify items in cart",
            target_urls=["https://example.com/view_cart"],
        )
    )

    assert "expect(page.locator('.cart_description')).to_be_visible()" in final_code


def test_run_pipeline_normalises_payable_type_to_page() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

class CheckoutPage:
    def __init__(self, page: Payable):
        self.page = page

def test_checkout(page: Page):
    checkout_page = CheckoutPage(page)
    checkout_page
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(return_value={})  # type: ignore[method-assign]

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to check out",
            conditions="1. Check out",
            target_urls=[],
        )
    )

    assert "page: Payable" not in final_code
    assert "page: Page" in final_code


def test_run_pipeline_normalises_unknown_page_parameter_type_to_page() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

class CheckoutPage:
    def __init__(self, page: Note):
        self.page = page

def test_01_checkout(page: Note):
    checkout_page = CheckoutPage(page)
    checkout_page
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(return_value={})  # type: ignore[method-assign]

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to check out",
            conditions="1. Check out",
            target_urls=[],
        )
    )

    assert "page: Note" not in final_code
    assert "def __init__(self, page: Page)" in final_code
    assert "def test_01_checkout(page: Page)" in final_code


def test_run_pipeline_injects_consent_helper_in_auto_dismiss_mode() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page, expect

def test_checkout(page: Page):
    page.goto("https://example.com/")
    {{CLICK:go to cart}}
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": [
                {
                    "selector": 'a[href="/view_cart"]',
                    "text": "Cart",
                    "role": "a",
                    "href": "https://example.com/view_cart",
                }
            ]
        }
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to go to cart",
            conditions="1. Go to cart",
            target_urls=["https://example.com/"],
            consent_mode="auto-dismiss",
        )
    )

    assert "def dismiss_consent_overlays(page: Page) -> None:" in final_code
    assert 'page.goto("https://example.com/")' in final_code
    assert "dismiss_consent_overlays(page)" in final_code
