from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.home_page import HomePage
from pages.home_page import HomePage
from pages.cart_page import CartPage
from pages.products_page import ProductsPage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_Navigate_to_automationexercise_com_home_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_Click_the_Products_link_in_the_header_navigation_to_go_to_the_products_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")
    evidence_tracker.click('a[href="/products"]', label='Products link in the header navigation')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_Click_the_Add_to_cart_button_next_to_a_product_(page: Page, e_g_Blue_Top, evidence_tracker)(page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")
    evidence_tracker.click('a[href="/products"]', label='Products link in the header navigation')
    expect(page).to_have_url("https://automationexercise.com")
    products_page.click('Add to cart button next to Blue Top')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_Verify_a_confirmation_message_appears_indicating_the_product_was_added_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")
    evidence_tracker.click('a[href="/products"]', label='Products link in the header navigation')
    expect(page).to_have_url("https://automationexercise.com")
    products_page.click('Add to cart button next to Blue Top')
    evidence_tracker.assert_visible('.text-center', label='a confirmation message appears indicating the product was added to cart')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_Click_the_Cart_link_in_the_header_navigation_to_go_to_the_cart_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")
    evidence_tracker.click('a[href="/products"]', label='Products link in the header navigation')
    expect(page).to_have_url("https://automationexercise.com")
    products_page.click('Add to cart button next to Blue Top')
    evidence_tracker.assert_visible('.text-center', label='a confirmation message appears indicating the product was added to cart')
    products_page.click('Cart link in the header navigation')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_Verify_the_cart_page_displays_the_product_that_was_added_with_its_name_and_price(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    products_page = ProductsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")
    evidence_tracker.click('a[href="/products"]', label='Products link in the header navigation')
    expect(page).to_have_url("https://automationexercise.com")
    products_page.click('Add to cart button next to Blue Top')
    evidence_tracker.assert_visible('.text-center', label='a confirmation message appears indicating the product was added to cart')
    products_page.click('Cart link in the header navigation')
    expect(page).to_have_url("https://automationexercise.com")
    evidence_tracker.assert_visible('.text-center', label='cart page displays the product that was added with its name and price')