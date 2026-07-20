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
    """Check runtime visibility of each scraped element using Playwright is_visible()."""
    for elem in elements:
        selector = elem.get("selector")
        if not selector:
            continue
        try:
            loc = page.locator(selector).first
            elem["is_visible"] = loc.is_visible()
        except Exception:
            pass  # Keep default is_visible value on lookup failure
    return elements


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
