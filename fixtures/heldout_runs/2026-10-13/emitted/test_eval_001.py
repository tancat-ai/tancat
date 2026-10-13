from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    expect(page).to_have_url("https://www.saucedemo.com/inventory.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.assert_visible('.shopping_cart_link[data-test="shopping-cart-link"]', label='cart badge updated', expected_page='https://www.saucedemo.com/inventory.html')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='Cart', expected_page='https://www.saucedemo.com/inventory.html')
    expect(page).to_have_url("https://www.saucedemo.com/cart.html")


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_item_in_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='Cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.assert_visible('.cart_item[data-test="inventory-item"]', label='cart item visible', expected_page='https://www.saucedemo.com/cart.html')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_navigate_to_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='Cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('#checkout', label='Checkout', expected_page='https://www.saucedemo.com/cart.html')
    expect(page).to_have_url("https://www.saucedemo.com/checkout-step-one.html")


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com/')
    evidence_tracker.fill('#user-name', 'standard_user', label='username', expected_page='https://www.saucedemo.com/')
    evidence_tracker.fill('#password', 'secret_sauce', label='password', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#login-button', label='Login', expected_page='https://www.saucedemo.com/')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Add to cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='Cart', expected_page='https://www.saucedemo.com/inventory.html')
    evidence_tracker.click('#checkout', label='Checkout', expected_page='https://www.saucedemo.com/cart.html')
    evidence_tracker.fill('#first-name', 'John', label='First Name', expected_page='https://www.saucedemo.com/checkout-step-one.html')
    evidence_tracker.fill('#last-name', 'Doe', label='Last Name', expected_page='https://www.saucedemo.com/checkout-step-one.html')
    evidence_tracker.fill('#postal-code', '12345', label='Zip Code', expected_page='https://www.saucedemo.com/checkout-step-one.html')
    evidence_tracker.click('#continue', label='Continue', expected_page='https://www.saucedemo.com/checkout-step-one.html')
    evidence_tracker.click('#finish', label='Finish', expected_page='https://www.saucedemo.com/checkout-step-two.html')
    expect(page).to_have_url("https://www.saucedemo.com/checkout-complete.html")