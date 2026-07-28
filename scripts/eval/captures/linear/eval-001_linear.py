from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.home_page import HomePage
from pages.home_page import HomePage
from pages.inventory_page import InventoryPage


def login_to_site(page: Page):

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login_user(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')
    evidence_tracker.fill('#password', 'secret_sauce', label='password')
    evidence_tracker.click('#login-button', label='Login')
    expect(page).to_have_url("https://www.saucedemo.com")

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://www.saucedemo.com")
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    pytest.skip("Skipping: unresolved placeholders for: 'Add to cart'; 'cart badge shows 1'")
    login_to_site(page)

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://www.saucedemo.com")
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    pytest.skip("Skipping: unresolved placeholders for: 'Add to cart'; 'shopping cart link'")
    login_to_site(page)
    expect(page).to_have_url("https://www.saucedemo.com")

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_cart_item(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://www.saucedemo.com")
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    pytest.skip("Skipping: unresolved placeholders for: 'Add to cart'; 'shopping cart link'; 'cart item details'")
    login_to_site(page)

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_navigate_to_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://www.saucedemo.com")
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    pytest.skip("Skipping: unresolved placeholders for: 'Add to cart'; 'shopping cart link'; 'Checkout'; 'checkout information page'")
    login_to_site(page)

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_checkout(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://www.saucedemo.com")
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    pytest.skip("Skipping: unresolved placeholders for: 'Add to cart'; 'shopping cart link'; 'Checkout'; 'Continue'; 'Finish'")
    login_to_site(page)
    evidence_tracker.fill('#user-name', 'John', label='first name')
    evidence_tracker.fill('#user-name', 'Doe', label='last name')
    evidence_tracker.fill('#user-name', '12345', label='zip code')
    evidence_tracker.assert_visible('#login_credentials', label='Thank You message')