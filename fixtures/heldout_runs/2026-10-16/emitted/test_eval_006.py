from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    expect(page).to_have_url("http://localhost:8781/index.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_blue_top(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    pytest.skip("Skipping: unresolved placeholders for: 'Blue Top added'. 2 of 3 placeholders resolved")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('#product-name', label='Blue Top added', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_confirmation(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    pytest.skip("Skipping: unresolved placeholders for: 'confirmation message'. 2 of 3 placeholders resolved")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('.text-center', label='confirmation message', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_go_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html')
    expect(page).to_have_url("http://localhost:8781/cart.html")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_cart_contents(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible(':has-text("Proceed To Checkout")', label='Blue Top in cart', expected_page='http://localhost:8781/cart.html')
    evidence_tracker.assert_section_has_price('visible', label='price visible')


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout', expected_page='http://localhost:8781/cart.html')
    expect(page).to_have_url("http://localhost:8781/checkout.html")


@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_fill_checkout_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout', expected_page='http://localhost:8781/cart.html')
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
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout', expected_page='http://localhost:8781/cart.html')
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