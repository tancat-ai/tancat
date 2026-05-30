# `src/browser_utils.py`

## High-Level Purpose

Browser interaction utilities for Playwright tests. Provides best-effort dismissal of consent banners, cookie popups, ad overlays, and other UI blockers that intercept pointer events during automated test execution.

## Module Metadata

- **Lines:** 143
- **Imports:** `playwright.sync_api.Page`

## Functions

### `dismiss_consent_overlays(page: Page) -> None`

Best-effort dismissal of consent, cookie, and ad-overlay popups using a multi-strategy approach:

1. **Standard consent buttons** — clicks first visible button matching: "Consent", "Accept", "Continue", "OK", "Got it", "I Agree", "Agree", or close buttons by aria-label
2. **Google Consent TVM** — handles `.fc-consent-root` "Consent" and "Manage options" buttons
3. **Escape key** — presses Escape to dismiss modals
4. **JS DOM removal** — removes Google Consent TVM elements, high z-index overlays (>10000), and cookie-banner classes via `page.evaluate()`
5. **Bootstrap panel expansion** — expands `.panel-collapse.collapse` elements by adding `in` class and `display: block`
6. **Ad overlay removal** — hides `#google_vignette`, `.adsbygoogle`, ad iframes, and ad-related elements via JS

## Dependencies
- `playwright.sync_api.Page`