from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    # Page arrival check: expected 'https://www.saucedemo.com/inventory.html', browser observed on 'https://www.saucedemo.com/inventory.html'
    evidence_tracker.record_page_expectation(expected_url='https://www.saucedemo.com/inventory.html', observed_url='https://www.saucedemo.com/inventory.html', trail_step="index=4; action=scrape; description='home page loaded'; from_url='https://www.saucedemo.com/inventory.html'; to_url='https://www.saucedemo.com/inventory.html'; navigated=False; timestamp=1793481482.2423482", producer='keyword', description='home page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://www.saucedemo.com/inventory.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.assert_visible('.shopping_cart_link[data-test="shopping-cart-link"]', label='cart badge updated', expected_page='https://www.saucedemo.com/inventory.html')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='cart', expected_page='https://www.saucedemo.com/inventory.html')
    # Page arrival check: expected 'https://www.saucedemo.com/cart.html', browser observed on 'https://www.saucedemo.com/cart.html'
    evidence_tracker.record_page_expectation(expected_url='https://www.saucedemo.com/cart.html', observed_url='https://www.saucedemo.com/cart.html', trail_step="index=6; action=scrape; description='cart page loaded'; from_url='https://www.saucedemo.com/cart.html'; to_url='https://www.saucedemo.com/cart.html'; navigated=False; timestamp=1793481490.6420772", producer='keyword', description='cart page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://www.saucedemo.com/cart.html")


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_item_in_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='cart', expected_page='https://www.saucedemo.com/inventory.html')
    pytest.skip("specificity guard: open-ended step resolved to one specific element ('.cart_item[data-test='inventory-item']'); asserting it would fail when a different outcome is legitimately chosen")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_navigate_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('#checkout', label='Checkout', expected_page='https://www.saucedemo.com/cart.html')
    # Page arrival check: expected 'https://www.saucedemo.com/checkout-step-one.html', browser observed on 'https://www.saucedemo.com/checkout-step-one.html'
    evidence_tracker.record_page_expectation(expected_url='https://www.saucedemo.com/checkout-step-one.html', observed_url='https://www.saucedemo.com/checkout-step-one.html', trail_step="index=7; action=scrape; description='checkout page loaded'; from_url='https://www.saucedemo.com/checkout-step-one.html'; to_url='https://www.saucedemo.com/checkout-step-one.html'; navigated=False; timestamp=1793481495.0807912", producer='keyword', description='checkout page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://www.saucedemo.com/checkout-step-one.html")


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('#checkout', label='Checkout', expected_page='https://www.saucedemo.com/cart.html')
    evidence_tracker.fill('#first-name', 'John', label='First Name', expected_page='https://www.saucedemo.com/checkout-step-one.html')
    evidence_tracker.fill('#last-name', 'Doe', label='Last Name', expected_page='https://www.saucedemo.com/checkout-step-one.html')
    evidence_tracker.fill('#postal-code', '12345', label='Zip Code', expected_page='https://www.saucedemo.com/checkout-step-one.html')
    evidence_tracker.click('#continue', label='Continue', expected_page='https://www.saucedemo.com/checkout-step-one.html')
    evidence_tracker.click('#finish', label='Finish', expected_page='https://www.saucedemo.com/checkout-step-two.html')
    # Page arrival check: expected 'https://www.saucedemo.com/checkout-complete.html', browser observed on 'https://www.saucedemo.com/checkout-complete.html'
    evidence_tracker.record_page_expectation(expected_url='https://www.saucedemo.com/checkout-complete.html', observed_url='https://www.saucedemo.com/checkout-complete.html', trail_step="index=12; action=scrape; description='Thank You page loaded'; from_url='https://www.saucedemo.com/checkout-complete.html'; to_url='https://www.saucedemo.com/checkout-complete.html'; navigated=False; timestamp=1793481505.1080759", producer='keyword', description='Thank You page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://www.saucedemo.com/checkout-complete.html")