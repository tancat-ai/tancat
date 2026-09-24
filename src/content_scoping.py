"""Element-kind scoping for content criteria (B-092).

A criterion that names an **image** ("the hero product screenshot", "the Noir
Art image") must resolve to an ``<img>``; a criterion that names a **headline**
must resolve to a heading. Session 7 measured the defect: "hero headline
visible" resolved to a hero paragraph, and "Noir Art image" resolved to the tab
button — the emitted assertion checked the wrong node.

The helpers here keep content-resolution criteria inside the right candidate
set and reject a resolution whose element kind contradicts the criterion, so
the pipeline skips honestly instead of checking the wrong element.
"""

from __future__ import annotations

import re
from typing import Any

#: Page-level scans start with these — they are owned by the count/page-fact
#: classifier, not by element resolution.
_PAGE_LEVEL_PREFIXES: tuple[str, ...] = ("no ", "all ", "every ", "none ")

#: Nouns that name an image asset.
_IMAGE_NOUNS: tuple[str, ...] = (
    "image",
    "images",
    "img",
    "imgs",
    "screenshot",
    "screenshots",
    "artwork",
    "photo",
    "photos",
    "picture",
    "pictures",
    "thumbnail",
    "thumbnails",
    "logo",
    "logos",
)

#: Nouns that name a heading.
_HEADING_NOUNS: tuple[str, ...] = (
    "headline",
    "headlines",
    "heading",
    "headings",
    "title",
    "titles",
)


def _lowered(description: str) -> str:
    return description.replace("_", " ").strip().lower()


def _has_noun(lowered: str, nouns: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(noun)}\b", lowered) for noun in nouns)


def is_image_criterion(description: str) -> bool:
    """Return True when the ASSERT description checks an image.

    "Noir Art image" → True. "hero product screenshot natural width" → True.
    "all images have alt" → False (a page-level scan, owned by the classifier).
    """
    lowered = _lowered(description)
    if not lowered or lowered.startswith(_PAGE_LEVEL_PREFIXES):
        return False
    if "natural width" in lowered or "broken image" in lowered:
        return True
    return _has_noun(lowered, _IMAGE_NOUNS)


def is_heading_criterion(description: str) -> bool:
    """Return True when the ASSERT description checks a heading.

    "hero headline visible" → True. "How It Works section" → False.
    """
    lowered = _lowered(description)
    if not lowered or lowered.startswith(_PAGE_LEVEL_PREFIXES):
        return False
    return _has_noun(lowered, _HEADING_NOUNS)


def is_image_element(element: dict[str, Any] | None) -> bool:
    """Return True when the scraped element is an ``<img>``."""
    if not element:
        return False
    tag = str(element.get("tag", "")).strip().lower()
    if tag == "img":
        return True
    role = str(element.get("role", "")).strip().lower()
    computed_role = str(element.get("computed_role", "")).strip().lower()
    if role == "img" or computed_role == "img":
        return True
    return str(element.get("selector", "")).strip().lower().startswith("img")


def is_heading_element(element: dict[str, Any] | None) -> bool:
    """Return True when the scraped element is a heading (h1–h6)."""
    if not element:
        return False
    tag = str(element.get("tag", "")).strip().lower()
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return True
    role = str(element.get("role", "")).strip().lower()
    computed_role = str(element.get("computed_role", "")).strip().lower()
    return role == "heading" or computed_role == "heading"


def kind_matches(description: str, element: dict[str, Any] | None) -> bool:
    """Return True when the element's kind is compatible with the criterion.

    An image criterion must resolve to an image; a heading criterion to a
    heading. Descriptions that name neither kind always pass.
    """
    if is_image_criterion(description) and not is_image_element(element):
        return False
    if is_heading_criterion(description) and not is_heading_element(element):
        return False
    return True


def scope_pages_to_images(
    action: str,
    description: str,
    pages_data: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Narrow an image criterion's candidate set to ``<img>`` elements.

    Returns ``pages_data`` unchanged when the description is not an image
    criterion or when no page has any image (a hard filter to an empty set
    would hide a genuinely absent image behind the same miss).
    """
    if action != "ASSERT" or not is_image_criterion(description):
        return pages_data
    scoped = {
        url: [element for element in elements if is_image_element(element)] for url, elements in pages_data.items()
    }
    if any(scoped.values()):
        return scoped
    return pages_data


def scope_pages_to_headings(
    action: str,
    description: str,
    pages_data: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Narrow a heading criterion's candidate set to heading elements.

    A "headline" criterion is scoped to ``h1`` specifically (the hero
    headline); a generic "heading" criterion to ``h1``–``h6``.
    """
    if action != "ASSERT" or not is_heading_criterion(description):
        return pages_data
    allowed = {"h1"} if "headline" in _lowered(description) else {"h1", "h2", "h3", "h4", "h5", "h6"}
    scoped = {
        url: [element for element in elements if str(element.get("tag", "")).strip().lower() in allowed]
        for url, elements in pages_data.items()
    }
    if any(scoped.values()):
        return scoped
    return pages_data


__all__ = [
    "is_heading_criterion",
    "is_heading_element",
    "is_image_criterion",
    "is_image_element",
    "kind_matches",
    "scope_pages_to_headings",
    "scope_pages_to_images",
]
