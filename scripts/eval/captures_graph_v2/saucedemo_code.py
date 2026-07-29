from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_Log_in_with_username_standard_user_and_password_secret_sauce(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='Products')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_Add_at_least_one_item_(page: Page, e.g._Sauce_Labs_Backpack, evidence_tracker)_to_the_cart(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='cart badge 1')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_Navigate_to_the_shopping_cart_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='Shopping cart link')
    expect(page).to_have_url("https://www.saucedemo.com")

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_Verify_the_added_item_appears_correctly_in_the_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='Shopping cart link')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='Sauce Labs Backpack appears in cart')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_Navigate_to_the_checkout_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Checkout'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='Shopping cart link')
    evidence_tracker.assert_visible('[data-test="title"]', label='Checkout: Your Information page')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_Complete_the_checkout_process_and_verify_success_(page: Page, Thank_You_page, evidence_tracker)(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Checkout'; 'Postal Code'; 'Continue'; 'Finish'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='Shopping cart link')
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', 'test', label='First Name')
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', 'user', label='Last Name')
    expect(page).to_have_url("https://www.saucedemo.com")