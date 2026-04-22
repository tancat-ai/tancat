"""Pure URL manipulation helpers extracted from TestOrchestrator."""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


def extract_seed_domain(seed_urls: list[str]) -> set[str]:
    """Extract normalized domain strings from seed URLs for validation."""
    domains: set[str] = set()
    for url in seed_urls:
        parsed = urlparse(url)
        domains.add(parsed.netloc.lower())
    return domains


def filter_urls_to_allowed_domain(urls: list[str], allowed_domains: set[str]) -> list[str]:
    """Filter URLs to only those sharing an allowed domain (or subdomain thereof).

    This prevents the LLM from hallucinating URLs that point to completely
    unrelated websites (e.g. ``https://www.youtube.com/c/AutomationExercise``
    when the seed URL is ``https://automationexercise.com/``).
    """
    filtered: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        # Allow exact domain match or subdomain match (e.g. sub.automationexercise.com)
        if netloc in allowed_domains or any(netloc.endswith(f".{domain}") for domain in allowed_domains):
            filtered.append(url)
        else:
            logger.warning(
                "Skipping URL with disallowed domain '%s' (allowed: %s). "
                "The LLM may have hallucinated an incorrect URL.",
                netloc,
                allowed_domains,
            )
    return filtered


def extract_route_concepts(texts: list[str]) -> set[str]:
    """Return high-level page journey concepts mentioned by the requirements."""
    combined_text = " ".join(text.lower() for text in texts if text)
    concepts: set[str] = {"home"}

    if any(term in combined_text for term in ("product", "products", "item", "catalog", "shop", "store")):
        concepts.add("products")
    if "cart" in combined_text or "basket" in combined_text:
        concepts.add("cart")
    if any(term in combined_text for term in ("checkout", "check out", "place order", "payment", "order")):
        concepts.add("checkout")

    return concepts


def build_common_path_candidates(seed_urls: list[str], concepts: set[str]) -> list[str]:
    """Construct common route URLs from the supplied starting pages."""
    candidates: list[str] = []
    if not seed_urls:
        return candidates

    for seed_url in seed_urls:
        parsed = urlparse(seed_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}/"
        if "products" in concepts:
            candidates.append(urljoin(base_url, "products"))
        if "cart" in concepts:
            candidates.append(urljoin(base_url, "view_cart"))
        if "checkout" in concepts:
            candidates.append(urljoin(base_url, "checkout"))

    return list(dict.fromkeys(candidates))


def heuristic_url_from_description(current_url: str, description: str) -> str | None:
    """Best-effort URL guess when we haven't scraped links yet."""
    base_url = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}/"
    lowered = description.lower().strip()
    if any(term in lowered for term in ("product", "products", "shop", "store", "catalog")):
        return urljoin(base_url, "products")
    if "cart" in lowered or "basket" in lowered:
        return urljoin(base_url, "view_cart")
    if "checkout" in lowered or "check out" in lowered:
        return urljoin(base_url, "checkout")
    return None
