"""Browser interaction utilities shared across the pipeline."""

from __future__ import annotations

from typing import Any


def dismiss_consent_overlays(page: Any) -> None:
    """Best-effort dismissal of consent, cookie, and ad-overlay popups.

    Handles:
    - Standard GDPR consent buttons (Consent, Accept, Agree, etc.)
    - Google Consent TVM (fc-consent-root / fc-dialog-overlay)
    - Google AdSense vignette overlays
    - General modal overlays that intercept pointer events
    """
    # --- 1. Standard consent/cookie banner buttons ---
    selectors = [
        "button:has-text('Consent')",
        "button:has-text('Accept')",
        "button:has-text('Continue')",
        "button:has-text('OK')",
        "button:has-text('Got it')",
        "button:has-text('I Agree')",
        "button:has-text('Agree')",
        "button[aria-label='Close']",
        "button[aria-label='close']",
        ".cc-banner button",
        ".cookie-banner button",
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=2000)
                page.wait_for_timeout(300)
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

    # --- 3. Google AdSense vignette ---
    try:
        vignette = page.locator("div.vignette-close-button").first
        if vignette.count() > 0 and vignette.is_visible():
            vignette.click(timeout=2000)
            page.wait_for_timeout(500)
    except Exception:
        pass

    # --- 4. Generic overlay dismissal (Escape key) ---
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass
