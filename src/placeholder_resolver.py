"""Resolve placeholder descriptions against scraped page elements.

Orchestrates semantic matching (SemanticMatcher) and intent filtering
(IntentMatcher) to produce ranked candidate lists for the live pipeline
(PlaceholderOrchestrator → rank_candidates → SemanticCandidateRanker).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from src.intent_matcher import IntentMatcher
from src.placeholder_scorers import PlaceholderScorer
from src.semantic_matcher import SemanticMatcher

logger = logging.getLogger(__name__)


def _css_escape_id(value: str) -> str:
    r"""Escape a raw ID value for safe use in a CSS #id selector.

    CSS selectors require certain characters to be escaped with backslashes.
    For example, an ID like ``add-to-cart-test.allthethings()-t-shirt-(red)``
    must become ``\(add-to-cart-test\.allthethings\(\)-t-shirt-\(red\)``
    to be parsed correctly by Playwright's CSS selector engine.

    Handles CSS special characters: space, tab, linefeed, #, ", ', \, ,, !, $,
    %, &, *, (, ), +, :, ;, <, =, >, ?, @, [, ], ^, `, {, |, }, ~ and control chars.
    """
    if not value:
        return value
    # CSS selector special characters that must be escaped in an ID component.
    # Per CSS Selectors Level 3, these need backslash escaping when not in a string.
    # CSS identifiers allow letters, digits, underscores, and hyphens without escaping.
    # Only escape true CSS delimiter/special characters.
    # See: https://drafts.csswg.org/selectors-3/#character-set
    escape_chars = r'"\'' + r"""#&*,/><:=?@[\]^`{|}~!$%();+""" + "\t\n\r\x0c"
    result = []
    for char in value:
        if char in escape_chars:
            result.append(f"\\{char}")
        else:
            result.append(char)
    return "".join(result)


def _default_min_confidence() -> float:
    """Return the minimum confidence threshold from environment or default."""
    try:
        return float(os.environ.get("PLACEHOLDER_MIN_CONFIDENCE", "0.3"))
    except ValueError, TypeError:
        return 0.3


class PlaceholderResolver:
    """Match placeholder descriptions to real scraped locators."""

    def __init__(
        self,
        match_threshold: int = 1,
        min_confidence: float | None = None,
    ) -> None:
        self.match_threshold = match_threshold
        self.min_confidence = min_confidence if min_confidence is not None else _default_min_confidence()

    def _build_element_haystack(self, element: dict[str, Any]) -> str:
        """Return a single string containing all searchable metadata for an element.

        All delimiters (hyphens, underscores) are normalized to spaces to ensure
        that 'login button' matches 'login-button'.
        """
        parts = [
            str(element.get("selector", "")),
            str(element.get("text", "")),
            str(element.get("role", "")),
            str(element.get("href", "")),
            str(element.get("title", "")),
            str(element.get("aria_label", "")),
            str(element.get("name", "")),
            str(element.get("id", "")),
            str(element.get("classes", "")),
            str(element.get("value", "")),
            str(element.get("placeholder", "")),
            str(element.get("icon_classes", "")),
            str(element.get("icon_unicode", "")),
            str(element.get("visual_description", "")),
            str(element.get("parent_text", "")),
            str(element.get("aria_icon_label", "")),
            str(element.get("accessible_name", "")),
            str(element.get("data_test", "")),
        ]
        # Normalize delimiters to spaces for better string containment matching
        raw_haystack = " ".join(part for part in parts if part).lower()
        return re.sub(r"[_-]+", " ", raw_haystack)

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

        if role in {
            "input",
            "textarea",
            "select",
            "textbox",
            "searchbox",
            "combobox",
            "email",
            "password",
            "text",
            "tel",
            "number",
        }:
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
        "click",
        "correctly",
        "dialog",
        "enter",
        "field",
        "fill",
        "for",
        "hover",
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
        Handles two common patterns:
        1. Direct text overlap: "Add to cart" matches "Add to cart button"
        2. Action + qualifier split: "add to cart button for Sauce Labs Backpack"
           splits on "for"/"next to"/"on" → action part "add to cart button" is validated
           against element text, ignoring the product qualifier.

        Intent-level filtering is handled by _matches_intent_bucket() in rank_candidates().
        This method only validates text overlap, not intent compatibility.
        """
        if not action_description:
            return False

        # Normalize underscores to spaces (LLM often generates "add_to_cart_button" style)
        # Strip LLM-generated quotes — common problem: "'Products'" should match "Products"
        norm_desc = re.sub(r"['\"']", "", action_description)
        norm_desc = re.sub(r"[_\s]+", " ", norm_desc).strip().lower()

        # Split description on qualifier separators to isolate the action part.
        # "add to cart button for Sauce Labs Backpack" -> "add to cart button"
        # "click remove button next to broken red light" -> "click remove button"
        action_part = re.split(r"\s+(?:for|next\s+to|beside|on|with|by|above|below)\s+", norm_desc)[0]

        if element_text:
            norm_text = re.sub(r"[_\s]+", " ", element_text).strip().lower()

            # Direct containment (most reliable check) - check against both full desc and action part
            if norm_text in norm_desc or norm_desc in norm_text:
                return True
            if norm_text in action_part or action_part in norm_text:
                return True

            # Word-level overlap with action-context words stripped
            desc_words = set(action_part.split()) - PlaceholderResolver.ACTION_CONTEXT_WORDS
            text_words = set(norm_text.split())
            if desc_words and text_words:
                overlap = len(desc_words & text_words)
                if overlap >= max(1, len(desc_words) // 2):
                    return True

            # Check if at least one significant action word overlaps
            action_words = set(action_part.split()) & PlaceholderResolver.ACTION_VERBS
            if action_words and action_words & text_words:
                return True

        return False

    def rank_candidates(
        self,
        action: str,
        description: str,
        page_elements: list[dict[str, Any]],
    ) -> list[tuple[int, dict[str, Any]]]:
        """Return scored candidate elements in descending match order."""
        desc_words = SemanticMatcher.get_words(description)
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

            # Penalize elements marked as invisible at runtime (Session 2: Visibility Capture).
            # Elements with is_visible=False were checked against the live browser DOM and found
            # to be hidden (display:none, off-screen, behind overlays, etc.). Prefer visible
            # candidates so generated tests interact with actually-useful page elements.
            if element.get("is_visible") is False:
                if action != "ASSERT":
                    logger.debug(
                        "Skipping hidden element '%s' (is_visible=False) for placeholder '%s' (action=%s)",
                        selector,
                        description,
                        action,
                    )
                    continue
                # For ASSERT: continue but apply heavy visibility penalty in scorer

            # Intent gate — skip elements that don't match the action intent
            if action == "FILL" and not IntentMatcher._is_fillable(element):
                continue

            if not IntentMatcher.matches(action, description, element):
                continue

            # ASSERT gate: haystack matches must be assertion candidates
            haystack = self._build_element_haystack(element).lower()
            if haystack and normalized_description in haystack:
                if action == "ASSERT" and not self._is_assertion_candidate(element):
                    continue

            # Delegate scoring to PlaceholderScorer
            score = PlaceholderScorer.compute_element_score(
                action, description, element, selector, self.match_threshold
            )
            if score is not None:
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

    def resolve_url(self, description: str, pages_data: dict[str, list[dict[str, Any]]]) -> str | None:
        """Resolve navigation placeholders to the best matching scraped URL."""
        if not pages_data:
            return None

        desc_words = SemanticMatcher.get_words(description)
        if not desc_words:
            first_url = next(iter(pages_data), None)
            return first_url

        best_score = -1
        best_url: str | None = None

        for url, elements in pages_data.items():
            parsed = urlparse(url)
            path_words = SemanticMatcher.get_words((parsed.path or "/").replace("/", " "), expand_aliases=False)
            page_words = set(path_words)
            for element in elements[:25]:
                page_words.update(
                    SemanticMatcher.get_words(self._build_element_haystack(element), expand_aliases=False)
                )

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
