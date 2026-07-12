"""Resolve page keywords to actually discovered URLs from journey scraping.

This module bridges the gap between LLM-generated page keywords (e.g., "cart",
"checkout") and the real URLs discovered by the journey scraper. It uses
heuristic matching against URL paths, then falls back to common path candidates.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from src.url_utils import build_common_path_candidates

logger = logging.getLogger(__name__)


class UrlResolver:
    """Build keyword → URL mapping from journey scraping results.

    After the skeleton phase, the LLM writes keywords in PAGES_NEEDED that match
    GOTO placeholder descriptions. This class maps those keywords to actual URLs
    discovered by journey scraping, so that GOTO placeholders resolve to real URLs
    instead of LLM-guessed paths.
    """

    def __init__(self) -> None:
        self._keyword_to_url: dict[str, str] = {}
        self._scraped_urls: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_mapping(
        self,
        keywords: list[str],
        scraped_urls: list[str],
        seed_url: str,
        concepts: list[str] | None = None,
    ) -> None:
        """Match keywords to discovered URLs using heuristic matching.

        Args:
            keywords: Page keywords from PAGES_NEEDED (e.g., ["cart", "checkout"]).
            scraped_urls: URLs actually visited by the journey scraper.
            seed_url: The user-provided homepage URL.
            concepts: Optional route concepts extracted from the user story.
        """
        # Store scraped URLs for resolve-time fallback
        self._scraped_urls = list(scraped_urls)
        # 1. Always map seed URL to home/login keywords
        self._keyword_to_url["home"] = seed_url
        self._keyword_to_url["login"] = seed_url
        self._keyword_to_url["homepage"] = seed_url

        # 2. Match keywords against discovered URL paths
        for keyword in keywords:
            kw_lower = keyword.lower()
            if kw_lower in self._keyword_to_url:
                continue  # Already mapped (home/login)

            resolved = self._match_keyword_to_url(kw_lower, scraped_urls)
            if resolved:
                self._keyword_to_url[kw_lower] = resolved
                logger.debug("Mapped keyword '%s' → %s", keyword, resolved)
            else:
                logger.warning("Could not resolve keyword '%s' to any scraped URL", keyword)

        # 3. Auto-map route concepts against scraped URLs.
        # This ensures common page types (cart, checkout, products) are mapped
        # even if PAGES_NEEDED was sparse or omitted them.
        if concepts:
            for concept in concepts:
                c_lower = concept.lower()
                if c_lower in self._keyword_to_url:
                    continue  # Already mapped
                resolved = self._match_keyword_to_url(c_lower, scraped_urls)
                if resolved:
                    self._keyword_to_url[c_lower] = resolved
                    logger.debug("Mapped concept '%s' → %s", concept, resolved)

        # 4. If concepts provided and no scraped URLs, generate common path candidates
        if not scraped_urls and concepts:
            logger.info("No scraped URLs available — generating common path candidates")
            candidates = build_common_path_candidates([seed_url], set(concepts))
            for candidate_url in candidates:
                # Extract a keyword-like path segment from the candidate
                path = urlparse(candidate_url).path.lower().strip("/")
                if path and path not in self._keyword_to_url.values():
                    # Reverse-map: use the last path segment as a keyword
                    segment = path.split("/")[-1].split(".")[0]
                    if segment and segment not in self._keyword_to_url:
                        self._keyword_to_url[segment] = candidate_url

    def resolve(self, keyword: str) -> str | None:
        """Resolve a keyword to an actual URL.

        Args:
            keyword: A page keyword (e.g., "cart", "checkout", "home").

        Returns:
            The resolved URL, or None if the keyword cannot be matched.
        """
        kw_lower = keyword.lower()
        if kw_lower in self._keyword_to_url:
            return self._keyword_to_url[kw_lower]

        # Fallback 1: try substring matching against known keywords
        for known_kw, url in self._keyword_to_url.items():
            if kw_lower in known_kw or known_kw in kw_lower:
                logger.debug(
                    "Partial keyword match: '%s' → '%s' (%s)",
                    keyword,
                    known_kw,
                    url,
                )
                return url

        # Fallback 2: multi-word decomposition against URL path segments.
        # Handles "Dress category page" → /category_products/1
        # Check ALL scraped URLs, not just pre-mapped keywords.
        # This catches GOTO descriptions that reference pages visited by journey
        # discovery but never declared in PAGES_NEEDED.
        noise = {"the", "a", "an", "page", "link", "button", "on", "to", "and", "or"}
        keyword_words = [w for w in kw_lower.replace("-", " ").split() if len(w) > 2 and w not in noise]
        if keyword_words:
            # Check mapped URLs first, then fall back to all scraped URLs
            all_urls = list(self._keyword_to_url.values())
            # Add scraped URLs that aren't already in the mapping
            for url in self._scraped_urls:
                if url not in all_urls:
                    all_urls.append(url)
            for url in all_urls:
                path = urlparse(url).path.lower().strip("/")
                if not path:
                    continue
                clean_path = path.rsplit(".", 1)[0]
                match_count = sum(1 for w in keyword_words if w in clean_path)
                if match_count >= 1:
                    logger.debug(
                        "Multi-word path match: '%s' → %s (%s)",
                        keyword,
                        url,
                        clean_path,
                    )
                    return url

        return None

    def get_seed_url(self) -> str | None:
        """Return the seed URL as fallback.

        Returns:
            The seed URL mapped to "home", or None if not set.
        """
        return self._keyword_to_url.get("home")

    def get_all_mappings(self) -> dict[str, str]:
        """Return a copy of all keyword→URL mappings.

        Returns:
            A dictionary mapping keywords to URLs.
        """
        return dict(self._keyword_to_url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_keyword_to_url(
        kw_lower: str,
        scraped_urls: list[str],
    ) -> str | None:
        """Match a single keyword to the best scraped URL.

        Strategy (in priority order):
        1. Exact path match: keyword "cart" matches /cart (single-segment path)
        2. Direct path segment match: keyword "cart" matches /shop/cart
        3. Normalized substring match: "checkout overview" matches /checkout-overview
        4. Prefix match: "product" matches /products (shortest path wins)

        Returns the first matching URL, or None.
        """
        # Normalize keyword: replace spaces with common separators
        kw_normalized = kw_lower.replace(" ", "-").replace("_", "-")

        # 1. Exact path match — keyword matches the entire path (single segment)
        exact_candidates: list[str] = []
        for url in scraped_urls:
            path = urlparse(url).path.lower().strip("/")
            if not path:
                continue
            clean_path = path.rsplit(".", 1)[0]
            if clean_path == kw_lower or clean_path == kw_normalized:
                exact_candidates.append(url)
        if exact_candidates:
            exact_candidates.sort(key=lambda url: (0 if "." in urlparse(url).path.rsplit("/", 1)[-1] else 1, len(url)))
            return exact_candidates[0]

        # 2. Direct path segment match
        for url in scraped_urls:
            path = urlparse(url).path.lower().strip("/")
            if not path:
                continue
            clean_path = path.rsplit(".", 1)[0]
            segments = clean_path.split("/")
            if kw_lower in segments:
                return url

        # 3. Normalized substring match (spaces → dashes)
        for url in scraped_urls:
            path = urlparse(url).path.lower().strip("/")
            if not path:
                continue
            clean_path = path.rsplit(".", 1)[0]
            if kw_normalized in clean_path:
                return url

        # 4. Prefix match — prefer shortest path (closest to root)
        candidates: list[tuple[int, str]] = []
        for url in scraped_urls:
            path = urlparse(url).path.lower().strip("/")
            if not path:
                continue
            clean_path = path.rsplit(".", 1)[0]
            segments = clean_path.split("/")
            for segment in segments:
                if (segment.startswith(kw_lower) or kw_lower.startswith(segment)) and len(segment) > 2:
                    candidates.append((len(path), url))
                    break
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]

        # 5. Multi-word keyword decomposition: try each significant word
        # against URL path segments. Handles "dress category page" → /category_products/1
        noise = {"the", "a", "an", "page", "link", "button", "on", "to", "and", "or"}
        keyword_words = [w for w in kw_lower.replace("-", " ").split() if len(w) > 2 and w not in noise]
        if len(keyword_words) > 1:
            for url in scraped_urls:
                path = urlparse(url).path.lower().strip("/")
                if not path:
                    continue
                clean_path = path.rsplit(".", 1)[0]
                # Count how many keyword words appear in the path
                match_count = sum(1 for w in keyword_words if w in clean_path)
                if match_count >= 1:
                    return url  # First URL with any keyword word match

        return None


# ------------------------------------------------------------------
# Module-level convenience function
# ------------------------------------------------------------------


def resolve_keywords_to_urls(
    keywords: list[str],
    scraped_urls: list[str],
    seed_url: str,
    concepts: list[str] | None = None,
) -> UrlResolver:
    """Create and populate a UrlResolver in a single call.

    This is a convenience function for the orchestrator pipeline.

    Args:
        keywords: Page keywords from PAGES_NEEDED.
        scraped_urls: URLs discovered by journey scraping.
        seed_url: The user-provided homepage URL.
        concepts: Optional route concepts from the user story.

    Returns:
        A configured UrlResolver instance.
    """
    resolver = UrlResolver()
    resolver.build_mapping(keywords, scraped_urls, seed_url, concepts)
    return resolver
