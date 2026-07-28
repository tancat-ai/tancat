import pytest
from playwright.sync_api import Page, expect
from pages.home_page import HomePage
from pages.inventory_page import InventoryPage
from pages.home_page import HomePage


@pytest.mark.evidence(condition_ref="AC-1", story_ref="US-01")
def test_01_login(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate("https://www.saucedemo.com")
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    evidence_tracker.assert_visible('[data-test="inventory-item-description"]', label="product list")


@pytest.mark.evidence(condition_ref="AC-2", story_ref="US-01")
def test_02_add_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate("https://www.saucedemo.com")
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    inventory_page.click("Add to cart")
    evidence_tracker.assert_visible('.shopping_cart_badge[data-test="shopping-cart-badge"]', label="cart badge updated")


@pytest.mark.evidence(condition_ref="AC-3", story_ref="US-01")
def test_03_navigate_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate("https://www.saucedemo.com")
    pytest.skip("Skipping: unresolved placeholders for: 'cart icon'")
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    expect(page).to_have_url("https://www.saucedemo.com")


@pytest.mark.evidence(condition_ref="AC-4", story_ref="US-01")
def test_04_verify_cart_item(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate("https://www.saucedemo.com")
    pytest.skip("Skipping: unresolved placeholders for: 'cart icon'")
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    inventory_page.click("Add to cart")
    evidence_tracker.assert_visible("#item_4_title_link", label="Sauce Labs Backpack")


@pytest.mark.evidence(condition_ref="AC-5", story_ref="US-01")
def test_05_proceed_to_checkout(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate("https://www.saucedemo.com")
    pytest.skip("Skipping: unresolved placeholders for: 'cart icon'; 'Checkout'")
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    inventory_page.click("Add to cart")
    evidence_tracker.assert_visible("#header_container", label="checkout form")


@pytest.mark.evidence(condition_ref="AC-6", story_ref="US-01")
def test_06_complete_checkout(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    inventory_page = InventoryPage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate("https://www.saucedemo.com")
    pytest.skip("Skipping: unresolved placeholders for: 'cart icon'; 'Checkout'; 'Continue'; 'Finish'")
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    inventory_page.click("Add to cart")
    inventory_page.fill("first name", "John")
    inventory_page.fill("last name", "Doe")
    inventory_page.fill("zip code", "12345")
    evidence_tracker.assert_visible('[data-test="inventory-item-description"]', label="thank you message")
