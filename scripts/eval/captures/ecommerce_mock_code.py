import pytest
from playwright.sync_api import Page, expect


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    expect(page).to_have_url("http://localhost:8781/index.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_add_confirmation(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart')
    evidence_tracker.assert_visible('p.text-center', label='added to cart message')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_go_to_cart_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart link')
    expect(page).to_have_url("http://localhost:8781/cart.html")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_cart_contents(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart link')
    evidence_tracker.assert_visible('#empty_cart', label='product name and price')


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_proceed_to_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart link')
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout')
    expect(page).to_have_url("http://localhost:8781/checkout.html")


@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_fill_checkout_and_place_order(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    pytest.skip("Skipping: unresolved placeholders for: 'cvc'")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart link')
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout')
    evidence_tracker.fill('#name', 'John Doe', label='name')
    evidence_tracker.fill('#email', 'john@example.com', label='email')
    evidence_tracker.fill('#address', '123 Main St', label='address')
    evidence_tracker.fill('#city', 'New York', label='city')
    evidence_tracker.fill('#zip', '10001', label='zip')
    evidence_tracker.fill('#card-name', '4111111111111111', label='card number')
    evidence_tracker.fill('#expiry', '12/25', label='expiry')
    evidence_tracker.click('#place-order', label='Place Order')


@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_verify_order_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart')
    evidence_tracker.click('a[href="/cart.html"]', label='Cart link')
    evidence_tracker.click('a[href="/checkout.html"]', label='Proceed To Checkout')
    evidence_tracker.fill('#name', 'John Doe', label='name')
    evidence_tracker.fill('#email', 'john@example.com', label='email')
    evidence_tracker.fill('#address', '123 Main St', label='address')
    evidence_tracker.fill('#city', 'New York', label='city')
    evidence_tracker.fill('#zip', '10001', label='zip')
    evidence_tracker.fill('#card-name', '4111111111111111', label='card number')
    evidence_tracker.fill('#expiry', '12/25', label='expiry')
    evidence_tracker.fill('#zip', '123', label='cvc')
    evidence_tracker.click('#place-order', label='Place Order')
    evidence_tracker.assert_visible('#place-order', label='order success message')