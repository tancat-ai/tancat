from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    # Page arrival check: expected 'http://localhost:8781/index.html', browser observed on 'http://localhost:8781/index.html'
    evidence_tracker.record_page_expectation(expected_url='http://localhost:8781/index.html', observed_url='http://localhost:8781/index.html', trail_step="index=1; action=scrape; description='home page loaded'; from_url='http://localhost:8781/index.html'; to_url='http://localhost:8781/index.html'; navigated=False; timestamp=1793749440.4900289", producer='keyword', description='home page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("http://localhost:8781/index.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_blue_top(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('h2.modal-title.w-100', label='Blue Top added', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_confirmation(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('p.text-center', label='confirmation message', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_go_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html', must_move=True)
    # Page arrival check: expected 'http://localhost:8781/cart.html', browser observed on 'http://localhost:8781/cart.html'
    evidence_tracker.record_page_expectation(expected_url='http://localhost:8781/cart.html', observed_url='http://localhost:8781/cart.html', trail_step="index=3; action=scrape; description='cart page loaded'; from_url='http://localhost:8781/cart.html'; to_url='http://localhost:8781/cart.html'; navigated=False; timestamp=1793749449.7078538", producer='keyword', description='cart page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("http://localhost:8781/cart.html")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_cart_contents(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html', must_move=True)
    evidence_tracker.assert_visible('h4.cart_description', label='Blue Top in cart', expected_page='http://localhost:8781/cart.html')
    evidence_tracker.assert_section_has_price('visible', label='price visible')


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html', must_move=True)
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout', expected_page='http://localhost:8781/cart.html', must_move=True)
    # Page arrival check: expected 'http://localhost:8781/checkout.html', browser observed on 'http://localhost:8781/checkout.html'
    evidence_tracker.record_page_expectation(expected_url='http://localhost:8781/checkout.html', observed_url='http://localhost:8781/checkout.html', trail_step="index=4; action=scrape; description='checkout page loaded'; from_url='http://localhost:8781/checkout.html'; to_url='http://localhost:8781/checkout.html'; navigated=False; timestamp=1793749454.2250876", producer='keyword', description='checkout page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("http://localhost:8781/checkout.html")


@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_fill_checkout_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html', must_move=True)
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout', expected_page='http://localhost:8781/cart.html', must_move=True)
    evidence_tracker.fill('#name', 'John Doe', label='name', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#email', 'john@example.com', label='email', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#address', '123 Main St', label='address', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#city', 'Springfield', label='city', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#zip', '12345', label='zip', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#card-number', '4242424242424242', label='card number', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#expiry', '12/25', label='expiry', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#cvv', '123', label='cvc', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.click('#place-order', label='Place Order', expected_page='http://localhost:8781/checkout.html')


@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_verify_order_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html', must_move=True)
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout', expected_page='http://localhost:8781/cart.html', must_move=True)
    evidence_tracker.fill('#name', 'John Doe', label='name', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#email', 'john@example.com', label='email', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#address', '123 Main St', label='address', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#city', 'Springfield', label='city', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#zip', '12345', label='zip', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#card-number', '4242424242424242', label='card number', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#expiry', '12/25', label='expiry', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.fill('#cvv', '123', label='cvc', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.click('#place-order', label='Place Order', expected_page='http://localhost:8781/checkout.html')
    evidence_tracker.assert_visible('#place-order', label='order success message', expected_page='http://localhost:8781/checkout.html')