"""Unit tests for POM helper deduplication (LLM skeleton POM-block fix)."""

from __future__ import annotations

from src.pom_helpers import deduplicate_pom_lines

DUPLICATED = '''"""Docstring"""

from playwright.sync_api import Page, expect
import pytest
from pages.home_page import HomePage
from pages.basket_page import BasketPage
from pages.cart_page import CartPage
from pages.checkout_page import CheckoutPage
from pages.home_page import HomePage
from pages.products_page import ProductsPage
from pages.cart_page import CartPage
from pages.home_page import HomePage
from pages.generated_page import GeneratedPage
from pages.generated_page import GeneratedPage


from pages.home_page import HomePage
from pages.basket_page import BasketPage
from pages.cart_page import CartPage
from pages.checkout_page import CheckoutPage
from pages.products_page import ProductsPage
from pages.generated_page import GeneratedPage
@pytest.mark.evidence(condition_ref="T01", story_ref="S01")
def test_t01(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    basket_page = BasketPage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    checkout_page = CheckoutPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    generated_page = GeneratedPage(page, evidence_tracker)
    generated_page = GeneratedPage(page, evidence_tracker)
    evidence_tracker.navigate('https://example.com/')
'''

CLEAN = '''"""Docstring"""

from playwright.sync_api import Page, expect
import pytest
from pages.home_page import HomePage
from pages.basket_page import BasketPage
from pages.cart_page import CartPage
from pages.checkout_page import CheckoutPage
from pages.products_page import ProductsPage
from pages.generated_page import GeneratedPage


@pytest.mark.evidence(condition_ref="T01", story_ref="S01")
def test_t01(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    basket_page = BasketPage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    checkout_page = CheckoutPage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    generated_page = GeneratedPage(page, evidence_tracker)
    evidence_tracker.navigate('https://example.com/')
'''


def test_deduplicates_imports_and_instantiations() -> None:
    result = deduplicate_pom_lines(DUPLICATED)
    # Imports: exactly one of each page import, no double blank-block
    assert result.count("from pages.home_page import HomePage") == 1
    assert result.count("from pages.cart_page import CartPage") == 1
    assert result.count("from pages.generated_page import GeneratedPage") == 1
    # Instantiations: one per instance variable inside the function
    assert result.count("home_page = HomePage(page, evidence_tracker)") == 1
    assert result.count("cart_page = CartPage(page, evidence_tracker)") == 1
    assert result.count("generated_page = GeneratedPage(page, evidence_tracker)") == 1
    assert result == CLEAN.rstrip("\n")


def test_clean_input_unchanged() -> None:
    assert deduplicate_pom_lines(CLEAN.rstrip("\n")) == CLEAN.rstrip("\n")


def test_legacy_mode_instantiations() -> None:
    code = (
        "def test_a(page):\n    home_page = HomePage(page)\n    home_page = HomePage(page)\n    home_page.click('x')\n"
    )
    result = deduplicate_pom_lines(code)
    assert result.count("home_page = HomePage(page)") == 1


def test_instantiations_deduped_per_function() -> None:
    code = (
        "def test_a(page, evidence_tracker):\n"
        "    home_page = HomePage(page, evidence_tracker)\n"
        "    home_page = HomePage(page, evidence_tracker)\n"
        "\n"
        "def test_b(page, evidence_tracker):\n"
        "    home_page = HomePage(page, evidence_tracker)\n"
    )
    result = deduplicate_pom_lines(code)
    # each function keeps its own single instantiation
    assert result.count("home_page = HomePage(page, evidence_tracker)") == 2


def test_non_pom_assignments_untouched() -> None:
    code = (
        "def test_a(page):\n"
        "    status = check_status(page)\n"
        "    status = check_status(page)\n"
        "    item = page.locator('#x')\n"
    )
    result = deduplicate_pom_lines(code)
    assert result.count("status = check_status(page)") == 2
    assert result.count("item = page.locator('#x')") == 1
