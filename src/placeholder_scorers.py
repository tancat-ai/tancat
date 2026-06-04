"""Scoring functions for placeholder resolution.

Extracted from PlaceholderResolver.rank_candidates() to improve testability
and decouple scoring logic from orchestration. Each scoring concern is a
standalone function that can be unit-tested in isolation.

Workflow:
  PlaceholderResolver.rank_candidates() -> compute_element_score() -> score adjustments
"""

import re
from typing import Any

from src.semantic_matcher import SemanticMatcher


class PlaceholderScorer:
    """Stateless scoring utilities for placeholder candidate ranking."""

    # Words that describe the action itself, not the target element.
    # Stripped before text-content overlap calculations.
    ACTION_CONTEXT_WORDS: set[str] = {
        "click",
        "tap",
        "press",
        "fill",
        "type",
        "enter",
        "check",
        "uncheck",
        "select",
        "assert",
        "verify",
        "confirm",
        "navigate",
        "goto",
    }

    # Terms that signal an icon or button-style element.
    ICON_SIGNAL_TERMS: tuple[str, ...] = ("icon", "button", "click", "btn", "arrow", "chevron")

    # Known icon library class prefixes.
    ICON_CLASS_PREFIXES: tuple[str, ...] = (
        "fa-",
        "fas",
        "far",
        "fab",
        "bi-",
        "mdi-",
        "eicon-",
        "octicon-",
    )

    # Words stripped from product-name extraction in "add to cart" scoring.
    PRODUCT_FILTER_WORDS: set[str] = {
        "add",
        "cart",
        "button",
        "item",
        "product",
        "for",
        "to",
        "the",
        "a",
        "an",
    }

    # Terms that signal a message-like assertion target.
    MESSAGE_LIKE_TERMS: tuple[str, ...] = (
        "message",
        "confirmation",
        "success",
        "alert",
        "notification",
        "popup",
    )

    # Text terms that signal confirmation-like content.
    CONFIRMATION_TEXT_TERMS: tuple[str, ...] = (
        "confirm",
        "success",
        "thank",
        "order",
        "complete",
        "done",
    )

    @staticmethod
    def compute_element_score(
        action: str,
        description: str,
        element: dict[str, Any],
        selector: str,
        match_threshold: float,
    ) -> int | None:
        """Compute a composite score for one candidate element.

        Returns the score when the element passes the threshold, or ``None``
        when it should be excluded from the ranked list.
        """
        lowered = description.replace("_", " ").lower()
        icon_classes = str(element.get("icon_classes", "")).lower()
        visual_desc = str(element.get("visual_description", "")).lower()
        parent_text = str(element.get("parent_text", "")).lower()

        # --- FILL gate ---
        if action == "FILL" and not PlaceholderScorer._is_fillable(element):
            return None

        # --- Visibility gate for ASSERT ---
        if action == "ASSERT" and description:
            desc_lower = description.lower()
            if any(
                keyword in desc_lower
                for keyword in ("message", "confirmation", "success", "error", "alert", "notification")
            ):
                if element.get("is_visible") is False:
                    # For assertion tokens seeking a message/confirmation element,
                    # invisible elements are still considered (they may need JS
                    # interaction) but penalised heavily downstream.
                    pass

        # --- Haystack match (fast path) ---
        haystack = PlaceholderScorer._build_haystack(element).lower()
        normalized_desc = re.sub(r"['\"]", "", description).lower().replace("_", " ")
        if haystack and normalized_desc in haystack:
            haystack_score = PlaceholderScorer._haystack_score(action, description, element)
            return haystack_score if haystack_score >= match_threshold else None

        # --- Semantic score (slow path) ---
        desc_words = SemanticMatcher.get_words(description)
        element_words = SemanticMatcher.get_words(haystack, expand_aliases=False)
        score = len(desc_words.intersection(element_words))

        # Structural match bonus
        score = max(score, PlaceholderScorer._structural_bonus(action, description, element))

        # Action-specific adjustments
        score += PlaceholderScorer._href_bonus(action, description, desc_words, element, element_words)
        score += PlaceholderScorer._product_id_bonus(action, description, desc_words, element, element_words)
        score += PlaceholderScorer._assert_cart_penalty(action, description, desc_words, element)
        score += PlaceholderScorer._assertion_candidate_bonus(action, element)
        score += PlaceholderScorer._role_bonus(action, description, element)
        score += PlaceholderScorer._journey_discovered_bonus(element)
        score += PlaceholderScorer._click_role_bonus(action, element)
        score += PlaceholderScorer._fill_bonus(action, element)
        score += PlaceholderScorer._assert_visibility_penalty(action, element)
        score += PlaceholderScorer._click_text_penalty(action, description, desc_words, element)
        score += PlaceholderScorer._assert_single_class_penalty(action, selector, element)
        score += PlaceholderScorer._visual_enrichment_bonus(
            action, description, element, lowered, icon_classes, visual_desc, parent_text
        )
        score += PlaceholderScorer._assert_action_penalty(action, description, element)
        score += PlaceholderScorer._assert_message_bonus(action, description, element)
        score += PlaceholderScorer._text_content_bonus(description, element)

        return score if score >= match_threshold else None

    # ------------------------------------------------------------------
    # Internal helpers — all pure functions or static lookups
    # ------------------------------------------------------------------

    @staticmethod
    def _build_haystack(element: dict[str, Any]) -> str:
        """Build the haystack string for an element (mirrors PlaceholderResolver logic)."""
        parts: list[str] = []
        for key in ("text", "name", "label", "placeholder", "title", "aria_label", "value"):
            val = str(element.get(key, "")).strip()
            if val:
                parts.append(val)
        return " ".join(parts)

    @staticmethod
    def _is_fillable(element: dict[str, Any]) -> bool:
        """Check if an element is a fillable input."""
        role = (element.get("role", "") or "").lower()
        tag = (element.get("tag", "") or "").lower()
        type_attr = (element.get("type", "") or "").lower()
        disabled = element.get("disabled", False)
        readonly = element.get("readonly", False)
        if disabled or readonly:
            return False
        fillable_roles = {"textbox", "searchbox", "search_box", "combobox", "spinbutton"}
        fillable_tags = {"input", "textarea", "select"}
        input_types = {"text", "search", "email", "password", "tel", "url", "number"}
        if role in fillable_roles:
            return True
        if tag in fillable_tags:
            if tag == "input":
                return type_attr in input_types or type_attr == ""
            return True
        return False

    @staticmethod
    def _haystack_score(action: str, description: str, element: dict[str, Any]) -> int:
        """Compute score for fast-path haystack matches."""
        score = 100
        # Product-ID bonus for add-to-cart clicks
        if action == "CLICK" and {"add", "cart"}.issubset(SemanticMatcher.get_words(description)):
            raw_product_words = (
                SemanticMatcher.get_words(description, expand_aliases=False) - PlaceholderScorer.PRODUCT_FILTER_WORDS
            )
            if raw_product_words:
                element_id_lower = str(element.get("id", "")).lower().replace("-", " ").replace("_", " ")
                product_word_set = set(" ".join(raw_product_words).lower().split())
                if product_word_set and all(pw in element_id_lower for pw in product_word_set):
                    score += 20
        # Journey-discovered bonus
        if element.get("_journey_discovered") == "true":
            score += 5
        return score

    @staticmethod
    def _structural_bonus(action: str, description: str, element: dict[str, Any]) -> int:
        """Structural match bonus when data-test or id contains description keywords."""
        desc_words = SemanticMatcher.get_words(description)
        desc_content_words = desc_words - {"click", "tap", "press"} if action == "CLICK" else desc_words
        data_test_words = set(str(element.get("data_test", "")).lower().replace("-", " ").replace("_", " ").split())
        id_words = set(str(element.get("id", "")).lower().replace("-", " ").replace("_", " ").split())
        structural_words = data_test_words | id_words
        structural_content = structural_words & desc_content_words
        if len(structural_content) >= 2:
            return 80 + len(structural_content) * 5
        return 0

    @staticmethod
    def _href_bonus(
        action: str, description: str, desc_words: set[str], element: dict[str, Any], element_words: set[str]
    ) -> int:
        bonus = 0
        href = str(element.get("href", "")).strip().lower()
        if action == "CLICK" and "cart" in desc_words and ("cart" in href or "cart" in element_words):
            bonus += 2
        if action == "CLICK" and "checkout" in desc_words and "checkout" in href:
            bonus += 2
        if action == "CLICK" and "checkout" in desc_words and "payment" in href and "payment" not in desc_words:
            bonus -= 3
        return bonus

    @staticmethod
    def _product_id_bonus(
        action: str, description: str, desc_words: set[str], element: dict[str, Any], element_words: set[str]
    ) -> int:
        if action != "CLICK" or not {"add", "cart"}.issubset(desc_words):
            return 0
        raw_product_words = (
            SemanticMatcher.get_words(description, expand_aliases=False) - PlaceholderScorer.PRODUCT_FILTER_WORDS
        )
        product_words = desc_words - PlaceholderScorer.PRODUCT_FILTER_WORDS
        bonus = 0
        if product_words:
            matched_product_words = len(product_words.intersection(element_words))
            bonus += matched_product_words * 4
            element_id_lower = str(element.get("id", "")).lower().replace("-", " ").replace("_", " ")
            product_word_set = set(" ".join(raw_product_words).lower().split())
            if product_word_set and all(pw in element_id_lower for pw in product_word_set):
                bonus += 20
        return bonus

    @staticmethod
    def _assert_cart_penalty(action: str, description: str, desc_words: set[str], element: dict[str, Any]) -> int:
        if (
            action == "ASSERT"
            and {"cart", "product"}.intersection(desc_words)
            and "cart" in str(element.get("href", "")).lower()
        ):
            return -2
        return 0

    @staticmethod
    def _assertion_candidate_bonus(action: str, element: dict[str, Any]) -> int:
        if action == "ASSERT":
            role = (element.get("role", "") or "").lower()
            tag = (element.get("tag", "") or "").lower()
            text = (element.get("text", "") or "").strip()
            aria_label = (element.get("aria_label", "") or "").strip()
            if role in {"status", "alert", "log", "marquee"} or tag in {"div", "p", "span"} and (text or aria_label):
                return 2
        return 0

    @staticmethod
    def _role_bonus(action: str, description: str, element: dict[str, Any]) -> int:
        role = str(element.get("role", "")).strip().lower()
        bonus = 0
        if "link" in description.lower() and role == "a":
            bonus += 1
        if "button" in description.lower() and role in {"button", "submit"}:
            bonus += 1
        return bonus

    @staticmethod
    def _journey_discovered_bonus(element: dict[str, Any]) -> int:
        if element.get("_journey_discovered") == "true":
            return 5
        return 0

    @staticmethod
    def _click_role_bonus(action: str, element: dict[str, Any]) -> int:
        if action != "CLICK":
            return 0
        role = str(element.get("role", "")).strip().lower()
        href = str(element.get("href", "")).strip()
        text = str(element.get("text", "")).strip()
        selector = str(element.get("selector", "")).strip().lower()
        bonus = 0
        if role in {"button", "link", "a", "submit"}:
            bonus += 3
        if href:
            bonus += 2
        if not text and not href and "data-" in selector:
            bonus -= 4
        return bonus

    @staticmethod
    def _fill_bonus(action: str, element: dict[str, Any]) -> int:
        if action == "FILL" and PlaceholderScorer._is_fillable(element):
            return 3
        return 0

    @staticmethod
    def _assert_visibility_penalty(action: str, element: dict[str, Any]) -> int:
        if action == "ASSERT" and element.get("is_visible") is False:
            return -40
        return 0

    @staticmethod
    def _click_text_penalty(action: str, description: str, desc_words: set[str], element: dict[str, Any]) -> int:
        if action != "CLICK":
            return 0
        element_text = str(element.get("text", "")).strip()
        desc_content_words = desc_words - {"click", "tap", "press"}
        if not element_text and desc_content_words:
            data_test = str(element.get("data_test", "")).lower().replace("-", " ").replace("_", " ")
            element_id = str(element.get("id", "")).lower().replace("-", " ").replace("_", " ")
            structural_haystack = f"{data_test} {element_id}"
            structural_words = set(structural_haystack.split())
            structural_overlap = len(desc_content_words & structural_words)
            if structural_overlap >= 2:
                return -2
            return -10
        return 0

    @staticmethod
    def _assert_single_class_penalty(action: str, selector: str, element: dict[str, Any]) -> int:
        if action != "ASSERT":
            return 0
        selector_lower = selector.lower()
        is_single_class = (
            selector_lower.startswith(".")
            and selector_lower.count(".") == 1
            and "[" not in selector_lower
            and "#" not in selector_lower
        )
        element_text = str(element.get("text", "")).strip()
        if is_single_class and not element_text:
            return -5
        return 0

    @staticmethod
    def _visual_enrichment_bonus(
        action: str,
        description: str,
        element: dict[str, Any],
        lowered: str,
        icon_classes: str,
        visual_desc: str,
        parent_text: str,
    ) -> int:
        if action != "CLICK":
            return 0
        bonus = 0
        is_icon = element.get("is_icon", False)
        is_decorative = element.get("is_decorative", False)
        if is_decorative:
            bonus -= 10
        if is_icon:
            if any(term in lowered for term in PlaceholderScorer.ICON_SIGNAL_TERMS):
                bonus += 3
            if icon_classes and any(term in icon_classes for term in PlaceholderScorer.ICON_CLASS_PREFIXES):
                bonus += 2
            if visual_desc and any(term in visual_desc for term in ("icon", "button", "label", "aria-label")):
                bonus += 1
        # Parent text bonus
        if parent_text and parent_text != lowered:
            parent_words = set(parent_text.split())
            desc_word_set = set(lowered.replace("_", " ").split())
            parent_overlap = len(parent_words.intersection(desc_word_set))
            if parent_overlap > 0:
                bonus += parent_overlap
        # Visual description bonus
        if visual_desc and visual_desc != lowered:
            visual_words = set(visual_desc.replace("_", " ").split())
            desc_word_set = set(lowered.replace("_", " ").split())
            visual_overlap = len(visual_words.intersection(desc_word_set))
            if visual_overlap > 0:
                bonus += visual_overlap
        return bonus

    # ------------------------------------------------------------------
    # B-014: ASSERT intent-aware scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _is_message_like_assertion(description: str) -> bool:
        """Return True if the description signals a message-like assertion target."""
        lowered = description.lower()
        return any(term in lowered for term in PlaceholderScorer.MESSAGE_LIKE_TERMS)

    @staticmethod
    def _assert_action_penalty(action: str, description: str, element: dict[str, Any]) -> int:
        """Penalize interactive elements for ASSERT targeting message-like descriptions.

        ASSERT for "confirmation message" should not resolve to buttons or
        action-oriented links. This penalty ensures display elements are
        preferred over interactive ones for message assertions.
        """
        if action != "ASSERT":
            return 0

        if not PlaceholderScorer._is_message_like_assertion(description):
            return 0

        role = str(element.get("role", "")).strip().lower()
        tag = str(element.get("tag", "")).strip().lower()
        href = str(element.get("href", "")).strip()

        # Buttons are poor assertion targets for messages
        if role in {"button", "submit"} or tag == "button":
            return -15

        # Links with action-oriented hrefs are poor targets
        if (role == "link" or tag == "a") and href:
            if any(term in href.lower() for term in ("delete", "remove", "cart", "action")):
                return -10

        return 0

    @staticmethod
    def _assert_message_bonus(action: str, description: str, element: dict[str, Any]) -> int:
        """Reward display elements for ASSERT targeting message-like descriptions.

        Dialog/alert roles and content elements with confirmation-like text
        are ideal targets for ASSERT tokens seeking messages.
        """
        if action != "ASSERT":
            return 0

        if not PlaceholderScorer._is_message_like_assertion(description):
            return 0

        role = str(element.get("role", "")).strip().lower()
        tag = str(element.get("tag", "")).strip().lower()
        text = str(element.get("text", "")).strip().lower()
        aria_label = str(element.get("aria_label", "")).strip().lower()
        aria_role = str(element.get("aria_role", "")).strip().lower()

        # Dialog/alert roles are ideal for confirmation messages
        if role in {"dialog", "alertdialog", "alert", "status"}:
            return 15

        # ARIA-based alert roles
        if aria_role in {"dialog", "alertdialog", "alert", "status"}:
            return 12

        # Content elements with confirmation-like text
        if tag in {"div", "p", "span"} and text:
            if any(term in text for term in PlaceholderScorer.CONFIRMATION_TEXT_TERMS):
                return 10

        # ARIA label with confirmation-like content
        if aria_label and any(term in aria_label for term in PlaceholderScorer.CONFIRMATION_TEXT_TERMS):
            return 8

        return 0

    @staticmethod
    def _text_content_bonus(description: str, element: dict[str, Any]) -> int:
        """Reward elements whose text content overlaps with the description."""
        element_text = str(element.get("text", "")).strip()
        if not element_text:
            return 0
        norm_elem_text = re.sub(r"[_\s]+", " ", element_text).strip().lower()
        norm_desc_text = re.sub(r"['\"']", "", description)
        norm_desc_text = re.sub(r"[_\s]+", " ", norm_desc_text).strip().lower()
        if norm_elem_text in norm_desc_text or norm_desc_text in norm_elem_text:
            return 10
        # Word overlap fallback
        elem_text_words = set(norm_elem_text.split())
        desc_text_words = set(norm_desc_text.split()) - PlaceholderScorer.ACTION_CONTEXT_WORDS
        if desc_text_words:
            text_overlap = len(elem_text_words & desc_text_words)
            if text_overlap >= max(1, len(desc_text_words) // 2):
                return 5
        return 0
