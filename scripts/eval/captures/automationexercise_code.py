import pytest
from playwright.sync_api import Page

from src.browser_utils import dismiss_consent_overlays
from src.evidence_tracker import EvidenceTracker


@pytest.mark.evidence(condition_ref="AC-1", story_ref="US-01")
def test_01_navigate_home(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.assert_visible(
        'expect(page).to_have_url("https://automationexercise.com")',
        label="home page loaded",
    )


@pytest.mark.evidence(condition_ref="AC-2", story_ref="US-01")
def test_02_navigate_products(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.assert_visible(
        'expect(page).to_have_url("https://automationexercise.com/products")',
        label="products page title",
    )


@pytest.mark.evidence(condition_ref="AC-3", story_ref="US-01")
def test_03_add_product_to_cart(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.click(
        '.add-to-cart.btn[data-product-id="1"]', label="Add to cart"
    )


@pytest.mark.evidence(condition_ref="AC-4", story_ref="US-01")
def test_04_verify_added_message(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.click(
        '.add-to-cart.btn[data-product-id="1"]', label="Add to cart"
    )
    evidence_tracker.assert_visible(
        '[data-product-id="11"]', label="add to cart confirmation"
    )


@pytest.mark.evidence(condition_ref="AC-5", story_ref="US-01")
def test_05_navigate_to_cart(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.click(
        '.add-to-cart.btn[data-product-id="1"]', label="Add to cart"
    )
    evidence_tracker.click('a[href="/view_cart"]', label="Cart link")
    evidence_tracker.assert_visible(
        'expect(page).to_have_url("https://automationexercise.com/view_cart")',
        label="cart page title",
    )


@pytest.mark.evidence(condition_ref="AC-6", story_ref="US-01")
def test_06_verify_cart_contents(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/products"]', label="Products link")
    evidence_tracker.click(
        '.add-to-cart.btn[data-product-id="1"]', label="Add to cart"
    )
    evidence_tracker.click('a[href="/view_cart"]', label="Cart link")
    evidence_tracker.assert_visible(
        ".cart_total_price", label="product name and price"
    )
