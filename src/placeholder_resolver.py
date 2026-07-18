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
        raw_haystack = " ".join(part for part in parts if part).lower()
        return re.sub(r"[_-]+", " ", raw_haystack)

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
        "click",
    }

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

    # B-016: Negation words that signal the absence or emptiness of content.
    # Universal — not domain-specific. When the element text contains these but
    # the description signals positive content, the match is rejected.
    _NEGATION_WORDS: frozenset[str] = frozenset(
        {
            "empty",
            "none",
            "no items",
            "no results",
            "not found",
            "nothing",
            "no data",
            "not available",
            "unavailable",
            "out of stock",
            "sold out",
            "deleted",
            "removed",
        }
    )

    # B-016: Positive-content indicators — presence signals in the description
    # that contradict a negation word in the element text.
    _POSITIVE_INDICATORS: frozenset[str] = frozenset(
        {
            "with items",
            "selected",
            "loaded",
            "present",
            "available",
            "in cart",
            "in basket",
            "content",
            "results",
            "found",
            "displayed",
            "shown",
            "visible",
            "non-empty",
            "has",
            "contains",
        }
    )

    @staticmethod
    def _is_negated(element_text: str, action_description: str) -> bool:
        """Return True when element text signals absence but description signals presence.

        E.g. element says "Your cart is empty!" but description says "cart content with items".
        This is a domain-agnostic heuristic — negation vs. presence contradiction.
        """
        has_negation = any(neg in element_text for neg in PlaceholderResolver._NEGATION_WORDS)
        has_positive = any(pos in action_description for pos in PlaceholderResolver._POSITIVE_INDICATORS)
        return has_negation and has_positive

    @staticmethod
    def text_matches_description(element_text: str, action_description: str) -> bool:
        """Check if element's visible text plausibly matches the action description.

        Strategy (fast-to-slow):
        1. Negation gate (B-016) — reject absence-vs-presence contradictions.
        2. Direct containment — substring match after normalisation.
        3. Key phrase extraction (R-001) — match short element text against
           key phrases from verbose descriptions.
        4. Word-overlap — keyword intersection minus context words.
        5. Action-verb check — shared action verbs signal intent match.
        6. Semantic similarity (B-016) — delegate to SemanticMatcher for
           synonym-aware Jaccard scoring. Threshold 0.25 catches "Login"≈"Sign in"
           without false-positive noise.
        """
        if not action_description:
            return False

        norm_desc = re.sub(r"['\"']", "", action_description)
        norm_desc = re.sub(r"[_\s]+", " ", norm_desc).strip().lower()
        action_part = re.split(r"\s+(?:for|next\s+to|beside|on|with|by|above|below)\s+", norm_desc)[0]

        if not element_text:
            return False

        norm_text = re.sub(r"[_\s]+", " ", element_text).strip().lower()

        # B-016: Negation gate — reject when element signals absence but description
        # signals positive content (e.g. "cart is empty" ≠ "cart with items").
        if PlaceholderResolver._is_negated(norm_text, norm_desc):
            return False

        # --- Original matching logic (unchanged) ---
        if norm_text in norm_desc or norm_desc in norm_text:
            return True
        if norm_text in action_part or action_part in norm_text:
            return True

        # R-001: Key phrase extraction for verbose descriptions.
        # Descriptions like "Dress category link in the left sidebar" should match
        # element text "Dress". Extract quoted substrings and noun phrases.
        key_phrases: list[str] = []
        quoted = re.findall(r'["\']([^"\']+)["\']', norm_desc)
        key_phrases.extend(quoted)

        # Extract noun phrase before context words
        context_words = {
            "link",
            "button",
            "in",
            "on",
            "at",
            "next",
            "to",
            "beside",
            "section",
            "list",
            "menu",
            "header",
            "page",
            "sidebar",
            "navigation",
            "the",
            "a",
            "an",
        }
        words = norm_desc.split()
        noun_words: list[str] = []
        for w in words:
            if w in context_words:
                break
            if len(w) > 1 and w not in PlaceholderResolver.ACTION_CONTEXT_WORDS:
                noun_words.append(w)
        if len(noun_words) >= 1:
            key_phrases.append(" ".join(noun_words))

        # Also try the last meaningful phrase (e.g., "Blue Top" from "Add to cart button next to Blue Top")
        # by splitting on common prepositions
        preposition_split = re.split(
            r"\s+(?:next\s+to|beside|before|after|above|below|under|near|around)\s+", norm_desc
        )
        if len(preposition_split) > 1:
            last_phrase = preposition_split[-1].strip()
            if last_phrase:
                key_phrases.append(last_phrase)

        for phrase in key_phrases:
            phrase_words = len(phrase.split())
            text_word_count = len(norm_text.split())
            if phrase_words > 0:
                word_ratio = max(text_word_count, phrase_words) / min(text_word_count, phrase_words)
                # Accept if word ratio <= 3 to avoid "cart" matching "Add to cart"
                # while still allowing "Backpack" ≈ "Sauce Labs Backpack"
                if word_ratio < 3 and (norm_text == phrase or phrase in norm_text or norm_text in phrase):
                    return True

        desc_words = set(action_part.split()) - PlaceholderResolver.ACTION_CONTEXT_WORDS
        text_words = set(norm_text.split())
        if desc_words and text_words:
            overlap = len(desc_words & text_words)
            if overlap >= max(1, len(desc_words) // 2):
                return True

        action_words = set(action_part.split()) & PlaceholderResolver.ACTION_VERBS
        if action_words and action_words & text_words:
            return True

        # B-016: Synonym-aware fallback — catches "Login" vs "Sign in" via
        # SemanticMatcher.TOKEN_EXPANSIONS (the single source of synonym truth).
        #
        # Uses two metrics to avoid the false-positive / false-negative trade-off:
        # 1. Recall (desc_tokens ⊆ text_tokens): if every meaningful word from
        #    the description is covered by the element's expanded token set, match.
        #    This handles "Create account" ⊆ expanded("Sign Up") even when Jaccard
        #    is diluted by one-sided expansions.
        # 2. Jaccard (intersection / union): catches symmetric overlaps like
        #    "Login" / "Sign in" where both sides have comparable expansion sizes.
        #    Threshold 0.25 is conservative — the containment and word-overlap gates
        #    above already handled easy cases, so this fires only on borderline matches.
        syn_desc_tokens = SemanticMatcher.get_words(action_part, expand_aliases=True)
        syn_text_tokens = SemanticMatcher.get_words(norm_text, expand_aliases=True)
        if syn_desc_tokens and syn_text_tokens:
            # Recall: description fully covered by element tokens?
            if syn_desc_tokens.issubset(syn_text_tokens):
                return True
            # Jaccard: symmetric overlap
            syn_union = syn_desc_tokens | syn_text_tokens
            syn_intersection = syn_desc_tokens & syn_text_tokens
            if syn_union:
                jaccard = len(syn_intersection) / len(syn_union)
                if jaccard >= 0.25:
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

            role = str(element.get("role", "")).strip().lower()
            if role == "hidden":
                continue

            if element.get("is_visible") is False:
                if action != "ASSERT":
                    logger.debug(
                        "Skipping hidden element '%s' (is_visible=False) for placeholder '%s' (action=%s)",
                        selector,
                        description,
                        action,
                    )
                    continue

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

        # Sort globally: 1) score desc, 2) text length desc, 3) selector specificity desc.
        ranked.sort(
            key=lambda item: (
                item[0],
                len(str(item[1].get("text", "")).strip()),
                len(str(item[1].get("selector", "")).strip()),
            ),
            reverse=True,
        )

        # Enforce global slice cap across all available pool items
        return ranked[:20]

    def resolve_url(
        self, description: str, pages_data: dict[str, list[dict[str, Any]]], known_urls: list[str] | None = None
    ) -> str | None:
        """Resolve navigation placeholders to the best matching scraped URL.

        First checks if description is a URL, then checks known_urls,
        then matches against already scraped pages.
        """
        # 1. Direct URL match - but validate it exists in scraped data
        if description.startswith("http") or (description.startswith("/") and len(description) > 1):
            # Validate the URL exists in scraped data before returning it
            if pages_data and description in pages_data:
                return description
            # URL not in scraped data - fall through to keyword matching
            logger.debug(
                "URL '%s' not found in scraped data, falling back to keyword matching",
                description,
            )

        # 2. Match against known URLs (provided by orchestrator)
        if known_urls:
            desc_norm = description.lower().strip()
            for url in known_urls:
                parsed = urlparse(url)
                path_norm = (parsed.path or "/").lower().replace("/", " ")
                if desc_norm in path_norm or path_norm in desc_norm:
                    return url

        if not pages_data:
            return None

        desc_words = SemanticMatcher.get_words(description)
        if not desc_words:
            return next(iter(pages_data), None)

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
