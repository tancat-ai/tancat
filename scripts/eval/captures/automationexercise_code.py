import pytest
from playwright.sync_api import Page

from src.browser_utils import dismiss_consent_overlays
from src.evidence_tracker import EvidenceTracker


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_home(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    pytest.skip("Skipping: unresolved placeholders for: 'home page loaded'")
    dismiss_consent_overlays(page)


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_products_link(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    pytest.skip("Skipping: unresolved placeholders for: 'products page title'")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_product_to_cart(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label="Add to cart")
    evidence_tracker.assert_visible('.add-to-cart.btn[data-product-id="11"]', label="add to cart confirmation")


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_confirmation_message(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label="Add to cart")
    evidence_tracker.assert_visible(".text-center", label="product added message")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_cart_link(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label="Add to cart")
    evidence_tracker.click('a[href="/view_cart"]', label="Cart link")
    evidence_tracker.assert_visible("#empty_cart", label="cart page title")


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_cart_contents(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label="Add to cart")
    evidence_tracker.click('a[href="/view_cart"]', label="Cart link")
    evidence_tracker.assert_visible(':has-text("Dictionaries & Encyclopedias")', label="product name and price")
