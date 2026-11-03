"""Enrichment helpers for journey scraping — consistent scrape quality.

Extracted from ``journey_scraper.py``. Reused by both ``JourneyScraper``
and ``journey_executor`` to match the same enrichment pipeline (visibility
checks + accessibility snapshot via CDP).
"""

from __future__ import annotations

from typing import Any


def capture_element_visibility_sync(
    page: Any,
    elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check runtime visibility of each scraped element using Playwright is_visible().

    Also records ``in_overlay``: True when the element sits inside a consent
    banner, promo or modal container (``OVERLAY_CONTAINER_SELECTOR``). d-0112:
    the post-click look is taken BEFORE those are dismissed - deliberately, so a
    confirmation modal the click opened is not recorded as closed - so an overlay
    control lands in the landing pool. The marker lets the matcher tell an overlay
    from the page content; it changes nothing about what is scraped.
    """
    overlay_flags = _overlay_membership(page, elements)
    for index, elem in enumerate(elements):
        selector = elem.get("selector")
        if index < len(overlay_flags):
            elem["in_overlay"] = overlay_flags[index]
        if not selector:
            continue
        try:
            loc = page.locator(selector).first
            elem["is_visible"] = loc.is_visible()
        except Exception:
            pass  # Keep default is_visible value on lookup failure
    return elements


def _overlay_membership(page: Any, elements: list[dict[str, Any]]) -> list[bool]:
    """Return per-element overlay membership in ONE DOM pass, best effort.

    One evaluate for the whole page: probing each element separately would add a
    round-trip per element to every scrape. On any failure the list is empty and
    no element is marked - an unknown overlay is left as content, never guessed.
    """
    selectors = [str(elem.get("selector", "") or "") for elem in elements]
    if not selectors:
        return []
    try:
        from src.browser_utils import OVERLAY_CONTAINER_SELECTOR

        flags = page.evaluate(
            """
            ([selectors, overlaySelector]) => selectors.map((selector) => {
                if (!selector) { return false; }
                try {
                    const el = document.querySelector(selector);
                    return el ? el.closest(overlaySelector) !== null : false;
                } catch (e) {
                    return false;
                }
            })
            """,
            [selectors, OVERLAY_CONTAINER_SELECTOR],
        )
    except Exception:
        return []
    if not isinstance(flags, list):
        return []
    return [bool(flag) for flag in flags]


def capture_a11y_snapshot_sync(
    context: Any,
    page: Any,
) -> dict[str, Any] | None:
    """Capture accessibility snapshot via CDP. Returns None if unavailable."""
    try:
        cdp_session = context.new_cdp_session(page)
    except Exception:
        return None

    a11y_snapshot: dict[str, Any] = {"nodes": []}
    try:
        tree_response = cdp_session.send("Accessibility.getFullAXTree")
        a11y_snapshot["nodes"] = tree_response.get("nodes", []) if isinstance(tree_response, dict) else []
    except Exception:
        pass  # Return empty nodes list on CDP failure

    try:
        cdp_session.detach()
    except Exception:
        pass

    return a11y_snapshot


__all__ = [
    "capture_a11y_snapshot_sync",
    "capture_element_visibility_sync",
]
