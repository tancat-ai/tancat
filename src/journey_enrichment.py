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
    """Check runtime visibility of each scraped element, and where it sits.

    Records, per element:

    - ``is_visible`` - Playwright's answer for the element itself;
    - ``overlay_container`` - a stable key for the nearest overlay container, or
      None. Empty when the element is page content;
    - ``overlay_kind`` - ``"dialog"`` or ``"banner"`` for an overlay container;
    - ``in_overlay`` - the FIRST answer to "is this an obstacle?": True for any
      overlay container, None when the question could not be evaluated (a
      Playwright-only selector that the browser-side probe cannot read and the
      per-element fallback could not resolve either).

    ``in_overlay`` is only the first answer for a dialog: a dialog the click
    OPENED holds the confirmation the criterion names, and the orchestrator flips
    its verdict to False once it can compare the page before the click with the
    page after it (``PlaceholderOrchestrator._mark_landing_overlays``, t-1251). A
    banner keeps its True - nobody opens a cookie banner on purpose in a journey.
    """
    overlay = _overlay_membership(page, elements)
    for index, elem in enumerate(elements):
        if index < len(overlay):
            container, kind, known = overlay[index]
            elem["overlay_container"] = container
            elem["overlay_kind"] = kind
            elem["in_overlay"] = None if not known else container is not None
        selector = elem.get("selector")
        if not selector:
            continue
        try:
            loc = page.locator(selector).first
            elem["is_visible"] = loc.is_visible()
        except Exception:
            pass  # Keep default is_visible value on lookup failure
    return elements


def _overlay_membership(
    page: Any,
    elements: list[dict[str, Any]],
) -> list[tuple[str | None, str | None, bool]]:
    """Return per-element ``(container_key, kind, known)``, best effort.

    One DOM pass for every plain-CSS selector (a round-trip per element would be
    paid on every scrape). A selector using Playwright-only syntax - ``:has-text``,
    ``:visible``, ``>>`` - cannot be read by ``document.querySelector``, so it is
    resolved through Playwright for that element alone; if that fails too the
    element is marked ``known=False`` rather than silently reported as "not in an
    overlay" (t-1251, fix 3).
    """
    from src.browser_utils import (
        OVERLAY_BANNER_SELECTOR,
        OVERLAY_DIALOG_SELECTOR,
        OVERLAY_MEMBERSHIP_SELECTOR,
        PLAYWRIGHT_ONLY_SELECTOR_MARKERS,
    )

    selectors = [str(elem.get("selector", "") or "") for elem in elements]
    if not selectors:
        return []
    plain = [s and not any(marker in s for marker in PLAYWRIGHT_ONLY_SELECTOR_MARKERS) for s in selectors]
    results: list[tuple[str | None, str | None, bool]] = [(None, None, False) for _ in selectors]
    try:
        rows = page.evaluate(
            """
            ([selectors, membership, dialogs, banners]) => selectors.map((selector) => {
                if (!selector) { return { key: null, kind: null }; }
                const el = document.querySelector(selector);
                if (!el) { return { key: null, kind: null }; }
                const container = el.closest(membership);
                if (!container) { return { key: null, kind: null }; }
                const key = container.id
                    ? '#' + container.id
                    : ((container.classList && container.classList.length)
                        ? '.' + container.classList[0]
                        : container.tagName.toLowerCase());
                const kind = container.matches(banners) ? 'banner'
                    : (container.matches(dialogs) ? 'dialog' : 'banner');
                return { key: key, kind: kind };
            })
            """,
            [
                [s if ok else "" for s, ok in zip(selectors, plain, strict=True)],
                OVERLAY_MEMBERSHIP_SELECTOR,
                OVERLAY_DIALOG_SELECTOR,
                OVERLAY_BANNER_SELECTOR,
            ],
        )
    except Exception:
        rows = None
    if isinstance(rows, list):
        for index, row in enumerate(rows[: len(results)]):
            if not plain[index]:
                continue  # resolved per element below
            key = row.get("key") if isinstance(row, dict) else None
            kind = row.get("kind") if isinstance(row, dict) else None
            results[index] = (str(key) if key else None, str(kind) if kind else None, True)

    for index, selector in enumerate(selectors):
        if plain[index]:
            continue
        if not selector:
            results[index] = (None, None, True)
            continue
        results[index] = _overlay_membership_one(
            page, selector, OVERLAY_MEMBERSHIP_SELECTOR, OVERLAY_DIALOG_SELECTOR, OVERLAY_BANNER_SELECTOR
        )
    return results


def _overlay_membership_one(
    page: Any,
    selector: str,
    membership: str,
    dialogs: str,
    banners: str,
) -> tuple[str | None, str | None, bool]:
    """Resolve ONE Playwright-only selector and ask the same question of its DOM.

    Playwright finds the element (``:has-text``, ``:visible`` and ``>>`` are its own
    syntax); the membership walk is plain CSS, which runs in the page. Any failure
    returns ``known=False`` - "could not be evaluated", never a silent "no".
    """
    try:
        locator = page.locator(selector).first
        if locator.count() == 0:
            return (None, None, True)  # the element is not on the page: no overlay
        found = locator.evaluate(
            """
            (el, selectors) => {
                const [membership, dialogs, banners] = selectors;
                const container = el.closest(membership);
                if (!container) { return null; }
                const key = container.id
                    ? '#' + container.id
                    : ((container.classList && container.classList.length)
                        ? '.' + container.classList[0]
                        : container.tagName.toLowerCase());
                return { key: key, kind: container.matches(banners) ? 'banner'
                    : (container.matches(dialogs) ? 'dialog' : 'banner') };
            }
            """,
            [membership, dialogs, banners],
        )
    except Exception:
        return (None, None, False)
    if not isinstance(found, dict):
        return (None, None, True)
    key = found.get("key")
    kind = found.get("kind")
    return (str(key) if key else None, str(kind) if kind else None, True)


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
