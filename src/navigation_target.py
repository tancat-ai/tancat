"""Known navigation targets (B-093 gate 1, t-0847).

A navigation step (a GOTO, or a step whose description means "go to page X")
only means something when its destination is KNOWN:

* the real ``href`` of a hyperlink on the page the cursor is on, or
* a URL the human gave us (the story's own target URLs), or
* a page the pipeline scraped whose identity matches the description.

When the destination is unknown the step is an honest unresolved. A guess
would resolve the step against the stale page and move the cursor to a page
nobody ever saw - which is how a journey ends up clicking the burger menu
for "Checkout".

The helper is the human-practice half of the rule: when the current page
carries a link that names the destination ("cart icon" -> the cart link),
that link is the target. The human clicks it; the resolver follows it.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

__all__ = [
    "find_navigation_anchor",
    "identity_words",
    "is_anchor",
    "names_start_page",
    "start_page_url",
    "target_words",
]


#: Words that carry no target identity. "go to the shopping cart page" says
#: "cart"; the rest is grammar. They are stripped before matching so a
#: navigation phrase still names one element.
_NOISE_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "at",
        "click",
        "go",
        "goto",
        "in",
        "into",
        "link",
        "links",
        "my",
        "navigate",
        "navigation",
        "of",
        "on",
        "open",
        "page",
        "pages",
        "the",
        "to",
        "view",
    }
)

#: Anchor roles: an element that navigates when it is clicked.
_ANCHOR_ROLES: frozenset[str] = frozenset({"a", "link"})

#: Href schemes that never navigate to another page of the site.
_NON_NAVIGABLE_PREFIXES: tuple[str, ...] = ("#", "javascript:", "mailto:", "tel:")


def _words(text: str) -> set[str]:
    """Return the lowercased word set of *text* (2+ characters only)."""
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
    return {word for word in cleaned.split() if len(word) >= 2}


def target_words(description: str) -> set[str]:
    """Return the identity words of a navigation description.

    Grammar words ("go to the ... page") are dropped; when that would empty
    the set the raw words are kept, so "page" still names something.
    """
    words = _words(description)
    if not words:
        return set()
    stripped = {word for word in words if word not in _NOISE_WORDS}
    return stripped or words


def is_anchor(element: dict[str, Any]) -> bool:
    """True when *element* is a hyperlink (an anchor, or an element with a link role)."""
    tag = str(element.get("tag", "")).strip().lower()
    role = str(element.get("role", "")).strip().lower()
    return tag == "a" or role in _ANCHOR_ROLES


def identity_words(element: dict[str, Any]) -> set[str]:
    """Return the words that name *element* - what a human would read on it.

    Visible text, the accessible name, the aria-label, the data attributes
    and the href path. A cart link whose icon has no text is still named
    "cart" by its ``data-test`` and its href.
    """
    words: set[str] = set()
    for key in ("text", "accessible_name", "aria_label", "title", "alt", "data_test", "classes", "id", "name"):
        value = str(element.get(key) or "").strip()
        if value:
            words |= _words(value)
    href = str(element.get("raw_href") or element.get("href") or "").strip()
    if href and not href.startswith(_NON_NAVIGABLE_PREFIXES):
        path = urlparse(href).path
        words |= _words(path.replace("/", " ").replace("-", " ").replace("_", " ").replace(".", " "))
    return words


def find_navigation_anchor(description: str, elements: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the hyperlink on this page that names *description*.

    Only anchors are considered: a navigation step is performed by clicking
    a link, and a button with the same words is a different action ("add to
    cart" is not "the cart page"). The anchor must cover every identity word
    of the description - a partial overlap names a different thing.
    """
    words = target_words(description)
    if not words:
        return None
    best: dict[str, Any] | None = None
    best_score = 0.0
    for element in elements:
        if not is_anchor(element):
            continue
        if element.get("is_visible") is False:
            continue
        identity = identity_words(element)
        if not identity:
            continue
        covered = words & identity
        if not covered:
            continue
        score = len(covered) / len(words)
        if score > best_score:
            best_score = score
            best = element
    return best if best_score >= 1.0 else None


#: Words that name the entry page - the URL the human gave us as the start.
_START_PAGE_WORDS: frozenset[str] = frozenset({"home", "homepage", "start", "landing"})

#: The root-path guard of ``PlaceholderResolver.resolve_url``: only a
#: start-page word may name a URL whose path is the site root.
_ROOT_PAGE_WORDS: frozenset[str] = frozenset({"home", "start", "landing", "store"})


def names_start_page(description: str) -> bool:
    """True when *description* names the entry page ("home", "start page")."""
    return bool(target_words(description) & _START_PAGE_WORDS)


def start_page_url(description: str, seed_url: str | None) -> str | None:
    """Return the entry page when *description* names it, else ``None``.

    The entry page is the URL the human gave us. A mock site that lives at
    ``/index.html`` is still the start page, so the word "home" names it
    even though its path is not the site root.
    """
    if not seed_url or not names_start_page(description):
        return None
    path = urlparse(seed_url).path
    if not path.strip("/"):
        # A root URL also answers to the root guard's words.
        return seed_url if target_words(description) & (_START_PAGE_WORDS | _ROOT_PAGE_WORDS) else None
    return seed_url
