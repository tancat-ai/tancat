"""Pure URL manipulation helpers extracted from TestOrchestrator."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


def is_stateful_cart_checkout_path(path: str) -> bool:
    """True when a URL path targets a cart/checkout page that needs session state.

    Site-agnostic: matches path tokens rather than an exact per-site vocabulary.
    automationexercise uses ``/view_cart`` / ``/checkout``; saucedemo uses
    ``/cart.html`` / ``/checkout-step-one.html``; others use ``/basket``.
    This mirrors the route vocabulary already used by journey discovery
    (``src/journey_scraper.py``) so stateful routing can never diverge from it.
    """
    if not path:
        return False
    lowered = path.lower()
    return any(token in lowered for token in ("view_cart", "cart", "checkout", "basket"))


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
    """Return same-domain candidate URLs for story concepts.

    Re-enabled 2026-08-03: journey discovery alone cannot traverse SPA sites
    (e.g. saucedemo) whose navigation uses JS click handlers with no hrefs, so
    cart/checkout URLs are never discovered and placeholders go unresolved.
    Concept-driven candidates from the shared route vocabulary (the same one
    journey discovery uses in ``src/journey_scraper.py``) fill the gap.
    Candidates are filtered to the seed domain to prevent cross-site
    hallucination — the original reason URL guessing was removed.
    """
    # Shared route vocabulary — mirrors src/journey_scraper.py keyword_routes
    concept_paths: dict[str, list[str]] = {
        "cart": ["/cart.html", "/cart", "/view_cart", "/basket"],
        "checkout": [
            "/checkout-step-one.html",
            "/checkout_step_one",
            "/checkout.html",
            "/checkout",
        ],
        "products": ["/products", "/inventory.html"],
    }
    if not seed_urls or not concepts:
        return []
    candidates: list[str] = []
    for concept in concepts:
        for path in concept_paths.get(concept.lower(), []):
            for seed in seed_urls:
                candidates.append(urljoin(seed, path))
    allowed = extract_seed_domain(seed_urls)
    return sorted(set(filter_urls_to_allowed_domain(candidates, allowed)))


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
