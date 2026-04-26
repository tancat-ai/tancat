"""Locator fallback strategies for Tier 2 controlled fallback.

This module provides higher-scoring locator alternatives when the primary
locator fails, with full confidence scoring and audit trail.

Part of the Tier 2: Locator Scoring + Controlled Fallback architecture.
"""

from __future__ import annotations

from typing import Any

from src.locator_scorer import LocatorScorer


class LocatorFallback:
    """Controlled locator fallback with scoring and audit trail.

    When a primary locator fails, this class:
    1. Builds candidate selectors from the current page DOM
    2. Scores candidates using ``LocatorScorer``
    3. Tries the top 2 higher-scoring alternatives
    4. Returns an audit trail with scores and confidence levels
    """

    @staticmethod
    def build_candidates(
        primary_locator: str,
        el_metadata: dict[str, Any],
        page: Any,
    ) -> list[dict[str, Any]]:
        """Build a list of locator candidates from the current page DOM.

        Uses JavaScript to extract candidate selectors for the same element
        (or similar elements) that could serve as alternatives.

        Args:
            primary_locator: The original selector that failed.
            el_metadata: Element metadata from the primary locator.
            page: Playwright Page instance for JS evaluation.

        Returns:
            List of candidate dicts with ``selector`` and ``element`` keys.
        """
        candidates: list[dict[str, Any]] = []

        # If we have element metadata with an id, build candidates from it
        element_id = el_metadata.get("element_id")
        if element_id:
            # Try id-based selectors (high confidence)
            candidates.append({"selector": f"#{element_id}", "element": el_metadata})
            # Try with tag prefix
            tag = el_metadata.get("tag", "")
            if tag:
                candidates.append({"selector": f"{tag}#{element_id}", "element": el_metadata})

        # Extract candidates from the current page via JavaScript
        # Get all interactive elements and build their common selectors
        try:
            page_candidates = page.evaluate(
                """
                (primarySelector) => {
                    const candidates = [];

                    try {
                        const el = document.querySelector(primarySelector.split('[')[0].replace(/[.#]/, '.'));
                        if (el) {
                            const sel = {
                                id: el.id ? `#${el.id}` : null,
                                testid: el.dataset?.testid ? `[data-testid="${el.dataset.testid}"]` : null,
                                name: el.name ? `[name="${el.name}"]` : null,
                                ariaLabel: el.getAttribute('aria-label') ? `[aria-label="${el.getAttribute('aria-label')}"]` : null,
                                role: el.getAttribute('role') ? `[role="${el.getAttribute('role')}"]` : null,
                                classes: el.className?.baseVal || el.className ? `.${(el.className.baseVal || el.className).split(' ').filter(Boolean).slice(0, 2).join('.')}` : null,
                                text: el.textContent?.trim() ? `:has-text("${el.textContent.trim().substring(0, 30)}")` : null,
                            };

                            return Object.values(sel).filter(Boolean);
                        }
                    } catch (e) {
                        return [];
                    }
                    return [];
                }
            """,
                primary_locator,
            )

            for sel in page_candidates or []:
                if sel and sel not in [c["selector"] for c in candidates]:
                    candidates.append({"selector": sel, "element": el_metadata})

        except Exception:
            # Best-effort — if JS evaluation fails, proceed with empty candidates
            pass

        return candidates

    @staticmethod
    def try_fallback(
        loc: Any,
        primary_locator: str,
        label: str,
        el_metadata: dict[str, Any],
        primary_error: Exception,
        page: Any,
        record_step: Any,
        max_fallbacks: int = 2,
    ) -> None:
        """Try higher-scoring locator alternatives when the primary locator fails.

        Builds candidate selectors from the current page DOM using Playwright's
        built-in locator strategies, scores them with ``LocatorScorer``, and tries
        the top ``max_fallbacks`` alternatives.

        Args:
            loc: The Playwright locator for the primary selector.
            primary_locator: The original selector that failed.
            label: Human-readable step label.
            el_metadata: Element metadata captured before the failed attempt.
            primary_error: The exception that triggered fallback.
            page: Playwright Page instance for JS evaluation.
            record_step: Callable to record the step result.
                Signature: ``record_step(type, label, locator, fallback_used, fallback_chain, take_screenshot, error)``
            max_fallbacks: Maximum number of fallback candidates to try.

        Raises:
            Exception: The primary error is re-raised after all fallbacks fail.
        """
        # Build candidate list from the current page DOM
        candidates = LocatorFallback.build_candidates(primary_locator, el_metadata, page)

        # Get scored fallback candidates (higher-scoring than the primary)
        fallbacks = LocatorScorer.get_fallback_candidates(primary_locator, candidates, max_fallbacks=max_fallbacks)

        if not fallbacks:
            # No higher-scoring alternatives — nothing to try
            raise primary_error

        fallback_chain: list[dict[str, Any]] = []

        # Record the primary failure in the chain
        primary_scored = LocatorScorer.score_locator(primary_locator)
        fallback_chain.append(
            {
                "locator": primary_locator,
                "type": primary_scored["type"],
                "score": primary_scored["score"],
                "confidence": primary_scored["confidence"],
                "result": "failed",
                "error": str(primary_error)[:200],
            }
        )

        # Try each fallback candidate in score-descending order
        for fallback in fallbacks:
            fallback_selector = fallback["selector"]
            try:
                fallback_loc = page.locator(fallback_selector).first
                fallback_loc.click(timeout=5000)
                # Success — record with fallback chain
                record_step(
                    "click",
                    label,
                    locator=primary_locator,
                    fallback_used=True,
                    fallback_chain=fallback_chain
                    + [
                        {
                            "locator": fallback_selector,
                            "type": fallback["type"],
                            "score": fallback["score"],
                            "confidence": fallback["confidence"],
                            "result": "success",
                        }
                    ],
                )
                return
            except Exception as fallback_error:
                fallback_chain.append(
                    {
                        "locator": fallback_selector,
                        "type": fallback["type"],
                        "score": fallback["score"],
                        "confidence": fallback["confidence"],
                        "result": "failed",
                        "error": str(fallback_error)[:200],
                    }
                )

        # All fallbacks failed — record the full chain and re-raise
        record_step(
            "click",
            label,
            locator=primary_locator,
            take_screenshot=True,
            error=str(primary_error),
            fallback_used=True,
            fallback_chain=fallback_chain,
        )
        raise primary_error
