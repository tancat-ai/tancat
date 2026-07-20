"""ARIA role mapping and display-role filtering.

Extracted from ``placeholder_orchestrator.py``. Provides HTML-tag-to-ARIA-role
mapping and utilities for identifying display (non-interactive) elements,
used by the ASSERT resolution pipeline (B-016).
"""

from __future__ import annotations

import re

# B-016: Display roles for ASSERT role filtering.
# These are leaf-level ARIA roles that present information to the user.
# Interactive roles (button, link, textbox) are excluded — ASSERT descriptions
# like "cart badge" should not match cart links by keyword overlap.
DISPLAY_ROLES = frozenset(
    {
        "heading",
        "paragraph",
        "text",
        "status",
        "alert",
        "listitem",
        "cell",
        "columnheader",
        "rowheader",
        "image",
        "strong",
        "em",
        "caption",
        "figure",
        "label",  # <label> elements present form field descriptions
        "generic",  # <span>, <div> — common containers for text content
    }
)

# B-016: Maximum score gap between best display-role element and global top
# before we fall back to non-display elements. Tunable after UAT.
ROLE_FALLBACK_GAP = 3

# Implicit ARIA role mapping for HTML tags.
# Used when computed_role is unavailable (e.g. journey scraper enrichment fails).
_TAG_TO_ROLE: dict[str, str] = {
    "a": "link",
    "abbr": "text",
    "address": "paragraph",
    "article": "article",
    "aside": "complementary",
    "b": "strong",
    "bdi": "text",
    "bdo": "text",
    "blockquote": "blockquote",
    "button": "button",
    "caption": "caption",
    "cite": "text",
    "code": "text",
    "data": "text",
    "dd": "definition",
    "del": "deletion",
    "details": "group",
    "dfn": "text",
    "div": "generic",
    "dl": "list",
    "dt": "term",
    "em": "em",
    "embed": "embed",
    "fieldset": "group",
    "figure": "figure",
    "footer": "contentinfo",
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
    "header": "banner",
    "hr": "separator",
    "i": "em",
    "img": "image",
    "input": "textbox",  # simplified — type determines actual role
    "ins": "insertion",
    "kbd": "text",
    "label": "label",
    "legend": "legend",
    "li": "listitem",
    "main": "main",
    "mark": "text",
    "nav": "navigation",
    "ol": "list",
    "output": "status",
    "p": "paragraph",
    "picture": "generic",
    "pre": "text",
    "progress": "progressbar",
    "q": "text",
    "rb": "text",
    "rp": "text",
    "rt": "text",
    "rtc": "text",
    "ruby": "text",
    "s": "deletion",
    "samp": "text",
    "section": "region",
    "select": "listbox",  # simplified
    "small": "text",
    "span": "generic",
    "strong": "strong",
    "sub": "text",
    "sup": "text",
    "table": "table",
    "tbody": "rowgroup",
    "td": "cell",
    "textarea": "textbox",
    "tfoot": "rowgroup",
    "th": "columnheader",  # simplified — scope determines row/column
    "thead": "rowgroup",
    "time": "text",
    "tr": "row",
    "u": "text",
    "ul": "list",
    "var": "text",
}


def normalise_element_text(element: dict[str, str]) -> str:
    """Extract and normalise element text for Pass 1 matching.

    Priority: accessible_name → aria_label → text.
    Strips non-ASCII characters (icon fonts), lowercases,
    and strips whitespace.
    """
    raw = (element.get("accessible_name") or element.get("aria_label") or element.get("text", "")).strip()
    return re.sub(r"[^\x00-\x7f]", "", raw).strip().lower()


def get_effective_role(element: dict[str, str]) -> str:
    """Resolve ARIA role: computed_role (CDP AX tree) -> raw role (HTML attr/tag).

    B-016: computed_role is set by the accessibility enricher (AI-024) and
    contains the proper computed ARIA role. Falls back to the raw ``role``
    field which is the HTML role attribute or tag-name fallback.
    """
    return str(element.get("computed_role") or element.get("role", "")).strip().lower()


def is_display_role(element: dict[str, str], *, tag_to_role: dict[str, str] | None = None) -> bool:
    """Check if an element's effective role is a display (non-interactive) role.

    B-016: Used for ASSERT role filtering. Resolution priority:
    1. ``computed_role`` from CDP AX tree enrichment (authoritative when present)
    2. ``role`` field — if it's a known ARIA role name (not a tag name), use it
    3. ``tag`` field — mapped through implicit ARIA role table
    4. ``role`` field as tag name — mapped through implicit ARIA role table

    The scraper stores tag names in the ``role`` field when no explicit
    role attribute exists. The enricher writes ``computed_role`` from the
    AX tree but often fails to match elements, leaving it None.
    """
    if tag_to_role is None:
        tag_to_role = _TAG_TO_ROLE

    # 1. computed_role from CDP AX tree — authoritative
    computed = str(element.get("computed_role", "")).strip().lower()
    if computed:
        return computed in DISPLAY_ROLES

    # 2. raw role field — could be explicit ARIA role or tag-name fallback
    raw_role = str(element.get("role", "")).strip().lower()

    # 3. tag field if available
    tag = str(element.get("tag", "")).strip().lower()

    # Check if raw_role is an explicit ARIA role (not a tag name)
    if raw_role in DISPLAY_ROLES:
        return True

    # Map via tag name (tag field first, then role-as-tag fallback)
    effective_tag = tag if tag else raw_role
    mapped_role = tag_to_role.get(effective_tag, "")
    return mapped_role in DISPLAY_ROLES


__all__ = [
    "DISPLAY_ROLES",
    "ROLE_FALLBACK_GAP",
    "get_effective_role",
    "is_display_role",
    "normalise_element_text",
]
