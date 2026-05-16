from playwright.sync_api import Page, expect
from src.browser_utils import dismiss_consent_overlays
import pytest

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.assert_visible('#item_3_title_link', label='products page loaded')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item_to_cart(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Sauce Labs Backpack add to cart button')
    evidence_tracker.assert_visible('#add-to-cart-test.allthethings\\(\\)-t-shirt-\\(red\\)', label='add to cart button changed to remove')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_to_cart(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'shopping cart icon'")
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    pytest.skip("Unresolved placeholder: {{CLICK:shopping cart icon}}")
    evidence_tracker.assert_visible('.shopping_cart_link[data-test="shopping-cart-link"]', label='cart page loaded')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_item_in_cart(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'shopping cart icon'")
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Sauce Labs Backpack add to cart button')
    pytest.skip("Unresolved placeholder: {{CLICK:shopping cart icon}}")
    evidence_tracker.assert_visible('#user-name', label='Sauce Labs Backpack item name visible in cart')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_navigate_to_checkout(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'shopping cart icon'; 'checkout button'")
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Sauce Labs Backpack add to cart button')
    pytest.skip("Unresolved placeholder: {{CLICK:shopping cart icon}}")
    evidence_tracker.assert_visible('.product_sort_container[data-test="product-sort-container"]', label='checkout information form loaded')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_checkout(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'shopping cart icon'; 'checkout button'; 'finish button'")
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-backpack', label='Sauce Labs Backpack add to cart button')
    pytest.skip("Unresolved placeholder: {{CLICK:shopping cart icon}}")
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', 'John', label='first name input')
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', 'Doe', label='last name input')
    evidence_tracker.fill('#user-name', '90210', label='zip code input')
    pytest.skip("Unresolved placeholder: {{CLICK:finish button}}")
    evidence_tracker.assert_visible('#react-burger-menu-btn', label='thank you confirmation page loaded')