import pytest
from playwright.sync_api import Page, expect
from pages.home_page import HomePage
from pages.home_page import HomePage
from pages.products_page import ProductsPage
from pages.home_page import HomePage
from pages.cart_page import CartPage


@pytest.mark.evidence(condition_ref="AC-1", story_ref="US-01")
def test_01_navigate_home(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="AC-2", story_ref="US-01")
def test_02_navigate_products(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="AC-3", story_ref="US-01")
def test_03_add_product_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    products_page.click('Add to cart')
    evidence_tracker.assert_visible('[data-product-id="11"]', label='cart modal')

@pytest.mark.evidence(condition_ref="AC-4", story_ref="US-01")
def test_04_verify_added_message(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    products_page.click('Add to cart')
    evidence_tracker.assert_visible('.text-center', label='Added confirmation')

@pytest.mark.evidence(condition_ref="AC-5", story_ref="US-01")
def test_05_navigate_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    products_page.click('Add to cart')
    products_page.click('Cart')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="AC-6", story_ref="US-01")
def test_06_verify_cart_contents(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    products_page.click('Add to cart')
    products_page.click('Cart')
    evidence_tracker.assert_visible('.cart_total_price', label='product name and price')