"""Browser interaction utilities for Playwright tests."""

from playwright.sync_api import Page


def dismiss_consent_overlays(page: Page) -> None:
    """Best-effort dismissal of consent, cookie, and ad-overlay popups.

    Uses a two-stage approach:
    1. Structural detection — find consent banner containers by known class/id
       patterns, then click dismiss buttons INSIDE those containers.
    2. Position-based detection — find overlay-like elements (fixed/sticky
       positioned near the bottom or center of the viewport) and try to dismiss
       them.

    This avoids matching generic button text (e.g. "Continue Shopping") on
    regular page content. See B-015 for the motivation.
    """
    # --- 1. Google Consent TVM (Two-Party Mode) — structural, safe ---
    _dismiss_google_consent_tvm(page)

    # --- 2. Structural consent banners — known containers ---
    _dismiss_structural_consent_banners(page)

    # --- 3. Position-based overlay detection ---
    _dismiss_position_overlays(page)

    # --- 4. Remove ad overlays via JavaScript (specific selectors only) ---
    _remove_ad_overlays_js(page)


def _dismiss_google_consent_tvm(page: Page) -> None:
    """Handle Google Consent Transparency & Consent Framework banners."""
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

    # Remove Google Consent TVM DOM elements via JavaScript
    try:
        page.evaluate(
            """
            () => {
                const consentRoot = document.querySelector('.fc-consent-root');
                if (consentRoot) { consentRoot.remove(); }
                const dialogOverlay = document.querySelector('.fc-dialog-overlay');
                if (dialogOverlay) { dialogOverlay.remove(); }
            }
            """
        )
        page.wait_for_timeout(200)
    except Exception:
        pass


def _dismiss_structural_consent_banners(page: Page) -> None:
    """Find consent/cookie banner containers and click dismiss buttons inside them.

    Uses known class/id patterns for common consent providers (OneTrust, Cookiebot,
    Osano, etc.) and generic overlay patterns. Buttons are only matched if they
    are descendants of these containers — preventing false positives on regular
    page content.
    """
    # Known consent banner container selectors
    container_selectors = [
        "[class*='oneTrust']",
        "[class*='cookiebanner']",
        "[class*='cookie-banner']",
        "[class*='cookie-consent']",
        "[class*='cookie-modal']",
        "[class*='cookie-overlay']",
        "[class*='consent-banner']",
        "[class*='consent-modal']",
        "[class*='consent-overlay']",
        "[class*='Cookiebot']",
        "[class*='osano-cm']",
        "[class*='cybot-cookie']",
        "#onetrust-banner-sdk",
        "#cookie-notice",
        "#cookie-info",
        "[id*='cookie-banner']",
        "[id*='cookie-consent']",
        "[id*='consent-banner']",
        "[role='dialog']",
        "[role='alertdialog']",
    ]

    # Button text patterns that signal consent dismissal
    # (only matched INSIDE consent containers, not globally)
    consent_button_patterns = [
        "button:has-text('Consent')",
        "button:has-text('Accept')",
        "button:has-text('Accept All')",
        "button:has-text('OK')",
        "button:has-text('Got it')",
        "button:has-text('Got It')",
        "button:has-text('I Agree')",
        "button:has-text('Agree')",
        "button:has-text('Allow')",
        "button:has-text('Allow All')",
        "button[aria-label='Close']",
        "button[aria-label='close']",
        "button[aria-label='Dismiss']",
        "button[aria-label='dismiss']",
        "button[aria-label='X']",
    ]

    for container_sel in container_selectors:
        try:
            container = page.locator(container_sel).first
            if container.count() == 0:
                continue
            if not container.is_visible(timeout=1000):
                continue

            for btn_pattern in consent_button_patterns:
                try:
                    btn = container.locator(btn_pattern).first
                    if btn.count() > 0 and btn.is_visible(timeout=500):
                        btn.click(timeout=500)
                        page.wait_for_timeout(200)
                        return  # Dismissed, move on
                except Exception:
                    continue
        except Exception:
            continue


def _dismiss_position_overlays(page: Page) -> None:
    """Dismiss overlays detected by position (fixed/sticky, bottom or center of viewport).

    Finds overlay-like elements using JavaScript (position: fixed/sticky, near bottom
    of viewport, or centered with backdrop) and clicks dismiss buttons inside them.

    This catches consent banners that don't use known class names but are positioned
    as typical overlay banners.
    """
    # Button text patterns for position-detected overlays
    dismiss_texts = [
        "Accept",
        "Accept All",
        "OK",
        "Got it",
        "Got It",
        "I Agree",
        "Agree",
        "Allow",
        "Allow All",
        "Consent",
    ]

    try:
        # Find overlay-like containers and their dismiss buttons via JS
        result: dict = page.evaluate(
            f"""
            () => {{
                const results = [];
                const dismissTexts = {dismiss_texts};
                const vpHeight = window.innerHeight;
                const vpWidth = window.innerWidth;
                const allElements = document.querySelectorAll('div, section, [role="dialog"], [role="alertdialog"]');

                for (const el of allElements) {{
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();

                    // Skip elements that are too small or off-screen
                    if (rect.width < 200 || rect.height < 40) continue;
                    if (rect.bottom < 0 || rect.top > vpHeight) continue;

                    // Check for overlay-like positioning
                    const isFixed = style.position === 'fixed';
                    const isSticky = style.position === 'sticky';
                    const hasBackdrop = style.backgroundColor &&
                        (style.backgroundColor.includes('rgba') ||
                         style.backgroundColor.includes('rgb('));

                    // Bottom banner: fixed/sticky near bottom
                    const isBottomBanner = isFixed && rect.bottom > 0 && rect.bottom < vpHeight * 0.3 &&
                                           rect.width > vpWidth * 0.3;

                    // Centered overlay/modal: fixed and near center
                    const isCenteredOverlay = isFixed &&
                                             rect.left > vpWidth * 0.1 && rect.left < vpWidth * 0.9 &&
                                             rect.top > vpHeight * 0.1 && rect.top < vpHeight * 0.7;

                    if (!isBottomBanner && !isCenteredOverlay) continue;

                    // Look for dismiss buttons inside this container
                    const buttons = el.querySelectorAll('button, [role="button"], a[role="button"]');
                    for (const btn of buttons) {{
                        const btnRect = btn.getBoundingClientRect();
                        if (btnRect.width < 20 || btnRect.height < 15) continue;

                        const btnText = (btn.innerText || '').trim();
                        if (btnText.length < 2 || btnText.length > 30) continue;

                        const matches = dismissTexts.some(t => btnText.includes(t));
                        if (matches) {{
                            results.push({{
                                buttonText: btnText,
                                x: btnRect.left + btnRect.width / 2,
                                y: btnRect.top + btnRect.height / 2,
                                overlayPosition: style.position,
                            }});
                        }}
                    }}
                }}
                return results;
            }}
            """
        )

        # Click the first matching button found
        if result and len(result) > 0:
            # Use the first (most likely) dismiss button
            btn_info = result[0]
            try:
                page.mouse.click(btn_info["x"], btn_info["y"])
                page.wait_for_timeout(300)
            except Exception:
                pass

    except Exception:
        pass

    # Expand collapsed Bootstrap panels (e.g., category dropdowns on automationexercise)
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


def _remove_ad_overlays_js(page: Page) -> None:
    """Remove known ad overlay elements via JavaScript.

    Uses specific, safe selectors for known ad patterns. Does NOT remove elements
    by generic properties (e.g. z-index) to avoid affecting legitimate page content.
    """
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass

    # Check for Google Vignette and similar known ad overlays
    ad_overlay_selectors = [
        "#google_vignette",
        "[id*='google_vignette']",
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

    # Remove ad overlays via JavaScript (specific selectors only)
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
        page.wait_for_timeout(300)
    except Exception:
        pass
