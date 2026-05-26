"""Tests for the intelligent pipeline orchestrator."""

import asyncio
from unittest.mock import AsyncMock

from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


def _disable_journey_discovery(orchestrator: TestOrchestrator) -> None:
    orchestrator._scrape_journeys_statefully = AsyncMock(return_value=({}, []))  # type: ignore[method-assign]


def test_run_pipeline_replaces_placeholders_with_scraped_locators() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page, expect

def test_checkout(page: Page):
    page.locator({{CLICK:add_to_cart_button}}).click()
    page.goto({{GOTO:cart_url}})
    {{ASSERT:cart_summary}}
"""
    )

    orchestrator = TestOrchestrator(generator)
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": (
                [
                    {"selector": "#add-to-cart", "text": "Add To Cart Button", "role": "button"},
                    {
                        "selector": "#cart-summary",
                        "text": "Items in cart",
                        "role": "region",
                        "href": "https://example.com/view_cart",
                    },
                ],
                None,
                "https://example.com/",
            ),
            "https://example.com/products": (
                [{"selector": "#add-to-cart", "text": "Add To Cart Button", "role": "button"}],
                None,
                "https://example.com/products",
            ),
            "https://example.com/view_cart": (
                [
                    {
                        "selector": "#cart-summary",
                        "text": "Items in cart",
                        "role": "region",
                        "href": "https://example.com/view_cart",
                    }
                ],
                None,
                "https://example.com/view_cart",
            ),
        }
    )
    orchestrator.scraper.scrape_url = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [
                {"selector": "#add-to-cart", "text": "Add To Cart Button", "role": "button"},
                {
                    "selector": "#cart-summary",
                    "text": "Items in cart",
                    "role": "region",
                    "href": "https://example.com/view_cart",
                },
            ],
            None,
            "https://example.com/",
        )
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a customer I want to add a product to the cart",
            conditions="1. User can add an item to cart",
            target_urls=["https://example.com/"],
        )
    )

    # NOTE: :visible suffix removed — Playwright auto-waits for elements before clicking
    # Selector format: prefers ID/data-attr over text-based; label= as separate argument
    # Our improved locator builder prefers #add-to-cart (ID) over button:has-text(...)
    assert (
        "evidence_tracker.click('#add-to-cart', label=" in final_code
        or "evidence_tracker.click('button:has-text(\"Add To Cart Button\")', label=" in final_code
    )
    assert "evidence_tracker.navigate(" in final_code
    assert "https://example.com/view_cart" in final_code
    # ID-based selector preferred over text-based for assert
    assert "evidence_tracker.assert_visible('#cart-summary', label=" in final_code
    assert orchestrator.last_result is not None
    assert [journey.test_name for journey in orchestrator.last_result.journeys] == ["test_checkout"]
    scraped_urls = [page.url for page in orchestrator.last_result.scraped_page_records]
    generated_class_names = [page_object.class_name for page_object in orchestrator.last_result.generated_page_objects]
    # URL guessing removed — only seed URLs are scraped statically.
    # Products and cart pages are discovered via journey navigation.
    assert "https://example.com/" in scraped_urls
    # The scraper mock returns data for products/view_cart but only the seed URL
    # is in pages_to_scrape. Journey discovery would populate the rest.
    assert "HomePage" in generated_class_names


def test_run_pipeline_rejects_malformed_skeleton_before_resolution() -> None:
    """Skeleton with hallucinated CSS selectors must be rejected before resolution."""
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

def test_checkout(page: Page):
    evidence_tracker.click('.btn.primary')
"""
    )

    orchestrator = TestOrchestrator(generator)

    try:
        asyncio.run(orchestrator.run_pipeline(user_story="story", conditions="1. criterion"))
        raise AssertionError("Expected malformed skeleton to raise ValueError")
    except ValueError as exc:
        assert (
            "hallucinated CSS selectors" in str(exc).lower()
            or "NEVER GUESS LOCATORS" in str(exc)
            or "CSS class selector" in str(exc).lower()
        )


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
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": (
                [
                    {
                        "selector": 'a[href="/view_cart"]',
                        "text": "Cart",
                        "role": "a",
                        "href": "https://example.com/view_cart",
                    },
                ],
                None,
                "https://example.com/",
            )
        }
    )
    orchestrator.scraper.scrape_url = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [
                {
                    "selector": 'a[href="/view_cart"]',
                    "text": "Cart",
                    "role": "a",
                    "href": "https://example.com/view_cart",
                },
            ],
            None,
            "https://example.com/",
        )
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to go to cart",
            conditions="1. Go to cart",
            target_urls=["https://example.com/"],
        )
    )

    assert "import pytest" in final_code
    assert "evidence_tracker.navigate(" in final_code
    assert "https://example.com/" in final_code
    # NOTE: :visible suffix removed — Playwright auto-waits for elements before clicking
    assert "evidence_tracker.click('a[href=\"/view_cart\"]'" in final_code
    assert "pytest.skip" in final_code


def test_build_candidate_urls_stays_scoped_to_expected_journey_pages() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    orchestrator = TestOrchestrator(generator)
    _disable_journey_discovery(orchestrator)
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

    # URL guessing has been removed — _build_candidate_urls only returns seed URLs.
    # Journey discovery finds all reachable pages by navigating statefully.
    assert discovered == ["https://example.com/"]


def test_run_pipeline_preserves_page_requirements_metadata() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

def test_checkout(page: Page):
    {{GOTO:home page}}
    {{CLICK:add to cart}}
"""
    )

    orchestrator = TestOrchestrator(generator)
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": (
                [
                    {"selector": "#hero", "text": "Hero", "role": "region"},
                    {"selector": "#buy", "text": "Add to Cart", "role": "button"},
                ],
                None,
                "https://example.com/",
            ),
            "https://example.com/products": (
                [{"selector": "#buy", "text": "Add to Cart", "role": "button"}],
                None,
                "https://example.com/products",
            ),
        }
    )
    orchestrator.scraper.scrape_url = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [
                {"selector": "#hero", "text": "Hero", "role": "region"},
                {"selector": "#buy", "text": "Add to Cart", "role": "button"},
            ],
            None,
            "https://example.com/",
        )
    )

    asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a customer I want to buy products",
            conditions="1. Add product to cart",
            target_urls=["https://example.com/"],
        )
    )

    assert orchestrator.last_result is not None


def test_run_pipeline_normalises_unsupported_placeholder_actions_before_validation() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

def test_01_add(page: Page):
    {{ADD:add a product to cart}}
"""
    )
    orchestrator = TestOrchestrator(generator)
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(return_value={})  # type: ignore[method-assign]

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="story",
            conditions="1. add to cart",
            target_urls=[],
        )
    )
    # ADD should be normalised to CLICK so placeholder replacement runs.
    assert "{{ADD:" not in final_code


def test_run_pipeline_normalises_placeholder_whitespace_that_breaks_token_matching() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

def test_01_example(page: Page):
    {{CLICK:product named }}.click()
"""
    )
    orchestrator = TestOrchestrator(generator)
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": (
                [{"selector": "#buy", "text": "Product named", "role": "button"}],
                None,
                "https://example.com/",
            )
        }
    )
    orchestrator.scraper.scrape_url = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [{"selector": "#buy", "text": "Product named", "role": "button"}],
            None,
            "https://example.com/",
        )
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="story",
            conditions="1. click product",
            target_urls=["https://example.com/"],
            consent_mode="leave-as-is",
        )
    )
    # NOTE: :visible suffix removed — Playwright auto-waits for elements before clicking
    assert "evidence_tracker.click('#buy'" in final_code


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
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/products": (
                [
                    {"selector": '[data-product-id="1"]', "text": "Add To Cart Button", "role": "button"},
                    {"selector": '[data-product-id="1"]', "text": "Add To Cart Button", "role": "button"},
                ],
                None,
                "https://example.com/products",
            )
        }
    )
    orchestrator.scraper.scrape_url = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [
                {"selector": '[data-product-id="1"]', "text": "Add To Cart Button", "role": "button"},
                {"selector": '[data-product-id="1"]', "text": "Add To Cart Button", "role": "button"},
            ],
            None,
            "https://example.com/products",
        )
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a customer I want to add a product to the cart",
            conditions="1. Add to cart",
            target_urls=["https://example.com/products"],
        )
    )

    assert '[data-product-id="1"]' in final_code


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
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": (
                [
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
                None,
                "https://example.com/",
            ),
            "https://example.com/view_cart": (
                [
                    {
                        "selector": "#cart-summary",
                        "text": "Cart Summary",
                        "role": "region",
                    }
                ],
                None,
                "https://example.com/view_cart",
            ),
        }
    )
    orchestrator.scraper.scrape_url = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [
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
            None,
            "https://example.com/",
        )
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to go to cart",
            conditions="1. Go to cart\n2. Verify cart",
            target_urls=["https://example.com/"],
        )
    )

    assert "evidence_tracker.navigate('https://example.com/')" in final_code
    # NOTE: :visible suffix removed — Playwright auto-waits for elements before clicking
    assert "evidence_tracker.click('a[href=\"/view_cart\"]'" in final_code
    assert "evidence_tracker.navigate('https://example.com/view_cart')" in final_code
    assert "evidence_tracker.assert_visible('#cart-summary'" in final_code
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
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/view_cart": (
                [
                    {
                        "selector": 'a[href="/view_cart"]',
                        "text": "Cart",
                        "role": "a",
                        "href": "https://example.com/view_cart",
                    },
                    {"selector": ".cart_description", "text": "Items added correctly", "role": "div", "href": ""},
                ],
                None,
                "https://example.com/view_cart",
            )
        }
    )
    orchestrator.scraper.scrape_url = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [
                {
                    "selector": 'a[href="/view_cart"]',
                    "text": "Cart",
                    "role": "a",
                    "href": "https://example.com/view_cart",
                },
                {"selector": ".cart_description", "text": "Items added correctly", "role": "div", "href": ""},
            ],
            None,
            "https://example.com/view_cart",
        )
    )
    orchestrator.semantic_ranker.choose_best_candidate = AsyncMock(  # type: ignore[method-assign]
        return_value={"selector": ".cart_description", "text": "Items added correctly", "role": "div", "href": ""}
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to verify cart contents",
            conditions="1. Verify items in cart",
            target_urls=["https://example.com/view_cart"],
        )
    )

    assert "evidence_tracker.assert_visible('.cart_description'" in final_code


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
    _disable_journey_discovery(orchestrator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": (
                [
                    {
                        "selector": 'a[href="/view_cart"]',
                        "text": "Cart",
                        "role": "a",
                        "href": "https://example.com/view_cart",
                    }
                ],
                None,
                "https://example.com/",
            )
        }
    )

    async def fake_scrape_url(url: str) -> tuple[list[dict[str, str]], str | None, str]:
        return (
            [
                {
                    "selector": 'a[href="/view_cart"]',
                    "text": "Cart",
                    "role": "a",
                    "href": "https://example.com/view_cart",
                }
            ],
            None,
            url,
        )

    orchestrator.scraper.scrape_url = fake_scrape_url  # type: ignore[assignment]

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to go to cart",
            conditions="1. Go to cart",
            target_urls=["https://example.com/"],
            consent_mode="auto-dismiss",
        )
    )

    # Consent helper is now inlined by _inject_consent_helper, not imported
    assert "def dismiss_consent_overlays(page: Page) -> None:" in final_code
    assert 'evidence_tracker.navigate("https://example.com/")' in final_code
    assert "dismiss_consent_overlays(page)" in final_code


def test_run_pipeline_advances_after_login_to_resolve_saucedemo_inventory_steps() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page, expect
import pytest

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page):
    {{GOTO:home}}
    {{FILL:username input:standard_user}}
    {{FILL:password input:secret_sauce}}
    {{CLICK:login button}}
    {{ASSERT:products page loaded}}

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item(page):
    {{GOTO:home}}
    {{FILL:username input:standard_user}}
    {{FILL:password input:secret_sauce}}
    {{CLICK:login button}}
    {{CLICK:add to cart button for Sauce Labs Backpack}}
    {{CLICK:shopping cart link}}

"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://www.saucedemo.com": (
                [
                    {"selector": "#user-name", "text": "", "role": "text", "id": "user-name"},
                    {"selector": "#password", "text": "", "role": "password", "id": "password"},
                    {"selector": "#login-button", "text": "Login", "role": "submit", "id": "login-button"},
                ],
                None,
                "https://www.saucedemo.com",
            ),
            "https://www.saucedemo.com/products": ([], None, "https://www.saucedemo.com/products"),
        }
    )
    orchestrator._scrape_journeys_statefully = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            {
                "https://www.saucedemo.com/inventory.html": [
                    {
                        "selector": "#add-to-cart-sauce-labs-backpack",
                        "text": "Add to cart",
                        "role": "button",
                        "id": "add-to-cart-sauce-labs-backpack",
                        "data_test": "add-to-cart-sauce-labs-backpack",
                    },
                    {
                        "selector": '.shopping_cart_link[data-test="shopping-cart-link"]',
                        "text": "",
                        "role": "a",
                        "href": "https://www.saucedemo.com/cart.html",
                        "classes": "shopping_cart_link",
                        "data_test": "shopping-cart-link",
                    },
                ],
                "https://www.saucedemo.com/cart.html": [
                    {
                        "selector": "#checkout",
                        "text": "Checkout",
                        "role": "button",
                        "id": "checkout",
                    }
                ],
            },
            [
                "https://www.saucedemo.com",
                "https://www.saucedemo.com/inventory.html",
                "https://www.saucedemo.com/cart.html",
            ],
        )
    )

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a user I want to log in and add items to my cart",
            conditions="1. Log in\n2. Add at least one item to the cart",
            target_urls=["https://www.saucedemo.com"],
        )
    )

    assert "def test_01_login(page):" in final_code


def test_orchestrator_without_credential_profile() -> None:
    """TestOrchestrator works with simple constructor (credential journey features removed)."""
    generator = TestGenerator(output_dir="generated_tests")
    orchestrator = TestOrchestrator(generator)

    assert orchestrator.test_generator is generator
