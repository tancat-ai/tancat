"""Score locators by reliability/fragility based on locator type.

This module provides confidence scoring for Playwright selectors, enabling:
1. Controlled fallback — when a primary locator fails, try higher-scoring alternatives
2. Coverage validation — elements hit via fallbacks are "fragile coverage"
3. Suite heatmap — confidence levels feed into the Tier 3 redesign

Scoring hierarchy (higher = more stable across UI changes):
  100  — data-testid attribute (explicitly added for testing)
   85  — id attribute (stable, user-assigned)
   70  — name attribute (reliable for form elements)
   60  — aria-label / role (good but changes with UI copy)
   40  — CSS class-based selectors (Medium-Low)
   25  — visible text selectors (breaks when copy changes)
   10  — XPath with text() (fragile)
    5  — Bare tag selectors (Very Low — almost always fragile)

Based on BACKLOG AI-012 "Selector Confidence Scores".
"""

from __future__ import annotations

import re
from typing import Any


class LocatorScorer:
    """Score locators by reliability/fragility based on locator type."""

    __test__ = False

    # Confidence level ranges (non-overlapping, ordered lowest-first for iteration)
    CONFIDENCE_LEVELS: dict[str, tuple[int, int]] = {
        "very-low": (0, 14),
        "low": (15, 29),
        "medium-low": (30, 49),
        "medium": (50, 69),
        "medium-high": (70, 84),
        "high": (85, 100),
    }

    # Locator type scores (base score when the attribute is present)
    LOCATOR_SCORES: dict[str, int] = {
        "data-testid": 100,
        "id": 85,
        "name": 70,
        "aria-label": 60,
        "role": 55,
        "css-class": 40,
        "text": 25,
        "xpath-text": 10,
        "tag": 5,
    }

    # Fragility reasons for each locator type
    FRAGILITY_REASONS: dict[str, str] = {
        "data-testid": "data-testid attributes are explicitly added for testing and won't change accidentally",
        "id": "id attributes are stable but may be auto-generated in some frameworks",
        "name": "name attributes are reliable for form elements but may not exist on all elements",
        "aria-label": "aria-labels are good but change when UI copy is updated",
        "role": "role attributes are semantic but may change with component redesign",
        "css-class": "CSS classes may change during UI refactoring or design system updates",
        "text": "Visible text changes when copy is updated — brittle across content changes",
        "xpath-text": "XPath with text() is fragile — breaks on whitespace, encoding, or text changes",
        "tag": "Bare tag selectors match many elements — almost always fragile and non-specific",
    }

    @classmethod
    def score_locator(cls, selector: str, element: dict[str, Any] | None = None) -> dict[str, Any]:
        """Score a single locator and return metadata.

        Args:
            selector: The Playwright selector string to score.
            element: Optional scraped element dict for additional context.

        Returns:
            Dict with keys: selector, type, score, confidence, fragility_reason.
        """
        selector = selector.strip()
        if not selector:
            return {
                "selector": "",
                "type": "unknown",
                "score": 0,
                "confidence": "very-low",
                "fragility_reason": "Empty selector",
            }

        # Determine locator type and base score
        loc_type, base_score = cls._determine_locator_type(selector, element or {})

        # Apply modifiers based on specificity
        final_score = cls._apply_specificity_modifier(base_score, selector, loc_type)

        # Clamp score to valid range
        final_score = max(0, min(100, final_score))

        # Determine confidence label
        confidence = cls._score_to_confidence(final_score)

        return {
            "selector": selector,
            "type": loc_type,
            "score": final_score,
            "confidence": confidence,
            "fragility_reason": cls.FRAGILITY_REASONS.get(loc_type, "Unknown locator type"),
        }

    @classmethod
    def score_candidates(
        cls,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Score a list of locator candidates and return sorted by score descending.

        Each candidate is a dict with 'selector' and optionally 'element'
        (scraped element data with fields like id, aria_label, classes, etc.).

        Args:
            candidates: List of locator candidates to score.

        Returns:
            List of scored candidates sorted by score descending.
        """
        scored = []
        for candidate in candidates:
            selector = candidate.get("selector", "")
            element = candidate.get("element") or candidate.get("element_data", {})
            result = cls.score_locator(selector, element)
            result["element"] = element
            scored.append(result)

        # Sort by score descending, then by selector length (shorter = preferred)
        scored.sort(key=lambda x: (-x["score"], len(x["selector"])))
        return scored

    @classmethod
    def get_fallback_candidates(
        cls,
        failed_locator: str,
        all_candidates: list[dict[str, Any]],
        max_fallbacks: int = 2,
    ) -> list[dict[str, Any]]:
        """Get the top N fallback candidates that are higher-scoring than the failed locator.

        Args:
            failed_locator: The selector that failed.
            all_candidates: All available locator candidates from the page.
            max_fallbacks: Maximum number of fallbacks to return.

        Returns:
            List of scored fallback candidates, sorted by score descending.
        """
        # Score the failed locator
        failed_score = cls.score_locator(failed_locator)
        failed_score_value = failed_score["score"]

        # Score all candidates and filter to those with higher scores
        scored = cls.score_candidates(all_candidates)

        # Get candidates with higher scores, excluding the failed locator
        fallbacks = [c for c in scored if c["score"] > failed_score_value and c["selector"] != failed_locator][
            :max_fallbacks
        ]

        return fallbacks

    @classmethod
    def _determine_locator_type(
        cls,
        selector: str,
        element: dict[str, Any],
    ) -> tuple[str, int]:
        """Determine the locator type and base score from a selector string.

        Priority: Check for the most specific/reliable locator type first.

        Args:
            selector: The Playwright selector string.
            element: Scraped element data for additional context.

        Returns:
            Tuple of (locator_type, base_score).
        """
        # 1. data-testid — highest confidence
        if "[data-testid=" in selector or "data-testid=" in selector:
            return "data-testid", cls.LOCATOR_SCORES["data-testid"]

        # 2. id attribute — high confidence
        if re.search(r"#[a-zA-Z_][a-zA-Z0-9_-]*", selector):
            return "id", cls.LOCATOR_SCORES["id"]

        # 3. name attribute — medium-high confidence
        if re.search(r"\[name=", selector):
            return "name", cls.LOCATOR_SCORES["name"]

        # 4. aria-label — medium confidence
        if re.search(r"\[aria-label=", selector):
            return "aria-label", cls.LOCATOR_SCORES["aria-label"]

        # 5. role attribute — medium confidence
        if re.search(r"\[role=", selector):
            return "role", cls.LOCATOR_SCORES["role"]

        # 6. visible text selectors — low confidence
        if ":has-text(" in selector or ":has-text" in selector:
            return "text", cls.LOCATOR_SCORES["text"]

        # 7. XPath — very low confidence
        if selector.startswith("/") or selector.startswith("//"):
            return "xpath-text", cls.LOCATOR_SCORES["xpath-text"]

        # 8. CSS class-based — medium-low confidence
        if re.search(r"\.[a-zA-Z_][a-zA-Z0-9_-]*", selector):
            return "css-class", cls.LOCATOR_SCORES["css-class"]

        # 9. Bare tag — very low confidence
        if re.match(r"^[a-zA-Z][a-zA-Z0-9]*", selector):
            return "tag", cls.LOCATOR_SCORES["tag"]

        # Fallback: unknown type
        return "unknown", 0

    @classmethod
    def _apply_specificity_modifier(
        cls,
        base_score: int,
        selector: str,
        loc_type: str,
    ) -> int:
        """Apply modifiers to the base score based on selector specificity.

        More specific selectors get a small bonus; overly broad ones get a penalty.

        Args:
            base_score: The base score for this locator type.
            selector: The full selector string.
            loc_type: The determined locator type.

        Returns:
            Modified score (clamped to 0-100 by caller).
        """
        modifier = 0

        # Bonus for compound selectors (multiple criteria)
        # e.g., "button#submit" or "input[name='email']"
        if loc_type == "id":
            # Check if there's also a tag or class component
            if re.match(r"^[a-zA-Z]+#", selector):
                modifier += 5  # Tag + ID is very specific
            elif re.search(r"\.[a-zA-Z]", selector):
                modifier += 3  # ID + class is specific

        elif loc_type == "css-class":
            # Multiple classes = more specific = slightly more reliable
            class_count = len(re.findall(r"\.[a-zA-Z_][a-zA-Z0-9_-]*", selector))
            if class_count > 1:
                modifier += 5
            elif class_count == 1:
                modifier -= 5  # Single class is vague

        elif loc_type == "tag":
            # Bare tags are very vague — apply penalty
            modifier -= 3

        # Penalize selectors with multiple combinators (child, descendant, etc.)
        combinator_count = len(re.findall(r"\s+[\s>+~]\s+|\s+[\s>+~]", selector))
        if combinator_count > 2:
            modifier -= 5  # Deeply chained selectors are fragile

        return base_score + modifier

    @staticmethod
    def _score_to_confidence(score: int) -> str:
        """Convert a numeric score to a confidence level label."""
        for level, (low, high) in LocatorScorer.CONFIDENCE_LEVELS.items():
            if low <= score <= high:
                return level
        return "very-low"
