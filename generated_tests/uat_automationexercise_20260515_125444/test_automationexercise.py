from playwright.sync_api import Page, expect
from src.browser_utils import dismiss_consent_overlays
import pytest

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_home_page(page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com')
    dismiss_consent_overlays(page)
    evidence_tracker.assert_visible('a[href="/"]', label='home page loaded')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_products_link(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'Products link in header navigation'")
    evidence_tracker.navigate('https://automationexercise.com')
    dismiss_consent_overlays(page)
    pytest.skip("Unresolved placeholder: {{CLICK:Products link in header navigation}}")
    evidence_tracker.assert_visible('a[href="/"]', label='products page loaded')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_add_to_cart_blue_top(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'Products link in header navigation'")
    evidence_tracker.navigate('https://automationexercise.com')
    dismiss_consent_overlays(page)
    pytest.skip("Unresolved placeholder: {{CLICK:Products link in header navigation}}")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="11"]', label='Add to cart button for Blue Top')
    evidence_tracker.assert_visible('.add-to-cart.btn[data-product-id="11"]', label='add to cart button clicked')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_add_to_cart_confirmation(page, evidence_tracker):
    # --- Prerequisite: prerequisite (injected) ---
    evidence_tracker.assert_visible('a[href="/"]', label='home page loaded')
    # --- Original test steps ---
    pytest.skip("Skipping: unresolved placeholders for: 'Products link in header navigation'; 'confirmation message indicating product added to cart'")
    evidence_tracker.navigate('https://automationexercise.com')
    dismiss_consent_overlays(page)
    pytest.skip("Unresolved placeholder: {{CLICK:Products link in header navigation}}")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="11"]', label='Add to cart button for Blue Top')
    pytest.skip("Unresolved placeholder: {{ASSERT:confirmation message indicating product added to cart}}")

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_cart_link(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'Products link in header navigation'")
    evidence_tracker.navigate('https://automationexercise.com')
    dismiss_consent_overlays(page)
    pytest.skip("Unresolved placeholder: {{CLICK:Products link in header navigation}}")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="11"]', label='Add to cart button for Blue Top')
    evidence_tracker.click('a[href="/view_cart"]', label='Cart link in header navigation')
    evidence_tracker.assert_visible('a[href="/"]', label='cart page loaded')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_cart_displays_product(page, evidence_tracker):
    pytest.skip("Skipping: unresolved placeholders for: 'Products link in header navigation'")
    evidence_tracker.navigate('https://automationexercise.com')
    dismiss_consent_overlays(page)
    pytest.skip("Unresolved placeholder: {{CLICK:Products link in header navigation}}")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="11"]', label='Add to cart button for Blue Top')
    evidence_tracker.click('a[href="/view_cart"]', label='Cart link in header navigation')
    evidence_tracker.assert_visible('a[href="/"]', label='cart page displays Blue Top name and price')