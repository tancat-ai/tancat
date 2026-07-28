from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.home_page import HomePage
from pages.home_page import HomePage
from pages.products_page import ProductsPage
from pages.home_page import HomePage
from pages.cart_page import CartPage


@pytest.mark.evidence(condition_ref="AC-01", story_ref="US-001")
def test_01_navigate_home(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="AC-02", story_ref="US-001")
def test_02_click_products_link(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="AC-03", story_ref="US-001")
def test_03_add_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    products_page.click('Add to cart')
    evidence_tracker.assert_visible('.text-center', label='added confirmation')

@pytest.mark.evidence(condition_ref="AC-04", story_ref="US-001")
def test_04_verify_confirmation_message(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    products_page.click('Add to cart')
    evidence_tracker.assert_visible('.text-center', label='product added message')

@pytest.mark.evidence(condition_ref="AC-05", story_ref="US-001")
def test_05_click_cart_link(page: Page, evidence_tracker):
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

@pytest.mark.evidence(condition_ref="AC-06", story_ref="US-001")
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
    evidence_tracker.assert_visible('.cart_total_price', label='product name')
    evidence_tracker.assert_visible('.cart_total_price', label='product price')