"""Authentication detection helpers for journey scraping.

Extracted from journey_scraper.py to keep the scraper focused on its core
responsibility (following user journeys). These functions detect unexpected
auth redirects, SSO gateways, MFA prompts, and CAPTCHAs so the pipeline
can surface meaningful errors instead of silently failing.
"""

from __future__ import annotations

import re
from re import compile as _re_compile
from urllib.parse import urlparse

# ── Detection patterns ──────────────────────────────────────────

_AUTH_REDIRECT_KEYWORDS = _re_compile(
    r"(login|sign\s*in|sign[- ]in|authenticate|log\s*in|session\s*expired|authentication)",
    flags=re.IGNORECASE,
)

_MFA_LABEL_PATTERN = _re_compile(
    r"(verification code|authenticator|one[- ]?time|2fa|two[- ]factor)",
    flags=re.IGNORECASE,
)

_CAPTCHA_DOMAINS: tuple[str, ...] = ("google.recaptcha.net", "hcaptcha.com", "captcha.")
_CAPTCHA_ELEMENT_PATTERN = _re_compile(r"(captcha|recaptcha|hcaptcha)", flags=re.IGNORECASE)


# ── Public API ──────────────────────────────────────────────────


def detect_auth_redirect(page_url: str, intended_url: str, page_title: str, h1_text: str) -> bool:
    """Return True if the current page appears to be an unexpected auth redirect."""
    # URL mismatch after navigation
    if page_url != intended_url and urlparse(page_url).netloc != urlparse(intended_url).netloc:
        return True
    # Page title or H1 contains auth keywords
    if _AUTH_REDIRECT_KEYWORDS.search(page_title):
        return True
    if _AUTH_REDIRECT_KEYWORDS.search(h1_text):
        return True
    return False


def detect_sso(base_domain: str, current_url: str) -> bool:
    """Return True if navigation left the base domain (likely SSO redirect)."""
    current_domain = urlparse(current_url).netloc
    return bool(current_domain != base_domain and current_domain)


def detect_mfa(page_html: str) -> bool:
    """Return True if the page contains MFA-related inputs."""
    if 'type="tel"' in page_html:
        return True
    if _MFA_LABEL_PATTERN.search(page_html):
        return True
    return False


def detect_captcha(page_html: str) -> bool:
    """Return True if the page contains CAPTCHA iframes or elements."""
    for domain in _CAPTCHA_DOMAINS:
        if domain in page_html:
            return True
    if _CAPTCHA_ELEMENT_PATTERN.search(page_html):
        return True
    return False
