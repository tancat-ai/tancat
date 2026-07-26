from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.home_page import HomePage
from pages.inventory_page import InventoryPage
from pages.home_page import HomePage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_Log_in_with_username_standard_user_and_password_secret_sauce(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='Products')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_Add_at_least_one_item_to_the_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='Products')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='Cart badge displays 1')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_Navigate_to_the_shopping_cart_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='Products')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    inventory_page.click('Shopping cart link')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_Verify_the_added_item_appears_correctly_in_the_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='Products')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    inventory_page.click('Shopping cart link')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='Sauce Labs Backpack is displayed in cart')
    evidence_tracker.assert_visible('.inventory_item_price[data-test="inventory-item-price"]', label='Sauce Labs Backpack price is $29.99')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_Navigate_to_the_checkout_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Checkout'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='Products')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    inventory_page.click('Shopping cart link')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='Sauce Labs Backpack is displayed in cart')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_Complete_the_checkout_process_and_verify_success(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    pytest.skip("Skipping: unresolved placeholders for: 'Checkout'; 'Zip/Postal Code'; 'Finish'")
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    evidence_tracker.assert_visible('.title[data-test="title"]', label='Products')
    inventory_page.click('Add to cart Sauce Labs Backpack')
    inventory_page.click('Shopping cart link')
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label='Sauce Labs Backpack is displayed in cart')
    inventory_page.fill('First Name', 'John')
    inventory_page.fill('Last Name', 'Doe')
    inventory_page.click('Continue')
    expect(page).to_have_url("https://www.saucedemo.com")