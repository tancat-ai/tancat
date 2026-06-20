"""Browser interaction utilities for Playwright tests."""

from playwright.sync_api import Page


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
            """
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
            """
        )
        page.wait_for_timeout(300)
    except Exception:
        pass

    # --- 3a. Expand collapsed Bootstrap panels (e.g., category dropdowns) ---
    try:
        page.evaluate(
            """
            () => {
                document.querySelectorAll('.panel-collapse.collapse').forEach(el => {
                    el.classList.add('in');
                    el.style.display = 'block';
                });
            }
            """
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
            """
            () => {
                // Remove Google Consent TVM root and overlay
                const consentRoot = document.querySelector('.fc-consent-root');
                if (consentRoot) { consentRoot.remove(); }
                const dialogOverlay = document.querySelector('.fc-dialog-overlay');
                if (dialogOverlay) { dialogOverlay.remove(); }

                // Remove Google Vignette (standard ad overlay)
                const vignette = document.getElementById('google_vignette');
                if (vignette) {
                    vignette.style.display = 'none';
                    vignette.style.visibility = 'hidden';
                    vignette.remove();
                }

                // Remove all Google Ads slots and their host containers
                document.querySelectorAll('ins.adsbygoogle').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    if (el.parentNode) { el.parentNode.removeChild(el); }
                });

                // Remove ASWIFT (AdSense Swift) host divs that intercept clicks
                document.querySelectorAll('[id^="aswift_"]').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    el.style.pointerEvents = 'none';
                    if (el.parentNode) { el.parentNode.removeChild(el); }
                });

                // Remove ad iframes
                document.querySelectorAll('iframe[id*="aswift"], iframe[title="Advertisement"]').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    if (el.parentNode) { el.parentNode.removeChild(el); }
                });

                // Remove general ad containers
                document.querySelectorAll('[class*="ads"], [id*="google_ads"]').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    if (el.parentNode) { el.parentNode.removeChild(el); }
                });

            }
            """
        )
        page.wait_for_timeout(500)
    except Exception:
        pass
