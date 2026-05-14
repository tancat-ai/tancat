"""Build robust Playwright locators from scraped element metadata.

This module transforms brittle CSS selectors into stable, specific locators
by prioritizing ID > href > data-attrs > class > text > aria-label patterns.
"""

from __future__ import annotations

import re


def _css_escape_id(value: str) -> str:
    """Escape a value for safe use as a CSS ID selector."""
    return re.sub(r"[^a-zA-Z0-9_-]", r"\\\g<0>", value)


def build_robust_locator(element: dict) -> str | None:
    """Build a robust Playwright locator from scraped element metadata.

    Prefers stable, specific selectors (ID, href, data-attrs) over
    text-based locators when a stable selector is available.  Text-based
    locators are used as a fallback when no stable selector exists.

    Priority order (most specific first):
    1. ID-based (e.g. ``#buy``)
    2. href-based for links (e.g. ``a[href="/view_cart"]``)
    3. Data attribute with specific value (e.g. ``[data-product-id="1"]``)
    4. Class-based without brittle framework prefixes (e.g. ``.cart_description``)
    5. Tag + :has-text (e.g. ``a:has-text("Add to cart")``)
    6. Role + :has-text (e.g. ``button:has-text("Submit")``)
    7. Aria-label based (e.g. ``[aria-label="Submit"]``)
    8. None — falls back to raw selector

    Args:
        element: Dict with keys such as ``tag``, ``text``, ``role``,
            ``selector``, ``id``, ``aria_label``, ``classes``, ``href``.

    Returns:
        A robust locator string, or ``None`` if nothing stable can be built.
    """
    tag = str(element.get("tag", "")).strip().lower()
    text = str(element.get("text", "")).strip()
    role = str(element.get("role", "")).strip().lower()
    selector = str(element.get("selector", "")).strip()
    element_id = str(element.get("id", "")).strip()
    aria_label = str(element.get("aria_label", "")).strip()
    classes = str(element.get("classes", "")).strip().lower()
    href = str(element.get("href", "")).strip()

    # Strip common UI framework class prefixes that add no semantic value
    # e.g. "btn btn-default add-to-cart" -> useful parts: "add-to-cart"
    useful_class_terms = {
        term
        for term in classes.split()
        if term and not any(prefix in term for prefix in ("btn-", "fa-", "fas", "far", "bi-", "mdi-", "icon-", "css-"))
    }

    # Build tag prefix for the locator
    tag_prefix = tag if tag and tag not in ("div", "span", "a", "") else ""

    # Priority 1: ID-based locator (most stable)
    if element_id:
        return f"#{_css_escape_id(element_id)}"
    id_match = re.search(r"#([\w-]+)", selector)
    if id_match:
        return f"#{_css_escape_id(id_match.group(1))}"

    # Priority 2: href-based locator for anchor elements
    if role in ("a", "link"):
        href_match = re.search(r'\[href=["\']([^"\']+)["\']\]', selector)
        if href_match:
            escaped_href = href_match.group(1).replace('"', '\\"')
            return f'a[href="{escaped_href}"]'
        if href:
            escaped_href = href.replace('"', '\\"')
            return f'a[href="{escaped_href}"]'

    # Priority 3: Data attribute with specific value from the raw selector
    data_attr_matches = re.findall(r'\[data-([\w-]+)=["\']([^"\']+)["\']\]', selector)
    if data_attr_matches:
        data_parts = [f'[data-{attr_name}="{attr_value}"]' for attr_name, attr_value in data_attr_matches]
        if useful_class_terms:
            class_part = "." + ".".join(sorted(useful_class_terms))
            return class_part + "".join(data_parts)
        return "".join(data_parts)

    # Priority 4: Class-based without brittle framework prefixes
    selector_class_matches = re.findall(r"\.([\w-]+)", selector)
    if selector_class_matches:
        clean_classes = [
            c
            for c in selector_class_matches
            if not any(prefix in c for prefix in ("btn-", "fa-", "fas", "far", "bi-", "mdi-", "icon-", "css-"))
        ]
        if clean_classes:
            class_part = "." + ".".join(sorted(clean_classes))
            if tag_prefix:
                return f"{tag_prefix}{class_part}"
            return class_part

    if useful_class_terms:
        class_part = "." + ".".join(sorted(useful_class_terms))
        if tag_prefix:
            return f"{tag_prefix}{class_part}"
        return class_part

    # Priority 5: Text-based locator (fallback)
    if text:
        escaped_text = text.replace('"', '\\"')
        if tag_prefix:
            return f'{tag_prefix}:has-text("{escaped_text}")'
        if role and role not in ("", "div", "span"):
            return f'{role}:has-text("{escaped_text}")'
        return f':has-text("{escaped_text}")'

    # Priority 6: Aria-label based locator
    if aria_label:
        escaped_label = aria_label.replace('"', '\\"')
        if tag_prefix:
            return f'{tag_prefix}[aria-label="{escaped_label}"]'
        return f'[aria-label="{escaped_label}"]'

    return None
