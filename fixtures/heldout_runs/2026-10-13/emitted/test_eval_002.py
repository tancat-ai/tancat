from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/')
    expect(page).to_have_url("https://automationexercise.com/")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_products_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/')
    expect(page).to_have_url("https://automationexercise.com/products")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_blue_top_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.assert_visible('.modal-title.w-100', label='Blue Top added', expected_page='https://automationexercise.com/products')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_confirmation_message(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.assert_visible('#cartModal', label='product added to cart', expected_page='https://automationexercise.com/products')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_cart_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/')
    evidence_tracker.click('[data-product-id="11"]', label='Add to cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.click('a[href="/view_cart"]', label='Cart', expected_page='https://automationexercise.com/products')
    expect(page).to_have_url("https://automationexercise.com/view_cart")


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_cart_contents(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/')
    evidence_tracker.click('[data-product-id="11"]', label='Add to cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.click('a[href="/view_cart"]', label='Cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.assert_visible('h4:has-text("Blue Top")', label='Blue Top in cart', expected_page='https://automationexercise.com/view_cart')