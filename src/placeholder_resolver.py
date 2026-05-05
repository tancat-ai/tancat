"""Resolve placeholder descriptions against scraped page elements."""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _default_min_confidence() -> float:
    """Return the minimum confidence threshold from environment or default."""
    try:
        return float(os.environ.get("PLACEHOLDER_MIN_CONFIDENCE", "0.3"))
    except (ValueError, TypeError):
        return 0.3


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

    def __init__(
        self,
        match_threshold: int = 1,
        min_confidence: float | None = None,
    ) -> None:
        self.match_threshold = match_threshold
        self.min_confidence = min_confidence if min_confidence is not None else _default_min_confidence()

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
            # Visual enrichment fields
            str(element.get("icon_classes", "")),
            str(element.get("icon_unicode", "")),
            str(element.get("parent_text", "")),
            str(element.get("aria_icon_label", "")),
            str(element.get("visual_description", "")),
            # Accessibility tree enrichment (AI-024)
            str(element.get("accessible_name", "")),
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
        """Return True when the scraped element fits the likely user intent for the step."""
        lowered = description.replace("_", " ").lower()
        selector = str(element.get("selector", "")).lower()
        text = str(element.get("text", "")).lower()
        href = str(element.get("href", "")).lower()
        classes = str(element.get("classes", "")).lower()
        icon_classes = str(element.get("icon_classes", "")).lower()
        visual_desc = str(element.get("visual_description", "")).lower()
        parent_text = str(element.get("parent_text", "")).lower()
        aria_icon_label = str(element.get("aria_icon_label", "")).lower()
        element_id = str(element.get("id", "")).lower()
        haystack = " ".join([selector, text, href, classes, icon_classes, visual_desc, parent_text, aria_icon_label])

        # GENERIC SUBSCRIBE/NEWSLETTER GUARD (enhanced)
        # Sites like automationexercise.com have a persistent footer with #subscribe / newsletter fields
        # that often confuses semantic rankers.  This guard now covers:
        #  - explicit cart/checkout/payment actions (original)
        #  - popup/modal related actions ("continue shopping", "close", "dismiss", "ok")
        #  - ANY CLICK action when the element has no visible text but carries a subscribe/newsletter ID.
        is_subscribe_element = (
            "subscribe" in haystack
            or "newsletter" in haystack
            or element_id in {"subscribe", "susbscribe_email", "newsletter_email"}
        )
        if any(term in lowered for term in ("cart", "checkout", "payment")):
            if is_subscribe_element:
                return False

        # Extended popup/modal guard: "continue shopping", "close modal", "dismiss", etc.
        if action == "CLICK" and any(
            term in lowered
            for term in (
                "continue shopping",
                "close",
                "dismiss",
                "ok",
                "cancel",
                "popup",
                "modal",
                "confirmation",
            )
        ):
            if is_subscribe_element:
                return False

        # Generic guard for CLICK actions: an element with NO visible text that carries a
        # subscribe/newsletter ID should never be clicked when the description expects specific
        # action-oriented text (e.g. "Continue Shopping").  Inputs without text are almost always
        # form fields, not clickable buttons.
        if action == "CLICK" and is_subscribe_element and not text.strip():
            return False

        if action == "ASSERT" and any(term in lowered for term in ("home page", "landing page", "start page")):
            # A page-state assertion this generic should skip rather than latch onto
            # an arbitrary visible element like a footer link.
            return False

        if action == "CLICK" and "product card" in lowered:
            return any(term in haystack for term in ("product card", "product-card", "card"))

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

    # Words that describe the UI interaction pattern rather than the content itself.
    # These should be stripped from placeholder descriptions before text matching
    # so that "Add to cart button next to a product" focuses on "add cart product"
    # rather than failing because the element text "Add to cart" lacks "button", "next", etc.
    # IMPORTANT: Do NOT strip words like "link", "icon", "header", "cart" — these are
    # meaningful content descriptors that help distinguish between elements.
    ACTION_CONTEXT_WORDS = {
        "a",
        "an",
        "and",
        "appears",
        "button",
        "click",
        "correctly",
        "dialog",
        "enter",
        "field",
        "fill",
        "for",
        "hover",
        "icon",
        "input",
        "in",
        "into",
        "loads",
        "modal",
        "next",
        "on",
        "or",
        "popup",
        "press",
        "select",
        "successfully",
        "tap",
        "the",
        "text",
        "to",
        "type",
        "visible",
        "with",
    }

    # Action verbs that signal a specific interaction (add, buy, remove, etc.).
    # When the description uses navigation language ("link", "icon") but the element
    # text contains action verbs, reject the match — they represent different intents.
    ACTION_VERBS = {
        "add",
        "buy",
        "remove",
        "delete",
        "submit",
        "register",
        "sign",
        "login",
        "logout",
        "place",
        "proceed",
        "continue",
        "close",
        "dismiss",
        "cancel",
    }

    # Navigation language that indicates the user wants to navigate TO something,
    # not perform an action ON something.
    NAVIGATION_WORDS = {
        "link",
        "icon",
        "button",
        "go",
        "open",
        "navigate",
        "header",
        "menu",
        "tab",
    }

    @staticmethod
    def text_matches_description(element_text: str, action_description: str) -> bool:
        """Check if element's visible text plausibly matches the action description.

        Uses case-insensitive containment with whitespace normalization.
        Strips action-context words from the description to focus on core intent words.
        For example: "Add to cart button next to a product" becomes "add cart product"
        which can now match element text "Add to cart".

        REJECTS mismatches where the description uses navigation language ("cart link")
        but the element text contains action verbs ("Add to cart") — different intents.
        """
        if not element_text or not action_description:
            return False

        # Normalize underscores to spaces (LLM often generates "add_to_cart_button" style)
        norm_text = re.sub(r"[_\s]+", " ", element_text).strip().lower()
        norm_desc = re.sub(r"[_\s]+", " ", action_description).strip().lower()

        # Direct containment (most reliable check)
        if norm_text in norm_desc or norm_desc in norm_text:
            return True

        # Word-level overlap with action-context words stripped from description
        desc_words = set(norm_desc.split()) - PlaceholderResolver.ACTION_CONTEXT_WORDS
        text_words = set(norm_text.split())
        if desc_words and text_words:
            overlap = len(desc_words & text_words)
            # Require at least half the core intent words to match, with minimum of 1
            if overlap >= max(1, len(desc_words) // 2):
                # REJECT: description uses navigation language but element has action verbs
                # e.g. "Cart link" should NOT match "Add to cart" element text
                desc_has_nav = bool(desc_words & PlaceholderResolver.NAVIGATION_WORDS)
                element_has_action = bool(text_words & PlaceholderResolver.ACTION_VERBS)
                if desc_has_nav and element_has_action:
                    return False
                return True

        return False

    def find_best_element(
        self,
        action: str,
        description: str,
        page_elements: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the best-matching scraped element for a placeholder description.

        Applies text-content validation and confidence threshold filtering.
        Elements whose visible text doesn't match the description are skipped.
        If the best candidate's confidence score is below ``min_confidence``,
        the method returns ``None`` (skip rather than guess).
        """
        ranked_candidates = self.rank_candidates(action, description, page_elements)
        if not ranked_candidates:
            return None

        # Filter by text-content validation (B1)
        for score, element in ranked_candidates:
            element_text = str(element.get("text", "")).strip()
            if self.text_matches_description(element_text, description):
                # Verify confidence threshold (B2)
                max_possible_score = max(c[0] for c in ranked_candidates)
                confidence = score / max_possible_score if max_possible_score > 0 else 0.0
                if confidence >= self.min_confidence:
                    return element
                logger.debug(
                    "Candidate '%s' confidence %.2f below threshold %.2f — marking unresolved",
                    element_text,
                    confidence,
                    self.min_confidence,
                )
            elif element_text:
                logger.debug(
                    "Skipped candidate '%s' — text does not match description '%s'",
                    element_text,
                    description,
                )

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

            # Skip hidden elements entirely — never select elements that are
            # explicitly marked as hidden (e.g. CSRF tokens, consent framework inputs).
            role = str(element.get("role", "")).strip().lower()
            if role == "hidden":
                continue

            # Extract visual enrichment variables for use in scoring
            lowered = description.replace("_", " ").lower()
            icon_classes = str(element.get("icon_classes", "")).lower()
            visual_desc = str(element.get("visual_description", "")).lower()
            parent_text = str(element.get("parent_text", "")).lower()

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

            # Extract element text once for use in multiple scoring rules below.
            element_text = str(element.get("text", "")).strip()

            # Text-content penalty for CLICK actions: elements with NO visible text should be
            # penalized when the description contains meaningful content words (not just stop words).
            # This prevents an empty newsletter input (#subscribe) from beating a button with
            # "Continue Shopping" text.  Increased from -5 to -10 to more strongly prefer
            # elements with visible, descriptive text over bare structural elements.
            if action == "CLICK":
                desc_content_words = desc_words - {"click", "tap", "press"}
                if not element_text and desc_content_words:
                    score -= 10

            # ASSERT-specific penalty: single-class selectors (e.g. ".btn") are overly generic
            # and often match hidden modal buttons or unrelated page elements.  Penalize them
            # so the resolver prefers elements with specific text content matching the description.
            if action == "ASSERT":
                selector_lower = selector.lower()
                # Detect single-class selectors: exactly one class, no ID, no data-attrs, no href
                is_single_class = (
                    selector_lower.startswith(".")
                    and selector_lower.count(".") == 1
                    and "[" not in selector_lower
                    and "#" not in selector_lower
                )
                if is_single_class and not element_text:
                    score -= 5

            # Visual enrichment bonus: icon-aware matching
            if action == "CLICK":
                # Icon-only elements get a small bonus when description mentions icons/buttons
                is_icon = element.get("is_icon", False)
                is_decorative = element.get("is_decorative", False)

                # Decorative elements should be excluded
                if is_decorative:
                    score -= 10

                if is_icon:
                    # Description mentions "icon", "button", or "click" — icon elements are good matches
                    if any(term in lowered for term in ("icon", "button", "click", "btn", "arrow", "chevron")):
                        score += 3
                    # Element has icon classes — bonus for icon-related descriptions
                    if icon_classes and any(
                        term in icon_classes
                        for term in ("fa-", "fas", "far", "fab", "bi-", "mdi-", "eicon-", "octicon-")
                    ):
                        score += 2
                    # Visual description contains relevant keywords
                    if visual_desc and any(term in visual_desc for term in ("icon", "button", "label", "aria-label")):
                        score += 1

                # Parent text bonus: if description matches parent context
                if parent_text and parent_text != lowered:
                    parent_words = set(parent_text.split())
                    desc_word_set = set(lowered.replace("_", " ").split())
                    parent_overlap = len(parent_words.intersection(desc_word_set))
                    if parent_overlap > 0:
                        score += parent_overlap

                # Visual description bonus
                if visual_desc and visual_desc != lowered:
                    visual_words = set(visual_desc.replace("_", " ").split())
                    desc_word_set = set(lowered.replace("_", " ").split())
                    visual_overlap = len(visual_words.intersection(desc_word_set))
                    if visual_overlap > 0:
                        score += visual_overlap

            if score >= self.match_threshold:
                ranked.append((score, element))

        # Sort by: 1) score desc, 2) text length desc (prefer more descriptive elements),
        # 3) selector specificity desc (prefer longer, more specific selectors).
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
        """Return the best-matching selector for a placeholder description.

        Transforms brittle CSS selectors (e.g. `.btn.btn-default.add-to-cart[data-product-id="11"]`)
        into robust Playwright locators (e.g. `a:has-text("Add to cart")`) when possible.
        """
        best_element = self.find_best_element(action, description, page_elements)
        if best_element is None:
            # No heuristic fallback — let placeholders resolve to None and emit pytest.skip()
            # This enforces "skip rather than guess" architectural principle.
            return None
        selector = self._build_robust_locator(best_element)
        if selector:
            return selector
        # Fallback to raw scraped selector if robust locator couldn't be built
        raw_selector = str(best_element.get("selector", "")).strip()
        return raw_selector if raw_selector else None

    @staticmethod
    def _build_robust_locator(element: dict[str, Any]) -> str | None:
        """Build a robust Playwright locator from scraped element metadata.

        Prefers stable, specific selectors (ID, href, data-attrs) over
        text-based locators when a stable selector is available.  Text-based
        locators are used as a fallback when no stable selector exists.

        Priority order (most specific first):
        1. ID-based (e.g. `#buy`)
        2. href-based for links (e.g. `a[href="/view_cart"]`)
        3. Data attribute with specific value (e.g. `[data-product-id="1"]`)
        4. Class-based without brittle framework prefixes (e.g. `.cart_description`)
        5. Tag + :has-text (e.g. `a:has-text("Add to cart")`)
        6. Role + :has-text (e.g. `button:has-text("Submit")`)
        7. Aria-label based (e.g. `[aria-label="Submit"]`)
        8. None — falls back to raw selector
        """
        tag = str(element.get("tag", "")).strip().lower()
        text = str(element.get("text", "")).strip()
        role = str(element.get("role", "")).strip().lower()
        selector = str(element.get("selector", "")).strip()
        element_id = str(element.get("id", "")).strip()
        aria_label = str(element.get("aria_label", "")).strip()
        classes = str(element.get("classes", "")).strip().lower()
        href = str(element.get("href", "")).strip()

        # Strip common UI framework class prefixes that add no semantic value
        # e.g. "btn btn-default add-to-cart" -> useful parts: "add-to-cart"
        useful_class_terms = {
            term
            for term in classes.split()
            if term
            and not any(prefix in term for prefix in ("btn-", "fa-", "fas", "far", "bi-", "mdi-", "icon-", "css-"))
        }

        # Build tag prefix for the locator
        tag_prefix = tag if tag and tag not in ("div", "span", "a", "") else ""

        # Priority 1: ID-based locator (most stable)
        # Check the `id` field first, then fall back to extracting from selector
        if element_id:
            return f"#{element_id}"
        # Extract ID from raw selector (e.g. "#buy" -> "buy")
        id_match = re.search(r"#([\w-]+)", selector)
        if id_match:
            return f"#{id_match.group(1)}"

        # Priority 2: href-based locator for anchor elements
        if role in ("a", "link"):
            # First try extracting href value from the raw selector (e.g. a[href="/view_cart"])
            href_match = re.search(r'\[href=["\']([^"\']+)["\']\]', selector)
            if href_match:
                escaped_href = href_match.group(1).replace('"', '\\"')
                return f'a[href="{escaped_href}"]'
            # Fall back to the href field
            if href:
                escaped_href = href.replace('"', '\\"')
                return f'a[href="{escaped_href}"]'

        # Priority 3: Data attribute with specific value from the raw selector
        # e.g. [data-product-id="1"] — keep the specific value when it's a simple data-* attr
        data_attr_matches = re.findall(r'\[data-([\w-]+)=["\']([^"\']+)["\']\]', selector)
        if data_attr_matches:
            # Build selector with specific data attribute values
            data_parts = [f'[data-{attr_name}="{attr_value}"]' for attr_name, attr_value in data_attr_matches]
            # Add useful class terms if present
            if useful_class_terms:
                class_part = "." + ".".join(sorted(useful_class_terms))
                return class_part + "".join(data_parts)
            return "".join(data_parts)

        # Priority 4: Class-based without brittle framework prefixes
        # Extract class names from the raw selector as primary source
        # e.g. ".cart_description", ".btn.btn-default.add-to-cart", etc.
        selector_class_matches = re.findall(r"\.([\w-]+)", selector)
        if selector_class_matches:
            # Filter out framework prefixes from selector-extracted classes too
            clean_classes = [
                c
                for c in selector_class_matches
                if not any(prefix in c for prefix in ("btn-", "fa-", "fas", "far", "bi-", "mdi-", "icon-", "css-"))
            ]
            if clean_classes:
                class_part = "." + ".".join(sorted(clean_classes))
                if tag_prefix:
                    return f"{tag_prefix}{class_part}"
                return class_part

        # Also use useful_class_terms from the `classes` field as fallback
        if useful_class_terms:
            class_part = "." + ".".join(sorted(useful_class_terms))
            if tag_prefix:
                return f"{tag_prefix}{class_part}"
            return class_part

        # Priority 5: Text-based locator (fallback — robust but less specific)
        if text:
            escaped_text = text.replace('"', '\\"')
            if tag_prefix:
                return f'{tag_prefix}:has-text("{escaped_text}")'
            if role and role not in ("", "div", "span"):
                return f'{role}:has-text("{escaped_text}")'
            return f':has-text("{escaped_text}")'

        # Priority 6: Aria-label based locator
        if aria_label:
            escaped_label = aria_label.replace('"', '\\"')
            if tag_prefix:
                return f'{tag_prefix}[aria-label="{escaped_label}"]'
            return f'[aria-label="{escaped_label}"]'

        # No robust locator could be built — caller falls back to raw selector
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
