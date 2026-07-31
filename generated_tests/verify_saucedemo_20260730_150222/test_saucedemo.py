import pytest
from playwright.sync_api import Page, expect
from pages.home_page import HomePage
from pages.inventory_page import InventoryPage
from pages.home_page import HomePage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_log_in(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    evidence_tracker.assert_visible('[data-test="inventory-item"]', label='product list')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    inventory_page.click('add to cart backpack')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='cart badge updated')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'cart icon'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    inventory_page.click('add to cart backpack')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='cart page title')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_item_in_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'cart icon'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    inventory_page.click('add to cart backpack')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='backpack in cart')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_checkout(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'cart icon'; 'checkout button'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    inventory_page.click('add to cart backpack')
    evidence_tracker.assert_visible('[data-test="secondary-header"]', label='checkout form')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_checkout(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'cart icon'; 'checkout button'; 'continue button'; 'finish button'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='login button')
    inventory_page.click('add to cart backpack')
    inventory_page.fill('first name', 'John')
    inventory_page.fill('last name', 'Doe')
    inventory_page.fill('zip code', '12345')
    evidence_tracker.assert_visible('[data-test="title"]', label='checkout complete message')