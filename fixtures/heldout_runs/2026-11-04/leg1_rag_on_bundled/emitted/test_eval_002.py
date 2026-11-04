from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/', expected_page='https://automationexercise.com/')
    # Page arrival check: expected 'https://automationexercise.com/', browser observed on 'https://automationexercise.com/'
    evidence_tracker.record_page_expectation(expected_url='https://automationexercise.com/', observed_url='https://automationexercise.com/', trail_step="index=1; action=scrape; description='home page loaded'; from_url='https://automationexercise.com/'; to_url='https://automationexercise.com/'; navigated=False; timestamp=1793746248.0524812", producer='keyword', description='home page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://automationexercise.com/")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_products_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/', expected_page='https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/', must_move=True)
    # Page arrival check: expected 'https://automationexercise.com/products', browser observed on 'https://automationexercise.com/products'
    evidence_tracker.record_page_expectation(expected_url='https://automationexercise.com/products', observed_url='https://automationexercise.com/products', trail_step="index=2; action=scrape; description='products page loaded'; from_url='https://automationexercise.com/products'; to_url='https://automationexercise.com/products'; navigated=False; timestamp=1793746254.8407636", producer='keyword', description='products page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://automationexercise.com/products")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_blue_top_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/', expected_page='https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/', must_move=True)
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.assert_visible('p.text-center', label='Blue Top added', expected_page='https://automationexercise.com/products')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_confirmation_message(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/', expected_page='https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/', must_move=True)
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.assert_visible('.add-to-cart.btn[data-product-id="11"]', label='product added to cart', expected_page='https://automationexercise.com/products')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_cart_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/', expected_page='https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/', must_move=True)
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.click('a[href="/view_cart"]', label='Cart', expected_page='https://automationexercise.com/products', must_move=True)
    # Page arrival check: expected 'https://automationexercise.com/view_cart', browser observed on 'https://automationexercise.com/view_cart'
    evidence_tracker.record_page_expectation(expected_url='https://automationexercise.com/view_cart', observed_url='https://automationexercise.com/view_cart', trail_step="index=4; action=scrape; description='cart page loaded'; from_url='https://automationexercise.com/view_cart'; to_url='https://automationexercise.com/view_cart'; navigated=False; timestamp=1793746267.4018364", producer='keyword', description='cart page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://automationexercise.com/view_cart")


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_cart_contents(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/', expected_page='https://automationexercise.com/')
    evidence_tracker.click('a[href="/products"]', label='Products', expected_page='https://automationexercise.com/', must_move=True)
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='https://automationexercise.com/products')
    evidence_tracker.click('a[href="/view_cart"]', label='Cart', expected_page='https://automationexercise.com/products', must_move=True)
    evidence_tracker.assert_visible('a[href="/product_details/1"]', label='Blue Top in cart', expected_page='https://automationexercise.com/view_cart')