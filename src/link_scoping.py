"""Link-criterion scoping (B-088).

A criterion that names a **link** and asks whether it resolves must resolve to
the anchor itself — never to a container, span or paragraph that merely
mentions the link text. Session 7 measured the defect twice:

- "Security Policy link resolves" resolved to a ``<span>`` whose text is
  "Security Policy" (a non-anchor), so ``assert_attribute(..., 'href')``
  failed on an element that has no href — a false red.
- "Watch 3-Min Walkthrough link resolves" resolved to the nav-logo anchor
  (``a[href="#"]``) because the named link no longer exists — a wrong-element
  green/red instead of an honest skip.

The helpers here keep link-resolution criteria inside the anchor candidate set
and reject a resolution whose element shares no distinctive token with the
named link, so the pipeline skips honestly instead of checking the wrong node.
"""

from __future__ import annotations

import re
from typing import Any

#: Words that carry no element-identity signal in a link-resolution criterion.
_LINK_CRITERION_GENERIC: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "link",
        "links",
        "anchor",
        "anchors",
        "href",
        "hrefs",
        "url",
        "urls",
        "resolve",
        "resolves",
        "resolving",
        "resolved",
        "return",
        "returns",
        "returning",
        "not",
        "no",
        "does",
        "do",
        "404",
        "valid",
        "live",
        "correct",
        "working",
        "broken",
        "should",
        "must",
        "point",
        "points",
        "at",
        "to",
        "of",
        "in",
        "on",
        "for",
        "and",
        "or",
        "is",
        "are",
        "be",
        "its",
        "it",
        "that",
        "this",
        "page",
        "footer",
        "header",
        "nav",
        "navigation",
        "section",
        "without",
        "new",
        "tab",
        "same",
        "destination",
        "button",
        "buttons",
        "video",
        "image",
        "photo",
    }
)

#: Page-level scans start with these — they are owned by the count classifier
#: (``count_assertion_from_description``), not by element resolution.
_PAGE_LEVEL_PREFIXES: tuple[str, ...] = ("no ", "all ", "every ", "none ")


def is_link_criterion(description: str) -> bool:
    """Return True when the ASSERT description checks a URL-bearing attribute.

    "Security Policy link resolves" → True.
    "Watch 3-Min Walkthrough live video URL" → True (the emitted check reads an
    href even though the skeleton dropped the word "link").
    "no TBD in hrefs" → False (a page-level scan, owned by the count classifier).
    "Air-Gap / Defense tier" → False (no resolution signal).
    """
    lowered = description.replace("_", " ").strip().lower()
    if not lowered or lowered.startswith(_PAGE_LEVEL_PREFIXES):
        return False
    has_signal = any(term in lowered for term in ("resolv", "404", "href", "url", "valid", "mailto"))
    if not has_signal:
        return False
    # A link noun or a URL-bearing target — both resolve to an href read. A
    # document/<head> criterion can also match here; that is harmless because
    # the emit chokepoint's document classifier always wins, and the match errs
    # towards a skip rather than a wrong-element assertion.
    return any(term in lowered for term in ("link", "anchor", "href", "url", "mailto", "video"))


def is_anchor(element: dict[str, Any] | None) -> bool:
    """Return True when the element is an anchor (or carries an href)."""
    if not element:
        return False
    tag = str(element.get("tag", "")).strip().lower()
    if tag == "a":
        return True
    role = str(element.get("role", "")).strip().lower()
    computed_role = str(element.get("computed_role", "")).strip().lower()
    if role in {"a", "link"} or computed_role == "link":
        return True
    if str(element.get("raw_href", "")).strip() or str(element.get("href", "")).strip():
        return True
    return "[href" in str(element.get("selector", "")).lower()


def link_name_tokens(description: str) -> tuple[str, ...]:
    """Return the distinctive tokens of the link name in a criterion.

    "Watch 3-Min Walkthrough link resolves" → ("watch", "3-min", "walkthrough").
    """
    lowered = description.replace("_", " ").lower()
    tokens: list[str] = []
    for word in re.split(r"[^a-z0-9@./\-]+", lowered):
        if not word or word in _LINK_CRITERION_GENERIC:
            continue
        if len(word) < 3 and not any(ch.isdigit() for ch in word):
            continue
        tokens.append(word)
    return tuple(dict.fromkeys(tokens))


def link_name_matches(description: str, element: dict[str, Any] | None) -> bool:
    """Return True when the element plausibly is the link named by the criterion.

    A criterion with no distinctive link tokens passes (nothing to verify). A
    criterion that names a link must see at least one token in the element's
    text / aria-label / id / href / selector — otherwise the resolver picked a
    lookalike and the caller should skip honestly.
    """
    tokens = link_name_tokens(description)
    if not tokens:
        return True
    if not element:
        return False
    haystack = " ".join(
        str(element.get(key, ""))
        for key in ("text", "aria_label", "accessible_name", "name", "id", "raw_href", "href", "selector")
    ).lower()
    return any(token in haystack for token in tokens)


def scope_pages_to_links(
    action: str,
    description: str,
    pages_data: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Narrow a link-resolution criterion's candidate set to anchor elements.

    Returns ``pages_data`` unchanged when the description is not a
    link-resolution criterion or when no page has any anchor (a hard filter to
    an empty set would hide a genuinely absent link behind the same miss).
    """
    if action != "ASSERT" or not is_link_criterion(description):
        return pages_data
    scoped = {url: [element for element in elements if is_anchor(element)] for url, elements in pages_data.items()}
    if any(scoped.values()):
        return scoped
    return pages_data


__all__ = [
    "is_anchor",
    "is_link_criterion",
    "link_name_matches",
    "link_name_tokens",
    "scope_pages_to_links",
]
