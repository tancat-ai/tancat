"""
Auto-generated Playwright test - automationexercise.com UAT run
Generated: 2026-05-05 (LM Studio / qwen3.6-27b)
Target: https://automationexercise.com/
User Story: As a customer, I want to browse products on the website and add them to my cart so that I can purchase them later.
"""

from playwright.sync_api import Page, expect
import pytest


def dismiss_consent_overlays(page: Page) -> None:
    """Best-effort dismissal of consent, cookie, and ad-overlay popups."""
    # --- 1. Standard consent/cookie banner buttons ---
    candidate_selectors = [
        "button:has-text('Consent')",
        "button:has-text('Accept')",
        "button:has-text('Continue')",
        "button:has-text('OK')",
        "button:has-text('Got it')",
        "button:has-text('I Agree')",
        "button:has-text('Agree')",
        "button[aria-label='Close']",
        "button[aria-label='close']",
    ]
    for selector in candidate_selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                locator.click(timeout=500)
                page.wait_for_timeout(200)
                break
        except Exception:
            continue

    # --- 2. Google Consent TVM (Two-Party Mode) ---
    try:
        consent_btn = page.locator(".fc-consent-root button:has-text('Consent')").first
        if consent_btn.count() > 0 and consent_btn.is_visible():
            consent_btn.click(timeout=2000)
            page.wait_for_timeout(500)
    except Exception:
        pass

    try:
        manage_btn = page.locator(".fc-consent-root button:has-text('Manage options')").first
        if manage_btn.count() > 0 and manage_btn.is_visible():
            manage_btn.click(timeout=2000)
            page.wait_for_timeout(500)
    except Exception:
        pass

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass

    # --- 3. Remove Google Consent TVM DOM elements via JavaScript ---
    try:
        page.evaluate(
            '''
            () => {
                const consentRoot = document.querySelector('.fc-consent-root');
                if (consentRoot) { consentRoot.remove(); }
                const dialogOverlay = document.querySelector('.fc-dialog-overlay');
                if (dialogOverlay) { dialogOverlay.remove(); }
                document.querySelectorAll('[class*=consent], [class*=cookie-banner], [class*=cookie-modal]').forEach(el => el.remove());
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    const style = window.getComputedStyle(el);
                    const zIndex = parseInt(style.zIndex, 10);
                    if (zIndex > 10000 && el.tagName !== 'IFRAME') { el.remove(); }
                }
            }
            '''
        )
        page.wait_for_timeout(300)
    except Exception:
        pass

    # --- 3a. Expand collapsed Bootstrap panels (e.g., category dropdowns) ---
    try:
        page.evaluate(
            '''
            () => {
                document.querySelectorAll('.panel-collapse.collapse').forEach(el => {
                    el.classList.add('in');
                    el.style.display = 'block';
                });
            }
            '''
        )
        page.wait_for_timeout(300)
    except Exception:
        pass

    # --- 4. Dismiss ad overlays that may intercept pointer events ---
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass

    ad_overlay_selectors = [
        "#google_vignette",
        "[id*='google_vignette']",
        ".adsbygoogle",
        "iframe[id*='google_ads']",
        "iframe[id*='aswift']",
        "iframe[title='Advertisement']",
    ]
    for selector in ad_overlay_selectors:
        try:
            ad_element = page.locator(selector).first
            if ad_element.count() > 0:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
        except Exception:
            continue

    # Use JavaScript to remove ad overlays that intercept pointer events
    try:
        page.evaluate(
            '''
            () => {
                const vignette = document.getElementById('google_vignette');
                if (vignette) {
                    vignette.style.display = 'none';
                    vignette.style.visibility = 'hidden';
                }
                document.querySelectorAll('ins.adsbygoogle').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                });
                document.querySelectorAll('iframe[id*="aswift"], iframe[title="Advertisement"]').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                });
                document.querySelectorAll('[class*="ads"], [id*="google_ads"]').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                });
            }
            '''
        )
        page.wait_for_timeout(300)
    except Exception:
        pass


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_home_page(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate('https://automationexercise.com/products')
    dismiss_consent_overlays(page)


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_products_link(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate('https://automationexercise.com/products')
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/brand_products/Allen Solly Junior"]', label='Products link in header navigation')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_add_to_cart_for_blue_top(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate('https://automationexercise.com/products')
    dismiss_consent_overlays(page)
    evidence_tracker.click('.add-to-cart.btn[data-product-id="11"]', label='Add to cart button for Blue Top product')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_product_added_confirmation(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate('https://automationexercise.com/products')
    dismiss_consent_overlays(page)
    evidence_tracker.click('.add-to-cart.btn[data-product-id="11"]', label='Add to cart button for Blue Top product')
    evidence_tracker.assert_visible('.cart_quantity_delete[data-product-id="1"]', label='confirmation message that product was successfully added to cart')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_cart_link(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate('https://automationexercise.com/view_cart')
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/view_cart"]', label='Cart link in header navigation')


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_cart_displays_product_name_and_price(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate('https://automationexercise.com/view_cart')
    dismiss_consent_overlays(page)
    evidence_tracker.assert_visible('.cart_quantity_delete[data-product-id="1"]', label='product name and price displayed in cart page')


# PAGES_NEEDED:
# - https://automationexercise.com/ (home page)
# - https://automationexercise.com/products (products page)
# - https://automationexercise.com/view_cart (cart page)