import pytest
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'standard_user', label='username')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.assert_count('[data-test="inventory-item"]', label='product list')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'standard_user', label='username')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='add to cart backpack')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='cart badge')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'standard_user', label='username')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='add to cart backpack')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='shopping cart icon')
    expect(page).to_have_url("https://www.saucedemo.com")

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_cart_item(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'standard_user', label='username')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='add to cart backpack')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='shopping cart icon')
    evidence_tracker.assert_visible('.inventory_item_description[data-test="inventory-item-description"]', label='backpack item in cart')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_navigate_to_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'checkout button'")
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'standard_user', label='username')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='add to cart backpack')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='shopping cart icon')
    evidence_tracker.assert_visible('[data-test="title"]', label='checkout form')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'checkout button'; 'continue button'; 'finish button'")
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'standard_user', label='username')
    evidence_tracker.fill('.login_wrapper[data-test="login-container"]', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.click('#add-to-cart-sauce-labs-bike-light', label='add to cart backpack')
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label='shopping cart icon')
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', 'John', label='first name')
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', 'Doe', label='last name')
    evidence_tracker.fill('.product_sort_container[data-test="product-sort-container"]', '12345', label='zip code')
    expect(page).to_have_url("https://www.saucedemo.com")