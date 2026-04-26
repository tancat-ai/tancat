"""Tests for the intelligent pipeline orchestrator."""

import ast
import asyncio
from unittest.mock import AsyncMock

from src.code_postprocessor import (
    normalise_generated_code,
    replace_remaining_placeholders,
    replace_token_in_line,
)
from src.orchestrator import TestOrchestrator
from src.spec_analyzer import TestCondition
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

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a customer I want to add a product to the cart",
            conditions="1. User can add an item to cart",
            target_urls=["https://example.com/"],
        )
    )

    # NOTE: :visible suffix removed — Playwright auto-waits for elements before clicking
    assert "evidence_tracker.click('#add-to-cart'" in final_code
    assert "evidence_tracker.navigate(" in final_code
    assert "https://example.com/view_cart" in final_code
    assert "evidence_tracker.assert_visible('#cart-summary'" in final_code
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
        return [], None, url

    orchestrator.scraper.scrape_url = fake_scrape_url  # type: ignore[assignment]

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
            "https://example.com/": (
                [{"selector": "#hero", "text": "Hero", "role": "region"}],
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
        return_value={
            "https://example.com/": (
                [{"selector": "#cart", "text": "Cart", "role": "button"}],
                None,
                "https://example.com/",
            )
        }
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


def test_run_pipeline_generates_one_fragment_per_reviewed_condition_and_combines_results() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.client.generate = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            """
from playwright.sync_api import Page, expect
import pytest

@pytest.mark.evidence(condition_ref="TC01.01", story_ref="S01")
def test_01_add_to_cart(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("{{GOTO:home page}}")
    evidence_tracker.click({{CLICK:add to cart button}}, label="add to cart")

# PAGES_NEEDED:
# - https://example.com/ (home)
""",
            """
from playwright.sync_api import Page, expect
import pytest

@pytest.mark.evidence(condition_ref="TC01.02", story_ref="S01")
def test_02_go_to_cart(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("{{GOTO:home page}}")
    evidence_tracker.click({{CLICK:cart link}}, label="cart")

# PAGES_NEEDED:
# - https://example.com/view_cart (cart)
""",
        ]
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": (
                [{"selector": "#buy", "text": "Add to cart", "role": "button"}],
                None,
                "https://example.com/",
            ),
            "https://example.com/view_cart": (
                [{"selector": "#cart-link", "text": "Cart", "role": "a", "href": "https://example.com/view_cart"}],
                None,
                "https://example.com/view_cart",
            ),
        }
    )
    reviewed_conditions = [
        TestCondition(
            id="TC01.01",
            type="happy_path",
            text="add items to cart",
            expected="Meets acceptance criteria.",
            source="Acceptance Criteria 1",
            flagged=False,
            src="manual",
            intent="element_behavior",
        ),
        TestCondition(
            id="TC01.02",
            type="happy_path",
            text="go to cart",
            expected="Meets acceptance criteria.",
            source="Acceptance Criteria 2",
            flagged=False,
            src="manual",
            intent="journey_step",
        ),
    ]

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to add to cart and go to cart",
            conditions=(
                "1. [TC01.01] add items to cart -> Expected: Meets acceptance criteria.\n"
                "2. [TC01.02] go to cart -> Expected: Meets acceptance criteria."
            ),
            target_urls=["https://example.com/"],
            reviewed_conditions=reviewed_conditions,
        )
    )

    assert generator.client.generate.await_count == 2  # type: ignore[attr-defined]
    assert "def test_01_add_to_cart" in orchestrator.last_result.skeleton_code  # type: ignore[union-attr]
    assert "def test_02_go_to_cart" in orchestrator.last_result.skeleton_code  # type: ignore[union-attr]
    assert orchestrator.last_result is not None
    assert [journey.test_name for journey in orchestrator.last_result.journeys] == [
        "test_01_add_to_cart",
        "test_02_go_to_cart",
    ]
    assert "https://example.com/view_cart" in final_code


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
    orchestrator.scraper.scrape_all = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "https://example.com/": (
                [{"selector": "#buy", "text": "Buy", "role": "button"}],
                None,
                "https://example.com/",
            )
        }
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

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a customer I want to add a product to the cart",
            conditions="1. Add to cart",
            target_urls=["https://example.com/products"],
        )
    )

    # NOTE: :visible suffix removed — Playwright auto-waits for elements before clicking
    assert "evidence_tracker.click('[data-product-id=\"1\"]'" in final_code


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
                    {"selector": ".cart_description", "text": "Blue Top", "role": "div", "href": ""},
                ],
                None,
                "https://example.com/view_cart",
            )
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

    assert "evidence_tracker.assert_visible('.cart_description'" in final_code


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
        return [], None, url

    orchestrator.scraper.scrape_url = fake_scrape_url  # type: ignore[assignment]

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to go to cart",
            conditions="1. Go to cart",
            target_urls=["https://example.com/"],
            consent_mode="auto-dismiss",
        )
    )

    assert "def dismiss_consent_overlays(page: Page) -> None:" in final_code
    assert 'evidence_tracker.navigate("https://example.com/")' in final_code
    assert "dismiss_consent_overlays(page)" in final_code


def test_normalise_generated_code_strips_invalid_pytest_mark_assignment() -> None:
    broken = """
import pytest
from playwright.sync_api import Page

@pytest.markelse = None # Placeholder to keep structure clean
@pytest.mark.evidence(condition_ref="TC01.01", story_ref="S1")
def test_01_ok(page: Page, evidence_tracker) -> None:
    pass
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "@pytest.markelse" not in fixed
    assert "@pytest.mark.evidence" in fixed


def test_normalise_generated_code_repairs_hallucinated_page_object_constructor_and_callsite() -> None:
    broken = """
from playwright.sync_api import Page, expect

def dismiss_consent_overlays(page: Page) -> None:
    pass

class CartPage:
    def __larry(self, page: Page):
        self.page = page

    def go(self) -> None:
        dismiss_consent_overlays(page)
        page.goto("https://example.com/")

def test_01_checkout(page: Page):
    cart = CartPage(project=page) # Note: using placeholder logic
    cart.go()
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "def __init__(self, page: Page) -> None:" in fixed
    assert "CartPage(page)" in fixed
    assert "dismiss_consent_overlays(self.page)" in fixed
    assert 'evidence_tracker.navigate("https://example.com/")' in fixed


def test_normalise_generated_code_rewrites_hallucinated_evidence_launcher_fixture() -> None:
    broken = """
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC01.01", story_ref="S1")
def test_01_ok(page: Page, evidence_launcher) -> None:
    evidence_launcher.step("hello")
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "evidence_launcher" not in fixed
    assert "evidence_tracker" in fixed


def test_normalise_generated_code_repairs_pytest_mark_slash_typo() -> None:
    broken = """
import pytest

@pytest.mark/evidence(condition_ref="TC01.01", story_ref="S1")
def test_01_ok() -> None:
    assert True
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "@pytest.mark/evidence" not in fixed
    assert "@pytest.mark.evidence" in fixed


def test_normalise_generated_code_rewrites_consent_helper_page_reference_in_page_objects() -> None:
    broken = """
from playwright.sync_api import Page

def dismiss_consent_overlays(page: Page) -> None:
    pass

class ProductPage:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, evidence_tracker) -> None:
        evidence_tracker.navigate("https://example.com/")
        dismiss_consent_overlays(page)
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "dismiss_consent_overlays(self.page)" in fixed


def test_normalise_generated_code_dedents_top_level_test_block_after_helper() -> None:
    broken = """
import pytest
from playwright.sync_api import Page

def dismiss_consent_overlays(page: Page) -> None:
    pass

     @pytest.mark.evidence(condition_ref="TC01.01", story_ref="S01")
     def test_01_ok(page: Page, evidence_tracker) -> None:
         evidence_tracker.navigate("https://example.com/")
         assert True

     # PAGES_NEEDED:
     # - https://example.com/
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "\n@pytest.mark.evidence" in fixed
    assert "\n     @pytest.mark.evidence" not in fixed
    assert "\ndef test_01_ok" in fixed


def test_normalise_generated_code_injects_playwright_import_when_page_annotations_exist() -> None:
    broken = """
def test_01_ok(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("https://example.com/")
"""
    fixed = normalise_generated_code(broken, consent_mode="auto-dismiss")
    assert "from playwright.sync_api import Page, expect" in fixed
    assert "def dismiss_consent_overlays(page: Page) -> None:" in fixed


def test_replace_token_in_line_uses_description_for_label_not_token() -> None:
    """Ensure evidence labels use the plain description, not the bracketed token."""
    line = "evidence_tracker.click('{{CLICK:basket}}')"

    fixed = replace_token_in_line(
        line=line,
        action="CLICK",
        token="{{CLICK:basket}}",
        resolved_value="'#cart-btn'",
        duplicate_selectors=set(),
        description="shopping basket",
    )

    assert "label='shopping basket'" in fixed
    assert "{{CLICK:basket}}" not in fixed


def test_replace_remaining_placeholders_ignores_placeholders_inside_quotes() -> None:
    """The safety net must not corrupt labels that already contain placeholders."""
    code = "evidence_tracker.click('#id', label='{{CLICK:basket}}')"
    fixed = replace_remaining_placeholders(code)

    # It should NOT be wrapped in pytest.skip() because it's inside quotes
    assert fixed == code
    assert "pytest.skip" not in fixed


def test_replace_token_in_line_with_skip_replaces_whole_line() -> None:
    """Unresolved steps should become standalone skips, not invalid parameter injections."""
    line = "    evidence_tracker.click('{{CLICK:missing}}')"

    fixed = replace_token_in_line(
        line=line,
        action="CLICK",
        token="{{CLICK:missing}}",
        resolved_value='pytest.skip("not found")',
        duplicate_selectors=set(),
        description="missing button",
    )

    assert fixed.strip() == 'pytest.skip("not found")'
    assert "evidence_tracker.click" not in fixed


def test_replace_token_in_line_goto_replaces_quoted_placeholder_without_double_quotes() -> None:
    line = '    evidence_tracker.navigate("{{GOTO:products page}}")'

    fixed = replace_token_in_line(
        line=line,
        action="GOTO",
        token="{{GOTO:products page}}",
        resolved_value="'https://example.com/products'",
        duplicate_selectors=set(),
        description="products page",
    )

    assert fixed.strip() == "evidence_tracker.navigate('https://example.com/products')"


def test_replace_remaining_placeholders_converts_raw_placeholder_to_skip() -> None:
    """Unresolved {{...}} placeholders (e.g. those with Python variable syntax) must be
    replaced with pytest.skip() so they never produce a SyntaxError."""
    code_with_unresolved = """\
def test_something(page, evidence_tracker):
    {{ASSERT:item {item_name} is present in cart}}
    {{CLICK:add to cart button}}
"""
    fixed = replace_remaining_placeholders(code_with_unresolved)
    assert "pytest.skip(" in fixed
    # Confirm no line starts with a raw placeholder (which would be invalid Python syntax)
    for line in fixed.splitlines():
        assert not line.lstrip().startswith("{{"), f"Raw placeholder still present: {line!r}"
    # Indentation must be preserved
    for line in fixed.splitlines():
        if "pytest.skip" in line:
            assert line.startswith("    "), f"Expected indented skip, got: {line!r}"


def test_replace_remaining_placeholders_replaces_function_call_line_with_valid_skip() -> None:
    """Unresolved placeholders inside function calls must become valid standalone skips."""
    code_with_unresolved = """\
import pytest

def test_checkout(page, evidence_tracker):
    evidence_tracker.fill({{FILL:email}}, '', label="email")
    """
    fixed = replace_remaining_placeholders(code_with_unresolved)
    assert "evidence_tracker.fill(" not in fixed
    assert "Unresolved placeholder in this step." in fixed
    assert "pytest.skip(" in fixed
    ast.parse(fixed)


def test_skeleton_validator_rejects_python_variable_syntax_in_placeholder() -> None:
    """Reject skeleton code where a placeholder description contains Python variable
    syntax like {item_name} — the resolver regex can't match those tokens."""
    from src.skeleton_parser import SkeletonParser

    bad_skeleton = """\
import pytest
from playwright.sync_api import Page

# PAGES_NEEDED:
# https://example.com/

def test_01(page: Page, evidence_tracker) -> None:
    {{ASSERT:item {item_name} is present in cart}}
"""
    parser = SkeletonParser()
    error = parser.validate_skeleton(bad_skeleton)
    assert error is not None
    assert "Python variable syntax" in error
