"""Tests for src/locator_builder — B-065: unmatchable selectors.

The robust locator is the selector that ends up in the generated tests, so it
must survive Tailwind variant classes (hover:/sm:/3xl:), fractional utilities
(py-3.5, w-1/2) and absolute hrefs.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.locator_builder import _css_escape_class_token, build_dot_classes, build_robust_locator

# ── Escape helpers ───────────────────────────────────────────────────────────


def test_css_escape_class_token_escapes_colon_variants() -> None:
    assert _css_escape_class_token("hover:text-amber-200") == "hover\\:text-amber-200"
    assert _css_escape_class_token("sm:text-3xl") == "sm\\:text-3xl"


def test_css_escape_class_token_escapes_dot_and_slash() -> None:
    assert _css_escape_class_token("py-3.5") == "py-3\\.5"
    assert _css_escape_class_token("w-1/2") == "w-1\\/2"


def test_css_escape_class_token_leading_digit_uses_six_digit_escape() -> None:
    # A bare \3 would parse as the unicode escape for U+0003.
    assert _css_escape_class_token("3xl:flex") == "\\000033xl\\:flex"


def test_css_escape_class_token_plain_unchanged() -> None:
    assert _css_escape_class_token("mt-2") == "mt-2"
    assert _css_escape_class_token("font-extrabold") == "font-extrabold"


def test_build_dot_classes_joins_escaped_tokens() -> None:
    assert build_dot_classes("mt-2 sm:text-3xl hover:text-amber-200") == ".mt-2.sm\\:text-3xl.hover\\:text-amber-200"
    assert build_dot_classes("") == ""
    assert build_dot_classes("   ") == ""


def test_build_dot_classes_selector_matches_element() -> None:
    html = '<h2 class="mt-2 sm:text-3xl hover:text-amber-200 py-3.5">X</h2>'
    selector = build_dot_classes("mt-2 sm:text-3xl hover:text-amber-200 py-3.5")
    assert len(BeautifulSoup(html, "html.parser").select(selector)) == 1


# ── build_robust_locator: classes ────────────────────────────────────────────


def test_robust_locator_keeps_escaped_tailwind_tokens() -> None:
    """Variant classes must survive the class re-extraction (B-065).

    The old regex (\\.([\\w-]+)) split hover:text-amber-200 into the bare
    class .hover and dropped the suffix.
    """
    element = {
        "tag": "h2",
        "text": "Built for the regulated buyer",
        "role": "h2",
        "selector": ".mt-2.sm\\:text-3xl.text-white.font-extrabold",
        "classes": "mt-2 sm:text-3xl text-white font-extrabold",
        "href": "",
        "raw_href": "",
        "id": "",
        "aria_label": "",
    }
    locator = build_robust_locator(element)
    assert locator == "h2.font-extrabold.mt-2.sm\\:text-3xl.text-white"
    html = '<h2 class="mt-2 sm:text-3xl text-white font-extrabold">X</h2>'
    assert len(BeautifulSoup(html, "html.parser").select(locator)) == 1


def test_robust_locator_unescaped_legacy_selector_still_uses_classes_key() -> None:
    """Elements whose selector predates escaping still emit escaped classes.

    The classes key carries the raw names, so the locator escapes them at
    build time rather than re-parsing a broken selector string.
    """
    element = {
        "tag": "div",
        "text": "Buy Pro",
        "role": "div",
        "selector": ".block.font-mono.hover:text-amber-200",
        "classes": "block font-mono hover:text-amber-200",
        "href": "",
        "raw_href": "",
        "id": "",
        "aria_label": "",
    }
    locator = build_robust_locator(element)
    assert locator == ".block.font-mono.hover\\:text-amber-200"
    html = '<div class="block font-mono hover:text-amber-200">X</div>'
    assert len(BeautifulSoup(html, "html.parser").select(locator)) == 1


def test_robust_locator_selector_fallback_keeps_escaped_tokens() -> None:
    """Without a classes key, escaped tokens survive selector re-extraction."""
    element = {
        "tag": "h2",
        "text": "Regulated buyer",
        "role": "h2",
        "selector": ".\\000033xl\\:flex.items-center",
        "classes": "",
        "href": "",
        "raw_href": "",
        "id": "",
        "aria_label": "",
    }
    locator = build_robust_locator(element)
    assert locator == "h2.\\000033xl\\:flex.items-center"


# ── build_robust_locator: hrefs ──────────────────────────────────────────────


def test_robust_locator_absolute_href_keeps_full_url() -> None:
    element = {
        "tag": "a",
        "text": "Egress Audit",
        "role": "a",
        "selector": 'a[href="https://github.com/tancat-ai/tancat/blob/main/docs/security/egress-audit.md"]',
        "classes": "font-bold",
        "href": "https://github.com/tancat-ai/tancat/blob/main/docs/security/egress-audit.md",
        "raw_href": "https://github.com/tancat-ai/tancat/blob/main/docs/security/egress-audit.md",
        "id": "",
        "aria_label": "",
    }
    assert (
        build_robust_locator(element)
        == 'a[href="https://github.com/tancat-ai/tancat/blob/main/docs/security/egress-audit.md"]'
    )


def test_robust_locator_relative_href_prefers_raw_attribute() -> None:
    """The normalised absolute URL never matches a relative attribute value.

    The raw attribute (as written in the markup) is what a[href=...] must
    carry (B-065).
    """
    element = {
        "tag": "a",
        "text": "About",
        "role": "a",
        "selector": ".about-link",
        "classes": "about-link",
        "href": "https://example.com/about",
        "raw_href": "/about",
        "id": "",
        "aria_label": "",
    }
    locator = build_robust_locator(element)
    assert locator is not None
    assert locator == 'a[href="/about"]'
    html = '<a href="/about" class="about-link">About</a>'
    assert len(BeautifulSoup(html, "html.parser").select(locator)) == 1


def test_robust_locator_href_from_selector_regex_wins() -> None:
    element = {
        "tag": "a",
        "text": "Cart",
        "role": "a",
        "selector": 'a[href="/view_cart"]',
        "classes": "cart-link",
        "href": "https://example.com/view_cart",
        "raw_href": "/view_cart",
        "id": "",
        "aria_label": "",
    }
    assert build_robust_locator(element) == 'a[href="/view_cart"]'


def test_robust_locator_mailto_href_emits_matchable_selector() -> None:
    element = {
        "tag": "a",
        "text": "hello",
        "role": "a",
        "selector": ".mail-link",
        "classes": "mail-link",
        "href": "",
        "raw_href": "mailto:hello@tancat.dev",
        "id": "",
        "aria_label": "",
    }
    assert build_robust_locator(element) == 'a[href="mailto:hello@tancat.dev"]'
