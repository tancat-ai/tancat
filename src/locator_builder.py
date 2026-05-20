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


def _token_overlap(description_tokens: set[str], element_tokens: set[str]) -> float:
    """Compute Jaccard-like overlap between two token sets.

    Returns a value in [0, 1] representing how many description tokens
    are covered by the element tokens.
    """
    if not description_tokens or not element_tokens:
        return 0.0
    matches = len(description_tokens & element_tokens)
    union = len(description_tokens | element_tokens)
    return matches / union if union > 0 else 0.0


def build_selector_relaxed(description: str, page_elements: list[dict]) -> str | None:
    """Build a selector with relaxed matching criteria.

    Used as a fallback when the strict selector build fails.
    Relaxes: exact text match to partial match, requires all attributes to any attribute.

    This function uses a simple keyword-based approach: it tokenizes the
    description and scores elements by how many tokens appear in their text,
    attributes, or role. A lower confidence threshold (0.2) is used compared
    to strict matching (0.3).

    Args:
        description: Human-readable description of the target element
            (e.g., "cart link", "submit button").
        page_elements: List of element metadata dictionaries as returned
            by the scraper.

    Returns:
        A relaxed locator string, or None if no element meets the threshold.
    """
    tokens = set(description.lower().split())
    if not tokens or not page_elements:
        return None

    best_element: dict | None = None
    best_score: float = 0.0

    for elem in page_elements:
        # Build a token set from everything we know about this element
        elem_tokens: set[str] = set()
        for key in ("text", "aria_label", "role", "id", "classes"):
            value = str(elem.get(key, "")).lower()
            if value:
                elem_tokens.update(value.split())

        score = _token_overlap(tokens, elem_tokens)
        if score > best_score:
            best_score = score
            best_element = elem

    # Relaxed threshold: 0.2 (vs 0.3 strict)
    if best_score >= 0.2 and best_element is not None:
        return build_robust_locator(best_element)
    return None
