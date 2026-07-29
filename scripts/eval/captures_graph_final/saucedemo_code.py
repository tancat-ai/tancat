from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_log_in_with_username_standard_user_and_password_secret_sauce(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='user-name')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.inventory_item_name[data-test="inventory-item-name"]', label='Log in with username standard_user and password secret_sauce')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_at_least_one_item_(page: Page, e.g._Sauce_Labs_Backpack, evidence_tracker)_to_the_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='user-name')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='Add at least one item (e.g. Sauce Labs Backpack) to the cart')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_to_the_shopping_cart_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Cart icon'")
    evidence_tracker.fill('#user-name', 'standard_user', label='user-name')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    expect(page).to_have_url("https://www.saucedemo.com")

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_the_added_item_appears_correctly_in_the_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Cart icon'")
    evidence_tracker.fill('#user-name', 'standard_user', label='user-name')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='Verify the added item appears correctly in the cart')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_navigate_to_the_checkout_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Cart icon'; 'Checkout'")
    evidence_tracker.fill('#user-name', 'standard_user', label='user-name')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    expect(page).to_have_url("https://www.saucedemo.com")

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_the_checkout_process_and_verify_success_(page: Page, Thank_You_page, evidence_tracker)(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Cart icon'; 'Checkout'; 'Zip/Postal Code'; 'Finish'")
    evidence_tracker.fill('#user-name', 'standard_user', label='user-name')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='Add to cart Sauce Labs Backpack')
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', 'Standard', label='First Name')
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', 'User', label='Last Name')
    evidence_tracker.click('#item_3_title_link', label='Continue')
    expect(page).to_have_url("https://www.saucedemo.com")