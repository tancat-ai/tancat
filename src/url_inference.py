"""URL transition inference for journey-aware placeholder resolution.

Extracted from placeholder_orchestrator.py to separate URL inference
into its own independently testable module.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


def infer_next_page_url(
    action: str,
    description: str,
    matched_element: dict[str, str],
    scraped_data: dict[str, list[dict[str, str]]],
    current_url: str | None,
) -> str | None:
    """Infer the next active page after a resolved step when navigation is implied."""
    href = str(matched_element.get("href", "")).strip()
    if action == "CLICK" and href:
        if href.startswith(("http://", "https://")):
            return href
        if current_url:
            return urljoin(current_url, href)
        return href

    if action == "CLICK":
        inferred = _infer_click_transition_url(description, matched_element, scraped_data, current_url)
        if inferred:
            return inferred

    lowered_description = description.replace("_", " ").lower()
    if action == "CLICK" and "add" in lowered_description and "cart" in lowered_description:
        return None

    is_navigation_click = any(
        term in lowered_description for term in ("link", "icon", "go to", "open", "navigate", "checkout", "home")
    )
    if (
        action == "CLICK"
        and is_navigation_click
        and any(term in lowered_description for term in ("cart", "checkout", "product", "home"))
    ):
        from src.placeholder_resolver import PlaceholderResolver

        resolver = PlaceholderResolver()
        return resolver.resolve_url(description, scraped_data)

    return None


def _infer_click_transition_url(
    description: str,
    matched_element: dict[str, str],
    scraped_data: dict[str, list[dict[str, str]]],
    current_url: str | None,
) -> str | None:
    """Infer common URL transitions for buttons that navigate without hrefs."""
    desc_lower = description.lower()
    selector_lower = str(matched_element.get("selector", "")).lower()
    id_lower = str(matched_element.get("id", "")).lower()
    data_test_lower = str(matched_element.get("data_test", "")).lower()
    haystack = " ".join([desc_lower, selector_lower, id_lower, data_test_lower])

    if "login" in haystack:
        return _find_discovered_url(scraped_data, ("inventory", "products"))

    if "checkout" in haystack:
        return _find_discovered_url(
            scraped_data,
            ("checkout-step-one", "checkout_step_one", "checkout"),
        )

    if "continue" in haystack and current_url and "checkout-step-one" in current_url:
        return _find_discovered_url(
            scraped_data,
            ("checkout-step-two", "checkout_step_two", "checkout-overview"),
        )

    if "finish" in haystack:
        return _find_discovered_url(
            scraped_data,
            ("checkout-complete", "complete", "thank"),
        )

    return None


def _find_discovered_url(
    scraped_data: dict[str, list[dict[str, str]]],
    preferred_terms: tuple[str, ...],
) -> str | None:
    """Return the best discovered URL containing one of the preferred terms."""
    candidates: list[tuple[int, int, str]] = []
    for url, elements in scraped_data.items():
        lowered_url = url.lower()
        for priority, term in enumerate(preferred_terms):
            if term in lowered_url:
                candidates.append((priority, -len(elements), url))
                break
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]
