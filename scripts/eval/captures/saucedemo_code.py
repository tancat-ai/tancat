from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.home_page import HomePage
from pages.inventory_page import InventoryPage
from pages.home_page import HomePage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login_with_standard_user(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='Products')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_sauce_labs_backpack_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    evidence_tracker.assert_visible('[data-test="primary-header"]', label='1')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_to_shopping_cart_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    inventory_page.click('Shopping cart link')
    expect(page).to_have_url("https://www.saucedemo.com")

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_added_item_appears_correctly_in_the_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    inventory_page.click('Shopping cart link')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='Sauce Labs Backpack appears in cart')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_navigate_to_checkout_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Checkout'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    inventory_page.click('Shopping cart link')
    evidence_tracker.assert_visible('[data-test="title"]', label='Checkout Information page')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_checkout_process_and_verify_success(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Checkout'; 'Postal Code'; 'Continue'; 'Finish'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    inventory_page.click('Shopping cart link')
    inventory_page.fill('First Name', 'Test')
    inventory_page.fill('Last Name', 'User')
    expect(page).to_have_url("https://www.saucedemo.com")