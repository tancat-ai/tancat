"""Page context tracking for journey-aware placeholder resolution.

Tracks which page the resolver should be operating on as it processes
journey steps sequentially. Uses both URL inference from element hrefs
and action-based heuristics to maintain accurate page state.

This module replaces the inline URL tracking in PlaceholderOrchestrator
with explicit, testable page context management.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


# Action words that imply page transitions when clicked.
NAVIGATION_ACTIONS = {
    "login",
    "sign in",
    "submit",
    "checkout",
    "continue",
    "finish",
    "place order",
    "proceed",
    "confirm",
    "next",
    "complete",
}

# Keyword mappings from action descriptions to expected URL patterns.
TRANSITION_URL_PATTERNS: dict[str, tuple[str, ...]] = {
    "login": ("inventory", "products", "dashboard", "home"),
    "checkout": ("checkout-step-one", "checkout_step_one", "checkout"),
    "continue": ("checkout-step-two", "checkout_step_two", "checkout-overview"),
    "finish": ("checkout-complete", "complete", "thank"),
    "cart": ("cart", "view_cart", "basket"),
    "home": ("home", "/"),
}


class PageContextTracker:
    """Track the active page URL as journey steps are processed."""

    def __init__(self, scraped_urls: list[str]) -> None:
        """Initialize with the list of all discovered/scraped URLs.

        Args:
            scraped_urls: URLs that have been scraped and have element data.
        """
        self._scraped_urls = list(dict.fromkeys(scraped_urls))  # deduplicate, preserve order
        self._current_url: str | None = None
        self._history: list[str] = []

    @property
    def current_url(self) -> str | None:
        """The currently active page URL."""
        return self._current_url

    @current_url.setter
    def current_url(self, value: str | None) -> None:
        """Set the current URL, recording history for diagnostics."""
        if value != self._current_url:
            if value is not None:
                self._history.append(value)
            self._current_url = value

    def set_initial_url(self, url: str | None) -> None:
        """Set the starting URL for a journey."""
        self.current_url = url

    def infer_next_url(
        self,
        action: str,
        description: str,
        matched_element: dict[str, str] | None,
    ) -> str | None:
        """Infer the next page URL after an action is performed.

        Priority:
        1. Element href (for CLICK on links)
        2. Action-based URL pattern matching
        3. Navigation-click with resolve_url fallback

        Returns:
            The inferred next URL, or None if no navigation is implied.
        """
        # Priority 1: Direct href from clicked element
        if action == "CLICK" and matched_element is not None:
            href = str(matched_element.get("href", "")).strip()
            if href:
                if href.startswith(("http://", "https://")):
                    return self._normalize_href(href)
                if self._current_url:
                    return self._normalize_href(urljoin(self._current_url, href))

        # Priority 2: Action-based pattern matching
        inferred = self._infer_from_action(description, matched_element)
        if inferred:
            return inferred

        # Priority 3: Navigation click — search scraped URLs
        if action == "CLICK" and self._is_navigation_click(description):
            return self._find_url_by_keywords(description)

        # No navigation implied for this action
        return None

    def _normalize_href(self, href: str) -> str | None:
        """Return the href if it matches a known scraped URL."""
        if not href:
            return None
        # Exact match
        if href in self._scraped_urls:
            return href
        # Contains match — find a scraped URL that contains the href path
        parsed = urlparse(href)
        href_path = parsed.path.lower()
        for url in self._scraped_urls:
            if href_path in url.lower():
                return url
        return href

    def _infer_from_action(
        self,
        description: str,
        matched_element: dict[str, str] | None,
    ) -> str | None:
        """Infer URL transitions from action description and element attributes."""
        haystack = description.lower()
        if matched_element:
            haystack += " "
            haystack += str(matched_element.get("selector", "")).lower()
            haystack += " "
            haystack += str(matched_element.get("id", "")).lower()
            haystack += " "
            haystack += str(matched_element.get("data_test", "")).lower()

        for keyword, patterns in TRANSITION_URL_PATTERNS.items():
            if keyword in haystack:
                result = self._find_url_by_patterns(patterns)
                if result:
                    # Avoid transitioning to the current URL
                    if result != self._current_url:
                        return result

        # Special case: "add to cart" does NOT navigate
        if "add" in haystack and "cart" in haystack:
            return None

        return None

    def _is_navigation_click(self, description: str) -> bool:
        """Check if a CLICK description implies navigation."""
        lowered = description.replace("_", " ").lower()
        nav_terms = {"link", "icon", "go to", "open", "navigate", "button", "home"}
        return any(term in lowered for term in nav_terms)

    def _find_url_by_keywords(self, description: str) -> str | None:
        """Find a scraped URL that matches keywords from the description."""
        lowered = description.lower()
        # Extract meaningful keywords (skip common words)
        stop_words = {"the", "a", "an", "to", "for", "of", "in", "on", "at", "by", "with"}
        words = {w for w in lowered.split() if w not in stop_words and len(w) > 2}

        best_url: str | None = None
        best_score = 0

        for url in self._scraped_urls:
            url_lower = url.lower()
            score = sum(1 for word in words if word in url_lower)
            if score > best_score:
                best_score = score
                best_url = url

        # Only return if at least one keyword matched
        if best_score > 0 and best_url != self._current_url:
            return best_url
        return None

    def _find_url_by_patterns(self, patterns: tuple[str, ...]) -> str | None:
        """Find a scraped URL containing any of the preferred patterns."""
        # Prefer patterns that appear earlier in the tuple
        for priority, pattern in enumerate(patterns):
            for url in self._scraped_urls:
                if pattern in url.lower():
                    logger.debug(
                        "PageContextTracker: pattern '%s' (priority=%d) matched URL '%s'",
                        pattern,
                        priority,
                        url,
                    )
                    return url
        return None

    def get_scoped_pages(
        self,
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, list[dict[str, str]]]:
        """Return scraped data scoped to the current page URL.

        Returns empty dict if current_url is None or not in scraped_data.
        """
        if self._current_url and self._current_url in scraped_data:
            return {self._current_url: scraped_data[self._current_url]}
        return {}

    def update_url(self, new_url: str | None) -> None:
        """Update the current URL if a new one is provided.

        This is called after each placeholder resolution to track
        page transitions.
        """
        if new_url is not None:
            self.current_url = new_url
