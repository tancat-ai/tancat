"""Login form detection and filling utilities.

Extracted from stateful_scraper.py to centralize login form handling.
Used by stateful scrapers to detect and fill common demo-site login patterns.
"""

from __future__ import annotations

from typing import Any

from src.journey_models import CredentialProfile

# ── Public API ──────────────────────────────────────────────────


def attempt_login(page: Any, credential_profile: CredentialProfile | None) -> None:
    """Detect and fill login forms on the current page.

    Handles common demo-site patterns:
    - saucedemo.com: #user-name / #password / #login-button
    - Generic: input[type="text"] + input[type="password"] + button

    If a credential profile is provided, uses its username/password.
    Otherwise, attempts form detection without filling credentials.
    """
    if credential_profile is None:
        _detect_login_forms_only(page)
        return

    username = credential_profile.username
    password = credential_profile.password

    # Strategy 1: saucedemo-style (id-based)
    _try_saucedemo_login(page, username, password)

    # Strategy 2: Generic form detection
    _try_generic_form_login(page, username, password)


# ── Private helpers ─────────────────────────────────────────────


def _try_saucedemo_login(page: Any, username: str, password: str) -> None:
    """Try saucedemo-style login (id-based selectors)."""
    try:
        user_field = page.locator("#user-name, #username, #email, [name='username'], [name='email']").first
        pass_field = page.locator("#password, [name='password']").first
        login_btn = page.locator(
            "#login-button, #login-btn, button[type='submit'], "
            'button:has-text("Login"), button:has-text("Log in"), button:has-text("Sign in")',
        ).first
        if user_field.is_visible(timeout=2000) and pass_field.is_visible(timeout=2000):
            user_field.fill(username)
            pass_field.fill(password)
            if login_btn.is_visible(timeout=2000):
                login_btn.click(timeout=5000)
                page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass


def _try_generic_form_login(page: Any, username: str, password: str) -> None:
    """Try generic form-based login."""
    try:
        form = page.locator("form").first
        if form and form.is_visible(timeout=1000):
            text_input = form.locator('input[type="text"], input[type="email"]').first
            pass_input = form.locator('input[type="password"]').first
            submit_btn = form.locator('button[type="submit"], input[type="submit"]').first
            if text_input.is_visible(timeout=1000) and pass_input.is_visible(timeout=1000):
                text_input.fill(username)
                pass_input.fill(password)
                if submit_btn.is_visible(timeout=1000):
                    submit_btn.click(timeout=5000)
                    page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass


def _detect_login_forms_only(page: Any) -> None:
    """Detect login forms without filling credentials.

    Some sites allow anonymous access or have pre-filled fields.
    This method detects forms but does not fill them.
    """
    # Strategy 1: saucedemo-style fields — detect but don't fill
    try:
        user_field = page.locator("#user-name, #username, #email, [name='username'], [name='email']").first
        pass_field = page.locator("#password, [name='password']").first
        if user_field.is_visible(timeout=2000) and pass_field.is_visible(timeout=2000):
            return
    except Exception:
        pass

    # Strategy 2: Generic form detection — detect but don't fill
    try:
        form = page.locator("form").first
        if form and form.is_visible(timeout=1000):
            text_input = form.locator('input[type="text"], input[type="email"]').first
            pass_input = form.locator('input[type="password"]').first
            if text_input.is_visible(timeout=1000) and pass_input.is_visible(timeout=1000):
                return
    except Exception:
        pass
