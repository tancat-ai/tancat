"""Helpers for tests that exercise PlaceholderResolver without dead pipeline methods."""

from __future__ import annotations

from typing import Any

from src.locator_builder import build_robust_locator
from src.placeholder_resolver import PlaceholderResolver


def best_ranked_element(
    resolver: PlaceholderResolver,
    action: str,
    description: str,
    page_elements: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the top-ranked element from ``rank_candidates`` (live pipeline scoring)."""
    ranked = resolver.rank_candidates(action, description, page_elements)
    if not ranked:
        return None
    return ranked[0][1]


def resolve_placeholders(
    resolver: PlaceholderResolver,
    placeholders: list[tuple[str, str]],
    pages_data: dict[str, list[dict[str, Any]]],
) -> list[str]:
    """Resolve placeholders the same way the live pipeline builds selectors."""
    resolutions: list[str] = []
    skip_msg = "pytest.skip(\"Locator for '{desc}' not found on scraped pages.\")"

    for action, description in placeholders:
        if action in {"GOTO", "URL"}:
            url = resolver.resolve_url(description, pages_data)
            if url:
                resolutions.append(repr(url))
                continue
            resolutions.append(skip_msg.format(desc=description))
            continue

        all_ranked: list[tuple[int, dict[str, Any]]] = []
        for elements in pages_data.values():
            all_ranked.extend(resolver.rank_candidates(action, description, elements))

        if not all_ranked:
            resolutions.append(skip_msg.format(desc=description))
            continue

        all_ranked.sort(key=lambda item: item[0], reverse=True)
        best = all_ranked[0][1]
        selector = build_robust_locator(best) or str(best.get("selector", "")).strip()
        if selector:
            resolutions.append(repr(selector))
        else:
            resolutions.append(skip_msg.format(desc=description))

    return resolutions
