"""Pure URL manipulation helpers extracted from TestOrchestrator."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


def normalize_url_path(url: str) -> str:
    """Normalize common LLM-generated URL path variations to real site routes.

    Handles patterns like ``category-product``, ``categoryproduct``, and
    ``category_product`` mapping to ``category_products``.
    """
    if not url:
        return url

    normalized = url
    normalized = re.sub(r"category-product", "category_products", normalized)
    normalized = re.sub(r"/categoryproduct(?=/|$)", "/category_products", normalized)
    normalized = re.sub(r"/category_product(?:\.php)?(?=/|$)", "/category_products", normalized)
    normalized = re.sub(r"product-details", "product_details", normalized)
    normalized = re.sub(r"\.php(?=/|$)", "", normalized)
    normalized = re.sub(r"contact-us", "contact_us", normalized)
    return normalized


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
    """URL guessing removed — journey discovery finds all reachable pages.

    This function is kept as a stub for backwards compatibility but returns
    an empty list. The journey scraper navigates the site statefully,
    capturing all pages and elements without guessing URL patterns.
    """
    return []


def heuristic_url_from_description(current_url: str, description: str) -> str | None:
    """Best-effort URL guess when we haven't scraped links yet.

    Returns multiple candidates as a list to allow fallback attempts.
    """
    base_url = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}/"
    lowered = description.lower().strip()

    if any(term in lowered for term in ("product", "products", "shop", "store", "catalog")):
        # Return multiple common product page URL patterns
        return urljoin(base_url, "products")  # primary fallback; caller should try others

    if "cart" in lowered or "basket" in lowered:
        return urljoin(base_url, "view_cart")  # primary fallback

    if "checkout" in lowered or "check out" in lowered:
        return urljoin(base_url, "checkout")  # primary fallback

    return None
