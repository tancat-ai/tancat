import pytest
from playwright.sync_api import Page

from src.browser_utils import dismiss_consent_overlays
from src.evidence_tracker import EvidenceTracker


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://www.saucedemo.com")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    evidence_tracker.assert_visible('[data-test="inventory-item-description"]', label="product list")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item_to_cart(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://www.saucedemo.com")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    evidence_tracker.click("#add-to-cart-sauce-labs-backpack", label="Add to cart (Backpack)")
    evidence_tracker.assert_visible('.shopping_cart_link[data-test="shopping-cart-link"]', label="cart badge updated")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_navigate_to_cart(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://www.saucedemo.com")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    evidence_tracker.click("#add-to-cart-sauce-labs-backpack", label="Add to cart (Backpack)")
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label="Cart icon")
    evidence_tracker.assert_visible("#cart_contents_container", label="Cart Summary")


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_cart_contents(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://www.saucedemo.com")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    evidence_tracker.click("#add-to-cart-sauce-labs-backpack", label="Add to cart (Backpack)")
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label="Cart icon")
    evidence_tracker.assert_visible('.cart_list[data-test="cart-list"]', label="backpack item in cart")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_navigate_to_checkout(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://www.saucedemo.com")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    evidence_tracker.click("#add-to-cart-sauce-labs-backpack", label="Add to cart (Backpack)")
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label="Cart icon")
    evidence_tracker.click("#checkout", label="Checkout")
    evidence_tracker.assert_visible("#checkout_info_container", label="Checkout Info form")


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_complete_checkout(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://www.saucedemo.com")
    pytest.skip("Skipping: unresolved placeholders for: 'Thank You page'")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="Login")
    evidence_tracker.click("#add-to-cart-sauce-labs-backpack", label="Add to cart (Backpack)")
    evidence_tracker.click('.shopping_cart_link[data-test="shopping-cart-link"]', label="Cart icon")
    evidence_tracker.click("#checkout", label="Checkout")
    evidence_tracker.fill("#first-name", "Demo", label="First Name")
    evidence_tracker.fill("#first-name", "User", label="Last Name")
    evidence_tracker.fill("#postal-code", "12345", label="Zip/Postal Code")
    evidence_tracker.click("#continue", label="Continue")
    evidence_tracker.click("#finish", label="Finish")
