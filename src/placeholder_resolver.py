"""Resolve placeholder descriptions against scraped page elements.

Orchestrates semantic matching (SemanticMatcher) and intent filtering
(IntentMatcher) to produce ranked candidate lists and final selector
resolutions for pytest-style Playwright tests.

Includes LLM-based disambiguation for near-tie candidates (Session 1 of
UAT fix series). When rule-based scoring produces top-2 candidates within
a score threshold, the LLM is consulted with Aria snapshot context.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from src.intent_matcher import IntentMatcher
from src.llm_client import LLMClient
from src.llm_reasoning_filter import strip_llm_reasoning
from src.locator_builder import build_robust_locator
from src.semantic_matcher import SemanticMatcher

logger = logging.getLogger(__name__)

# ── LLM Disambiguation Configuration ────────────────────────────────────────
# Trigger when top-2 candidate scores differ by ≤ this many points.
_DEFAULT_DISAMBIGUATION_THRESHOLD = 5

# Maximum number of candidates to send to the LLM for disambiguation.
_MAX_DISAMBIGUATION_CANDIDATES = 3


def _default_disambiguation_threshold() -> int:
    """Return the disambiguation threshold from environment or default."""
    try:
        return int(os.environ.get("DISAMBIGUATION_THRESHOLD", "5"))
    except (ValueError, TypeError):
        return _DEFAULT_DISAMBIGUATION_THRESHOLD


def _use_llm_disambiguation() -> bool:
    """Return whether LLM disambiguation is enabled via environment."""
    value = os.environ.get("USE_LLM_DISAMBIGUATION", "true").lower()
    return value not in ("false", "0", "no")


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
    except (ValueError, TypeError):
        return 0.3


class PlaceholderResolver:
    """Match placeholder descriptions to real scraped locators."""

    def __init__(
        self,
        match_threshold: int = 1,
        min_confidence: float | None = None,
        use_llm_disambiguation: bool | None = None,
        disambiguation_threshold: int | None = None,
    ) -> None:
        self.match_threshold = match_threshold
        self.min_confidence = min_confidence if min_confidence is not None else _default_min_confidence()
        self.use_llm_disambiguation = (
            use_llm_disambiguation if use_llm_disambiguation is not None else _use_llm_disambiguation()
        )
        self.disambiguation_threshold = (
            disambiguation_threshold if disambiguation_threshold is not None else _default_disambiguation_threshold()
        )

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
        Strips action-context words from the description to focus on core intent words.
        For example: "Add to cart button next to a product" becomes "add cart product"
        which can now match element text "Add to cart".

        Intent-level filtering is handled by _matches_intent_bucket() in rank_candidates().
        This method only validates text overlap, not intent compatibility.
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
            return overlap >= max(1, len(desc_words) // 2)

        return False

    @staticmethod
    def _extract_aria_snapshot(page_elements: list[dict[str, Any]]) -> str | None:
        """Extract Aria snapshot metadata from page elements.

        The Aria snapshot is stored as a special element dict with __meta__ key
        (Option A from the spec). This keeps the pipeline API unchanged.
        """
        for element in page_elements:
            if element.get("__meta__") == "aria_snapshot":
                return element.get("text", "")
        return None

    @staticmethod
    def _filter_aria_snapshot(page_elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return page elements excluding Aria snapshot metadata entries."""
        return [el for el in page_elements if el.get("__meta__") != "aria_snapshot"]

    def _disambiguate_with_llm(
        self,
        action: str,
        description: str,
        top_candidates: list[tuple[int, dict[str, Any]]],
        aria_snapshot: str | None = None,
    ) -> dict[str, Any] | None:
        """Use the LLM to pick the best element when rule-based scoring produces a tie.

        When the top-2 candidates are within DISAMBIGUATION_THRESHOLD points,
        delegate to the LLM with structured context (Aria snapshot + candidate details).

        Args:
            action: Placeholder action (CLICK, FILL, ASSERT, GOTO).
            description: Placeholder description text.
            top_candidates: Top N scored candidates from rank_candidates().
            aria_snapshot: Aria snapshot text from page.ariaSnapshot() — optional fallback context.

        Returns:
            The winning element dict, or None if LLM unavailable or response unparsable.
        """
        if len(top_candidates) < 2:
            return None

        # Limit to MAX_DISAMBIGUATION_CANDIDATES to keep the prompt small.
        candidates_to_send = top_candidates[:_MAX_DISAMBIGUATION_CANDIDATES]

        # Build candidate option lines
        option_lines: list[str] = []
        for idx, (_score, element) in enumerate(candidates_to_send, start=1):
            text = str(element.get("text", "")).strip()
            role = str(element.get("role", "")).strip()
            selector = str(element.get("selector", "")).strip()
            element_id = str(element.get("id", "")).strip()
            aria_label = str(element.get("aria_label", "")).strip() or str(element.get("accessible_name", "")).strip()
            line = f'{idx}. text="{text}", role="{role}", selector="{selector}"'
            if element_id:
                line += f', id="{element_id}"'
            if aria_label:
                line += f', aria="{aria_label}"'
            option_lines.append(line)

        # Build the prompt
        prompt_parts: list[str] = [
            f'Pick the element that matches: {action} "{description}"',
            "",
            "Options:",
        ]
        prompt_parts.extend(option_lines)

        if aria_snapshot:
            prompt_parts.append("")
            prompt_parts.append("Page accessibility context:")
            # Truncate snapshot to avoid excessive tokens
            snapshot_excerpt = aria_snapshot[:2000] if len(aria_snapshot) > 2000 else aria_snapshot
            prompt_parts.append(snapshot_excerpt)

        prompt_parts.append("")
        prompt_parts.append(f"Return only the number (1-{len(candidates_to_send)}) of the best match.")

        prompt = "\n".join(prompt_parts)

        try:
            client = LLMClient()
            # generate_test() is the sync method; _extract_code + normalise are applied internally.
            # For a simple numeric answer this is fine — strip_reasoning as a safety net.
            response = client.generate_test(prompt, timeout=30)
            cleaned = strip_llm_reasoning(response)

            # Extract a single digit from the response
            digits = re.findall(r"\d+", cleaned)
            if digits:
                choice = int(digits[0])
                if 1 <= choice <= len(candidates_to_send):
                    logger.debug(
                        "LLM disambiguation selected option %d for '%s' (action=%s)",
                        choice,
                        description,
                        action,
                    )
                    return candidates_to_send[choice - 1][1]

            logger.debug("LLM disambiguation returned unparsable response: %s", cleaned)
        except Exception as e:
            logger.debug("LLM disambiguation failed (%s) — falling back to rule-based scoring", e)

        return None

    def find_best_element(
        self,
        action: str,
        description: str,
        page_elements: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the best element match for a placeholder description.

        Elements whose visible text doesn't match the description are skipped.
        If the best candidate's confidence score is below ``min_confidence``,
        the method returns ``None`` (skip rather than guess).
        """
        ranked_candidates = self.rank_candidates(action, description, page_elements)
        if not ranked_candidates:
            return None

        # Extract Aria snapshot metadata from page_elements (Option A — __meta__ element)
        aria_snapshot = self._extract_aria_snapshot(page_elements)

        # LLM Disambiguation: when top-2 candidates are within threshold, delegate to LLM.
        llm_pick: dict[str, Any] | None = None
        if self.use_llm_disambiguation and len(ranked_candidates) >= 2:
            top_score = ranked_candidates[0][0]
            second_score = ranked_candidates[1][0]
            if top_score - second_score <= self.disambiguation_threshold:
                logger.debug(
                    "Disambiguation triggered: top=%d, second=%d (threshold=%d) for '%s'",
                    top_score,
                    second_score,
                    self.disambiguation_threshold,
                    description,
                )
                llm_pick = self._disambiguate_with_llm(
                    action,
                    description,
                    ranked_candidates[:_MAX_DISAMBIGUATION_CANDIDATES],
                    aria_snapshot=aria_snapshot,
                )
                # Validate LLM pick against text + confidence before accepting
                if llm_pick is not None:
                    pick_text = str(llm_pick.get("text", "")).strip()
                    pick_value = str(llm_pick.get("value", "")).strip()
                    pick_accessible = str(llm_pick.get("accessible_name", "")).strip()
                    if (
                        self.text_matches_description(pick_text, description)
                        or self.text_matches_description(pick_value, description)
                        or self.text_matches_description(pick_accessible, description)
                    ):
                        # Find the score for this pick
                        pick_score: int | None = None
                        for _s, _el in ranked_candidates:
                            if _el is llm_pick or _el.get("selector") == llm_pick.get("selector"):
                                pick_score = _s
                                break
                        if pick_score is not None:
                            max_possible = max(c[0] for c in ranked_candidates)
                            confidence = pick_score / max_possible if max_possible > 0 else 0.0
                            if confidence >= self.min_confidence:
                                logger.debug("LLM disambiguation pick accepted: %s", llm_pick.get("selector"))
                                return llm_pick

        # Filter by text-content validation (B1)
        for score, element in ranked_candidates:
            element_text = str(element.get("text", "")).strip()
            element_value = str(element.get("value", "")).strip()
            element_accessible = str(element.get("accessible_name", "")).strip()

            # Check visible text, input value, AND accessible_name from a11y tree (AI-024)
            # accessible_name is critical for icon-only elements (e.g., shopping cart icon
            # with empty text but accessible_name="Shopping cart")
            text_match = self.text_matches_description(element_text, description)
            value_match = self.text_matches_description(element_value, description)
            accessible_match = self.text_matches_description(element_accessible, description)

            if text_match or value_match or accessible_match:
                # Verify confidence threshold (B2)
                max_possible_score = max(c[0] for c in ranked_candidates)
                confidence = score / max_possible_score if max_possible_score > 0 else 0.0
                if confidence >= self.min_confidence:
                    return element
                logger.debug(
                    "Candidate '%s' (value='%s') confidence %.2f below threshold %.2f — marking unresolved",
                    element_text,
                    element_value,
                    confidence,
                    self.min_confidence,
                )
            elif element_text or element_value:
                logger.debug(
                    "Skipped candidate '%s' (value='%s') — text does not match description '%s'",
                    element_text,
                    element_value,
                    description,
                )
            else:
                # Elements with no visible text AND no value — accept if _matches_intent_bucket passed.
                # This covers saucedemo-style login forms where #user-name, #password, #login-button
                # have empty text but stable id/data-test attributes that already matched.
                id_val = str(element.get("id", "")).strip()
                data_test = str(element.get("data_test", "")).strip()
                has_stable_id = bool(id_val or data_test)
                if has_stable_id:
                    max_possible_score = max(c[0] for c in ranked_candidates)
                    confidence = score / max_possible_score if max_possible_score > 0 else 0.0
                    if confidence >= self.min_confidence:
                        logger.debug(
                            "Accepted textless element '%s' (id='%s', data_test='%s') confidence %.2f",
                            str(element.get("selector", "")),
                            id_val,
                            data_test,
                            confidence,
                        )
                        return element
                    logger.debug(
                        "Rejected textless element '%s' (id='%s', data_test='%s') — confidence %.2f below threshold %.2f",
                        str(element.get("selector", "")),
                        id_val,
                        data_test,
                        confidence,
                        self.min_confidence,
                    )

        return None

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

            # Extract visual enrichment variables for use in scoring
            lowered = description.replace("_", " ").lower()
            icon_classes = str(element.get("icon_classes", "")).lower()
            visual_desc = str(element.get("visual_description", "")).lower()
            parent_text = str(element.get("parent_text", "")).lower()

            if action == "FILL" and not IntentMatcher._is_fillable(element):
                continue

            if not IntentMatcher.matches(action, description, element):
                continue

            haystack = self._build_element_haystack(element).lower()
            if haystack and normalized_description in haystack:
                if action == "ASSERT" and not self._is_assertion_candidate(element):
                    continue
                else:
                    # Base score is 100 for haystack matches, but apply product-ID bonus
                    # to differentiate between products (e.g., backpack vs fleece-jacket).
                    haystack_score = 100
                    if action == "CLICK" and {"add", "cart"}.issubset(desc_words):
                        # Use raw words (no expansion) for product-ID matching in haystack branch too.
                        raw_product_words = SemanticMatcher.get_words(description, expand_aliases=False) - {
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
                        if raw_product_words:
                            element_id_lower = str(element.get("id", "")).lower().replace("-", " ").replace("_", " ")
                            product_word_set = set(" ".join(raw_product_words).lower().split())
                            if product_word_set and all(pw in element_id_lower for pw in product_word_set):
                                haystack_score += 20
                    ranked.append((haystack_score, element))
                    continue

            element_words = SemanticMatcher.get_words(haystack, expand_aliases=False)
            score = len(desc_words.intersection(element_words))
            role = str(element.get("role", "")).strip().lower()
            href = str(element.get("href", "")).strip().lower()

            # Content words for scoring (defined early for use in structural match and penalty sections)
            desc_content_words = desc_words - {"click", "tap", "press"}

            # Structural match bonus: when data-test or id contains meaningful
            # description keywords, treat it as a strong match. This handles icon/nav
            # elements like [data-test="shopping-cart-link"] for "shopping cart icon"
            # where the haystack doesn't contain "icon" but the structural attribute
            # is a near-perfect match for the intent.
            data_test_words = set(str(element.get("data_test", "")).lower().replace("-", " ").replace("_", " ").split())
            id_words = set(str(element.get("id", "")).lower().replace("-", " ").replace("_", " ").split())
            structural_words = data_test_words | id_words
            # Only count meaningful content words (not stop words)
            structural_content = (
                structural_words & desc_content_words if action == "CLICK" else structural_words & desc_words
            )
            if len(structural_content) >= 2:
                # Strong structural match — boost to near-haystack level
                score = max(score, 80 + len(structural_content) * 5)

            if action == "CLICK" and "cart" in desc_words and ("cart" in href or "cart" in element_words):
                score += 2
            if action == "CLICK" and "checkout" in desc_words and "checkout" in href:
                score += 2
            if action == "CLICK" and "checkout" in desc_words and "payment" in href and "payment" not in desc_words:
                # Avoid jumping straight to payment when the user intent is checkout.
                score -= 3
            if action == "CLICK" and {"add", "cart"}.issubset(desc_words):
                # Use raw description words (without token expansion) for product-ID matching.
                # desc_words includes TOKEN_EXPANSIONS (e.g. "add" -> {"buy", "basket", "place"})
                # which would cause the all() check below to fail.  We need only the actual
                # product name words from the original description.
                raw_product_words = SemanticMatcher.get_words(description, expand_aliases=False) - {
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
                product_words = desc_words - {
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
                if product_words:
                    matched_product_words = len(product_words.intersection(element_words))
                    score += matched_product_words * 4
                    # Strong bonus when ALL product name words match the element ID.
                    # This ensures "Sauce Labs Backpack" prefers #add-to-cart-sauce-labs-backpack
                    # over #add-to-cart-sauce-labs-fleece-jacket. Without this, the tiebreaker
                    # (selector length) incorrectly favors longer IDs.
                    element_id_lower = str(element.get("id", "")).lower().replace("-", " ").replace("_", " ")
                    # Use raw words (no expansion) so "sauce labs backpack" checks against the ID
                    # rather than the expanded set {"sauce", "labs", "backpack", "buy", "basket", ...}.
                    product_word_set = set(" ".join(raw_product_words).lower().split())
                    if product_word_set and all(pw in element_id_lower for pw in product_word_set):
                        score += 20  # Large bonus for exact product-ID match
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
            #
            # EXCEPTION: icon/nav elements with strong structural matches (data-test or id
            # containing relevant description words) should NOT be penalized. IntentMatcher
            # already approved them, and the structural match is more reliable than text.
            # This fixes: "shopping cart icon" resolving to "Add to cart" button instead of
            # [data-test="shopping-cart-link"].
            if action == "CLICK":
                desc_content_words = desc_words - {"click", "tap", "press"}
                if not element_text and desc_content_words:
                    # Check for strong structural match: data-test or id contains description words
                    data_test = str(element.get("data_test", "")).lower().replace("-", " ").replace("_", " ")
                    element_id = str(element.get("id", "")).lower().replace("-", " ").replace("_", " ")
                    structural_haystack = f"{data_test} {element_id}"
                    structural_words = set(structural_haystack.split())
                    structural_overlap = len(desc_content_words & structural_words)
                    has_strong_structural_match = structural_overlap >= 2

                    if has_strong_structural_match:
                        # IntentMatcher approved + structural match — light penalty only
                        score -= 2
                    else:
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
        selector = build_robust_locator(best_element)
        if selector:
            return selector
        # Fallback to raw scraped selector if robust locator couldn't be built
        raw_selector = str(best_element.get("selector", "")).strip()
        return raw_selector if raw_selector else None

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
