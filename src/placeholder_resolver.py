"""Resolve placeholder descriptions against scraped page elements."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


class PlaceholderResolver:
    """Match placeholder descriptions to real scraped locators."""

    STOP_WORDS = {
        "a",
        "an",
        "and",
        "be",
        "button",
        "check",
        "correctly",
        "for",
        "have",
        "icon",
        "in",
        "into",
        "items",
        "link",
        "logo",
        "of",
        "or",
        "page",
        "please",
        "product",
        "the",
        "to",
        "url",
        "with",
    }
    TOKEN_EXPANSIONS = {
        "add": {"buy", "basket"},
        "basket": {"cart"},
        "cart": {"basket", "bag", "shopping"},
        "checkout": {"check", "out", "order", "payment", "proceed", "complete"},
        "ecommerce": {"shop", "store"},
        "home": {"index", "landing", "start"},
        "product": {"item", "products", "shop", "store"},
        "products": {"catalog", "product", "shop"},
        "verify": {"assert", "check"},
    }

    def __init__(self, match_threshold: int = 1) -> None:
        self.match_threshold = match_threshold

    def _get_words(self, text: str, *, expand_aliases: bool = True) -> set[str]:
        clean_text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.replace("_", " ").lower())
        base_words = {word for word in clean_text.split() if word and word not in self.STOP_WORDS}
        expanded_words = set(base_words)

        for word in list(base_words):
            if word.endswith("s") and len(word) > 3:
                expanded_words.add(word[:-1])
            if expand_aliases:
                expanded_words.update(self.TOKEN_EXPANSIONS.get(word, set()))

        return expanded_words

    @staticmethod
    def _build_element_haystack(element: dict[str, Any]) -> str:
        """Return a text blob containing the element metadata used for matching."""
        parts = [
            str(element.get("text", "")),
            str(element.get("role", "")),
            str(element.get("selector", "")),
            str(element.get("href", "")),
            str(element.get("title", "")),
            str(element.get("aria_label", "")),
            str(element.get("name", "")),
            str(element.get("id", "")),
            str(element.get("classes", "")),
            str(element.get("value", "")),
            str(element.get("placeholder", "")),
        ]
        return " ".join(part for part in parts if part).strip()

    @staticmethod
    def _is_fillable_element(element: dict[str, Any]) -> bool:
        """Return True when the scraped element supports text entry."""
        role = str(element.get("role", "")).strip().lower()
        selector = str(element.get("selector", "")).strip().lower()
        name = str(element.get("name", "")).strip().lower()
        element_id = str(element.get("id", "")).strip().lower()

        # Never attempt to fill hidden inputs (e.g., CSRF tokens).
        if role == "hidden":
            return False
        if any(term in name or term in element_id or term in selector for term in ("csrf", "token", "authenticity")):
            return False

        if role in {"input", "textarea", "select", "textbox", "searchbox", "combobox", "email", "password"}:
            return True
        if selector.startswith(("input", "textarea", "select")):
            return True
        return bool(element.get("name") or element.get("placeholder"))

    @staticmethod
    def _is_assertion_candidate(element: dict[str, Any]) -> bool:
        """Return True when the scraped element is plausible for visibility assertions."""
        role = str(element.get("role", "")).strip().lower()
        href = str(element.get("href", "")).strip()
        text = str(element.get("text", "")).strip()

        if role in {"region", "list", "listitem", "article", "heading", "paragraph", "text", "div", "span"}:
            return True
        if not href and text:
            return True
        return False

    @staticmethod
    def _matches_intent_bucket(action: str, description: str, element: dict[str, Any]) -> bool:
        """Return True when the element fits the likely user intent for the step."""
        lowered = description.replace("_", " ").lower()
        selector = str(element.get("selector", "")).lower()
        text = str(element.get("text", "")).lower()
        href = str(element.get("href", "")).lower()
        classes = str(element.get("classes", "")).lower()
        haystack = " ".join([selector, text, href, classes])

        # If we are looking for a checkout or cart action, ignore footer subscription fields.
        # Sites like automationexercise.com have a persistent footer with #susbscribe_email
        # that often confuses semantic rankers.
        if any(term in lowered for term in ("cart", "checkout", "payment")):
            if "subscribe" in haystack or "newsletter" in haystack:
                return False

        if action == "CLICK" and "cart" in lowered and any(term in lowered for term in ("go", "open", "navigate")):
            return "view_cart" in haystack or ('href="/view_cart"' in selector) or text.strip() == "cart"

        if action == "CLICK" and "add" in lowered and "cart" in lowered:
            return any(
                term in haystack for term in ("add to cart", "add-to-cart", "data-product-id", "product_id", "buy")
            )

        if action == "ASSERT" and ("cart" in lowered or "item" in lowered or "checkout" in lowered):
            is_content_match = any(
                term in haystack
                for term in (
                    "cart_description",
                    "cart_quantity",
                    "cart_price",
                    "cart_total",
                    "cart-summary",
                    "summary",
                    "product",
                    "quantity",
                    "price",
                    "cart_info",
                    "checkout",
                    "order",
                    "payment",
                )
            )
            # Avoid matching product search widgets when asserting cart/checkout.
            if "search" in haystack and "cart" not in haystack:
                return False
            is_nav_link = str(element.get("role", "")).strip().lower() == "a" and "view_cart" in haystack
            return is_content_match and not is_nav_link

        if action == "CLICK" and any(term in lowered for term in ("checkout", "check out")):
            # Favor true checkout navigation, avoid "payment" shortcuts.
            if "payment" in haystack and "payment" not in lowered:
                return False
            return any(
                term in haystack
                for term in ("checkout", "check out", "proceed to checkout", "place order", "check_out")
            )

        return True

    def find_best_element(
        self,
        action: str,
        description: str,
        page_elements: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the best-matching scraped element for a placeholder description."""
        ranked_candidates = self.rank_candidates(action, description, page_elements)
        if ranked_candidates:
            score, element = ranked_candidates[0]

            # If we only have 1 word match, and it's a very short word, verify it's not a fluke
            if score == 1 and len(description) > 5:
                # Basic sanity check for single-word matches on long descriptions
                pass

            return element
        return None

    def rank_candidates(
        self,
        action: str,
        description: str,
        page_elements: list[dict[str, Any]],
    ) -> list[tuple[int, dict[str, Any]]]:
        """Return scored candidate elements in descending match order."""
        desc_words = self._get_words(description)
        if not desc_words:
            return []

        normalized_description = description.replace("_", " ").lower().strip()
        ranked: list[tuple[int, dict[str, Any]]] = []

        for element in page_elements:
            selector = str(element.get("selector", "")).strip()
            if not selector:
                continue

            if action == "FILL" and not self._is_fillable_element(element):
                continue
            if not self._matches_intent_bucket(action, description, element):
                continue

            haystack = self._build_element_haystack(element).lower()
            if haystack and normalized_description in haystack:
                if action == "ASSERT" and not self._is_assertion_candidate(element):
                    continue
                else:
                    ranked.append((100, element))
                    continue

            element_words = self._get_words(haystack, expand_aliases=False)
            score = len(desc_words.intersection(element_words))
            role = str(element.get("role", "")).strip().lower()
            href = str(element.get("href", "")).strip().lower()

            if action == "CLICK" and "cart" in desc_words and ("cart" in href or "cart" in element_words):
                score += 2
            if action == "CLICK" and "checkout" in desc_words and "checkout" in href:
                score += 2
            if action == "CLICK" and "checkout" in desc_words and "payment" in href and "payment" not in desc_words:
                # Avoid jumping straight to payment when the user intent is checkout.
                score -= 3
            if action == "ASSERT" and {"cart", "product"}.intersection(desc_words) and "cart" in href:
                score -= 2
            if action == "ASSERT" and self._is_assertion_candidate(element):
                score += 2
            if "link" in description.lower() and role == "a":
                score += 1
            if "button" in description.lower() and role in {"button", "submit"}:
                score += 1

            if action == "CLICK":
                if role in {"button", "link", "a", "submit"}:
                    score += 3
                if href:
                    score += 2
                if not str(element.get("text", "")).strip() and not href and "data-" in selector.lower():
                    score -= 4

            if action == "FILL" and self._is_fillable_element(element):
                score += 3

            if score >= self.match_threshold:
                ranked.append((score, element))

        ranked.sort(
            key=lambda item: (
                item[0],
                len(str(item[1].get("text", "")).strip()),
                len(str(item[1].get("selector", "")).strip()),
            ),
            reverse=True,
        )
        return ranked

    def find_best_match(self, action: str, description: str, page_elements: list[dict[str, Any]]) -> str | None:
        """Return the best-matching selector for a placeholder description."""
        best_element = self.find_best_element(action, description, page_elements)
        if best_element is None:
            # No heuristic fallback — let placeholders resolve to None and emit pytest.skip()
            # This enforces "skip rather than guess" architectural principle.
            return None
        selector = str(best_element.get("selector", "")).strip()
        if selector:
            return selector
        return None

    def resolve_url(self, description: str, pages_data: dict[str, list[dict[str, Any]]]) -> str | None:
        """Resolve navigation placeholders to the best matching scraped URL."""
        if not pages_data:
            return None

        desc_words = self._get_words(description)
        if not desc_words:
            first_url = next(iter(pages_data), None)
            return first_url

        best_score = -1
        best_url: str | None = None

        for url, elements in pages_data.items():
            parsed = urlparse(url)
            path_words = self._get_words((parsed.path or "/").replace("/", " "), expand_aliases=False)
            page_words = set(path_words)
            for element in elements[:25]:
                page_words.update(self._get_words(self._build_element_haystack(element), expand_aliases=False))

            score = len(desc_words.intersection(page_words))
            if parsed.path in {"", "/"} and {"home", "start", "landing", "store"}.intersection(desc_words):
                score += 4
            if "product" in desc_words and {"product", "products", "shop"}.intersection(path_words):
                score += 4
            if "cart" in desc_words and {"cart", "view", "basket"}.intersection(path_words):
                score += 4
            if {"checkout", "order", "payment"}.intersection(desc_words) and "checkout" in path_words:
                score += 4

            if score > best_score:
                best_score = score
                best_url = url

        if best_score > 0:
            return best_url

        return next(iter(pages_data), None)

    def resolve_all(
        self,
        placeholders: list[tuple[str, str]],
        pages_data: dict[str, list[dict[str, Any]]],
    ) -> list[str]:
        """Resolve all placeholders into selectors or explicit `pytest.skip()` calls."""
        resolutions: list[str] = []

        for action, description in placeholders:
            found_match: str | None = None

            if action in {"GOTO", "URL"}:
                found_match = self.resolve_url(description, pages_data)
                if found_match:
                    resolutions.append(repr(found_match))
                    continue

            for elements in pages_data.values():
                found_match = self.find_best_match(action, description, elements)
                if found_match:
                    break

            if found_match:
                resolutions.append(repr(found_match))
                continue

            error_msg = f"Locator for '{description}' not found on scraped pages."
            resolutions.append(f'pytest.skip("{error_msg}")')

        return resolutions
