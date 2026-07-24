"""Multi-pass element matching engine for placeholder resolution.

Extracted from ``placeholder_orchestrator.py``. Implements a 4-pass
resolution pipeline (Pass 0–3) for matching placeholder descriptions
to scraped DOM elements, plus LLM-based semantic ASSERT resolution (B-020).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.intent_matcher import SemanticFillStrategy
from src.locator_builder import build_robust_locator
from src.placeholder_resolver import PlaceholderResolver
from src.role_mapper import (
    ROLE_FALLBACK_GAP,
    is_display_role,
    normalise_element_text,
)
from src.semantic_candidate_ranker import AsyncGeneratorLike, SemanticCandidateRanker
from src.semantic_matcher import SemanticMatcher

logger = logging.getLogger(__name__)

# B-016: Text-bearing roles and tags for ASSERT matching.
TEXT_BEARING_ROLES = {
    "heading",
    "paragraph",
    "text",
    "status",
    "alert",
    "region",
    "article",
    "listitem",
    "cell",
    "columnheader",
    "rowheader",
}

TEXT_BEARING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "label", "li", "td", "th"}

# B-020: Minimum score for text fallback when no LLM selection is available.
MIN_SCORE_FOR_TEXT_FALLBACK = 5


class ElementMatcher:
    """Multi-pass element matching engine for placeholder resolution.

    Implements a staged resolution pipeline:
    - Pass 0: Exact text match for ASSERT:"exact text here"
    - Pass 1: Fast text match (CLICK/FILL) or text-bearing ASSERT match
    - Pass 2: Structural attribute match (id, data-test, aria)
    - Pass 3: Scoring + LLM semantic ranking (B-020 for ASSERT)
    """

    def __init__(self, resolver: PlaceholderResolver, generator: AsyncGeneratorLike | None = None) -> None:
        """Initialize the element matcher.

        Args:
            resolver: PlaceholderResolver instance for text matching and ranking.
            generator: B-020 LLM generator for semantic candidate ranking.
        """
        self._resolver = resolver
        self._semantic_ranker = SemanticCandidateRanker(generator)

    # ── Pass 0: Exact text match ────────────────────────────────

    def pass0_exact_text_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 0 — exact text match for ASSERT descriptions wrapped in quotes.

        B-020: When the skeleton emits ASSERT:"exact text here", strip the quotes
        and do literal string equality against element text. This bypasses all
        scoring and LLM calls for the simple "verify text is X" case.
        """
        if action != "ASSERT":
            return None

        text = description
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            text = text[1:-1]
        if not text:
            return None

        norm_target = text.strip().lower()
        if len(norm_target) < 2:
            return None

        for elements in pages_data.values():
            for element in elements:
                norm_text = normalise_element_text(element)
                if norm_text == norm_target:
                    return element

        return None

    # ── Pass 1: Text match ─────────────────────────────────────

    def pass1_text_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 1 — fast text match before scoring.

        Returns the first element whose normalised text is
        contained in the normalised description.
        Only fires for CLICK and FILL — ASSERT tokens for
        page state will not match element text and should
        fall through to the scoring path.

        Minimum element text length of 3 characters prevents
        single-character matches ('a', 'x') producing false wins.

        REGRESSION FIX (2026-05-17): When the description contains action verbs
        (add, remove, place, buy, etc.), require the element text to contain at
        least one of those action words.

        R-001 FIX: Key phrase extraction for verbose descriptions.
        """
        if action not in {"CLICK", "FILL"}:
            return None

        norm_description = description.lower()

        desc_words = set(norm_description.split())
        has_action_verb = bool(desc_words & PlaceholderResolver.ACTION_VERBS)

        # R-001: Extract key phrases from verbose descriptions.
        key_phrases: list[str] = []
        quoted_phrases = re.findall(r'["\']([^"\']+)["\']', norm_description)
        key_phrases.extend(quoted_phrases)

        context_boundary = {
            "link",
            "button",
            "in",
            "on",
            "at",
            "next to",
            "beside",
            "of",
            "the",
            "section",
            "list",
            "menu",
            "header",
            "page",
            "sidebar",
            "navigation",
            "header navigation",
            "left sidebar",
        }
        words = norm_description.split()
        noun_phrase_words: list[str] = []
        for w in words:
            if w in context_boundary:
                break
            if len(w) > 1 and w not in PlaceholderResolver.ACTION_CONTEXT_WORDS:
                noun_phrase_words.append(w)
        if len(noun_phrase_words) >= 1:
            key_phrases.append(" ".join(noun_phrase_words))

        for elements in pages_data.values():
            for element in elements:
                norm_text = normalise_element_text(element)
                if len(norm_text) < 3:
                    continue

                matched = False

                if norm_text in norm_description:
                    # B-024f: Single-word text requires word-boundary
                    # match. "year" ⊆ "(years)" is a substring
                    # coincidence, not a real match.
                    if " " not in norm_text and len(norm_text) >= 4:
                        desc_words_check = set(norm_description.replace("(", " ").replace(")", " ").split())
                        if norm_text in desc_words_check:
                            matched = True
                    else:
                        matched = True

                if not matched and key_phrases:
                    for phrase in key_phrases:
                        phrase_words = len(phrase.split())
                        text_word_count = len(norm_text.split())
                        if phrase_words > 0:
                            # B-024: Relax word-ratio guard when phrase is
                            # a literal substring of element text (e.g.
                            # "scheme" in "Select scheme..."). The ratio
                            # guard prevents 1-word matches on long texts
                            # but shouldn't block genuine substrings.
                            phrase_in_text = phrase in norm_text or norm_text in phrase
                            if phrase_in_text and phrase_words == 2:
                                # Two-word phrase found as substring — trust it
                                matched = True
                                break
                            if phrase_in_text and phrase_words == 1:
                                # Single-word key phrase: require exact text match,
                                # not substring inside a longer phrase. "cart" should
                                # match "Cart" exactly, not "Add to cart".
                                if norm_text == phrase or text_word_count == 1:
                                    matched = True
                            if not matched:
                                word_ratio = max(text_word_count, phrase_words) / min(text_word_count, phrase_words)
                                if word_ratio < 3 and (norm_text == phrase or phrase_in_text):
                                    matched = True
                                    break

                # B-024e: Targeted word match against element id/name
                # when substring matching fails for FILL actions.
                # If a description word prefixes the element's id or
                # name, that's a strong signal (e.g. "overnight" →
                # id="overnightLocation", "usage" → name="usageType").
                # Only for FILL — CLICK targets need structural matching.
                if not matched and action == "FILL" and key_phrases:
                    elem_id = str(element.get("id", "")).lower()
                    elem_name = str(element.get("name", "")).lower()
                    for phrase in key_phrases:
                        for word in phrase.split():
                            if len(word) >= 4:
                                if (elem_id and elem_id.startswith(word)) or (elem_name and elem_name.startswith(word)):
                                    matched = True
                                    break
                        if matched:
                            break

                if matched:
                    # B-025: For CLICK actions, skip heading elements
                    # (h1-h6). Headings are display elements inside click
                    # containers — they should not be selected as click
                    # targets. Pass 3 scoring handles the container bonus.
                    _heading_roles = {"h1", "h2", "h3", "h4", "h5", "h6", "heading"}
                    if action == "CLICK":
                        role = str(element.get("role", "")).strip().lower()
                        computed = str(element.get("computed_role", "")).strip().lower()
                        if role in _heading_roles or computed in _heading_roles:
                            continue  # Skip this heading, try next element
                    if has_action_verb:
                        text_words = set(norm_text.split())
                        action_words_in_desc = desc_words & PlaceholderResolver.ACTION_VERBS
                        if not (text_words & action_words_in_desc):
                            continue
                    return element

        return None

    def pass1_assert_text_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 1 (ASSERT) — match text-bearing elements whose label appears in the description.

        Requires the element text to contain at least 2 of the description's content words
        to avoid false positives like "Summary" matching "cart summary" when "Cart Summary"
        exists on a different page.

        R-001 FIX: Key phrase extraction for verbose ASSERT descriptions.
        """
        if action != "ASSERT":
            return None

        norm_description = description.lower()
        desc_words = set(norm_description.split())

        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "and",
            "or",
            "but",
            "not",
            "in",
            "on",
            "at",
            "to",
            "for",
            "with",
            "by",
            "from",
            "of",
            "as",
            "into",
            "through",
            "page",
            "element",
            "visible",
            "displayed",
            "shown",
        }
        desc_content_words = desc_words - stop_words

        requires_multi_word = len(desc_content_words) >= 2

        # R-001: Extract key phrases from verbose descriptions
        key_phrases: list[str] = []
        quoted_phrases = re.findall(r'["\']([^"\']+)["\']', norm_description)
        key_phrases.extend(quoted_phrases)

        context_boundary = {
            "section",
            "containing",
            "with",
            "like",
            "including",
            "displaying",
            "showing",
            "that",
            "which",
            "are",
            "is",
            "be",
            "the",
            "a",
            "an",
        }
        words = norm_description.split()
        phrase_parts: list[str] = []
        current_phrase: list[str] = []
        for w in words:
            if w in context_boundary and len(current_phrase) > 0:
                if len(current_phrase) >= 1:
                    phrase_parts.append(" ".join(current_phrase))
                current_phrase = []
            elif len(w) > 1 and w not in stop_words:
                current_phrase.append(w)
        if current_phrase:
            phrase_parts.append(" ".join(current_phrase))
        key_phrases.extend(phrase_parts)

        for elements in pages_data.values():
            for element in elements:
                effective_role = str(element.get("computed_role") or element.get("role", "")).strip().lower()
                tag = str(element.get("tag", "")).strip().lower()
                if effective_role not in TEXT_BEARING_ROLES and tag not in TEXT_BEARING_TAGS:
                    continue
                norm_text = normalise_element_text(element)
                if len(norm_text) < 3:
                    continue

                matched = False

                if norm_text in norm_description:
                    # B-024f: Single-word text requires word-boundary
                    # match. "year" ⊆ "(years)" is a substring
                    # coincidence, not a real match.
                    if " " not in norm_text and len(norm_text) >= 4:
                        desc_words_check = set(norm_description.replace("(", " ").replace(")", " ").split())
                        if norm_text in desc_words_check:
                            matched = True
                    else:
                        matched = True

                if not matched and key_phrases:
                    for phrase in key_phrases:
                        phrase_words = len(phrase.split())
                        text_word_count = len(norm_text.split())
                        if phrase_words > 0:
                            # B-024: Relax word-ratio guard when phrase is
                            # a literal substring of element text (e.g.
                            # "scheme" in "Select scheme..."). The ratio
                            # guard prevents 1-word matches on long texts
                            # but shouldn't block genuine substrings.
                            phrase_in_text = phrase in norm_text or norm_text in phrase
                            if phrase_in_text and phrase_words == 2:
                                # Two-word phrase found as substring — trust it
                                matched = True
                                break
                            if phrase_in_text and phrase_words == 1:
                                # Single-word key phrase: require exact text match,
                                # not substring inside a longer phrase.
                                if norm_text == phrase or text_word_count == 1:
                                    matched = True
                            if not matched:
                                word_ratio = max(text_word_count, phrase_words) / min(text_word_count, phrase_words)
                                if word_ratio < 3 and (norm_text == phrase or phrase_in_text):
                                    matched = True
                                    break

                if matched:
                    if requires_multi_word:
                        elem_words = set(norm_text.lower().replace("_", " ").split())
                        overlap = elem_words & desc_content_words
                        if len(overlap) < 2:
                            continue
                    return element

        return None

    # ── Pass 2: Structural match ────────────────────────────────

    def pass2_structural_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 2 — match stable attributes (id, data-test, aria) to description keywords."""
        if action not in {"CLICK", "FILL", "ASSERT"}:
            return None

        desc_words = SemanticMatcher.get_words(description, expand_aliases=False)
        if not desc_words:
            return None

        structural_fields = ("id", "data_test", "aria_label", "accessible_name", "name")

        for elements in pages_data.values():
            for element in elements:
                if action == "ASSERT" and not is_display_role(element):
                    continue
                for field in structural_fields:
                    raw = str(element.get(field, "")).strip()
                    if len(raw) < 2:
                        continue
                    field_words = SemanticMatcher.get_words(raw, expand_aliases=False)
                    overlap = desc_words & field_words
                    if len(overlap) >= 2:
                        return element
                    normalized_field = raw.lower().replace("_", " ").replace("-", " ")
                    if normalized_field in description.lower():
                        return element
                    desc_normalized = description.lower().replace("_", " ").replace("-", " ")
                    if desc_normalized in normalized_field:
                        return element
                    if action == "FILL" and SemanticFillStrategy().match(action, description, element):
                        return element

        return None

    # ── Pass 3: Scoring + LLM ──────────────────────────────────

    async def find_best_element_for_current_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
        excluded_selectors: set[str] | None = None,
        resolved_steps: list[str] | None = None,
        golden_patterns: list | None = None,
    ) -> dict[str, str] | None:
        """Return the best element match across the supplied page mapping.

        IMPORTANT: Collects candidates from ALL pages first, then selects the global
        best match. This prevents returning a low-quality match from an early page
        when a much better match exists on a later page.

        Args:
            excluded_selectors: Selectors to exclude from consideration (B-014).
            resolved_steps: B-020 list of compressed prior step descriptions.
            golden_patterns: Optional RAG RetrievedPattern list for scoring bonus.
        """
        # Pass 0 — exact text match for ASSERT:"exact text"
        pass0_result = self.pass0_exact_text_match(action, description, pages_data)
        if pass0_result is not None:
            if not excluded_selectors or not _is_excluded(pass0_result, excluded_selectors):
                _log_resolve_pass(0, "exact text match", description, pass0_result)
                pass0_result["assertion_type"] = "toHaveText"
                pass0_result["expected_value"] = description.strip("'\"")
                return pass0_result
            logger.debug("[RESOLVE] '%s' | pass=0 exact text EXCLUDED (step context)", description)

        # Pass 1 — fast text match (CLICK/FILL)
        pass1_result = self.pass1_text_match(action, description, pages_data)
        if pass1_result is not None:
            if not excluded_selectors or not _is_excluded(pass1_result, excluded_selectors):
                _log_resolve_pass(1, "text match", description, pass1_result)
                return pass1_result
            logger.debug("[RESOLVE] '%s' | pass=1 text match EXCLUDED (step context)", description)

        # Pass 1 — ASSERT text-bearing elements
        pass1_assert = self.pass1_assert_text_match(action, description, pages_data)
        if pass1_assert is not None:
            if not excluded_selectors or not _is_excluded(pass1_assert, excluded_selectors):
                _log_resolve_pass(1, "assert text match", description, pass1_assert)
                return pass1_assert
            logger.debug("[RESOLVE] '%s' | pass=1 assert text match EXCLUDED (step context)", description)

        # Pass 2 — structural attribute match
        pass2_result = self.pass2_structural_match(action, description, pages_data)
        if pass2_result is not None:
            if not excluded_selectors or not _is_excluded(pass2_result, excluded_selectors):
                _log_resolve_pass(2, "structural match", description, pass2_result)
                return pass2_result
            logger.debug("[RESOLVE] '%s' | pass=2 structural match EXCLUDED (step context)", description)

        # Pass 3 — scoring shortlist + semantic ranker
        logger.debug("[RESOLVE] '%s' | pass=3 (scoring)", description)

        all_ranked: list[tuple[float, dict[str, str]]] = []
        for url, elements in pages_data.items():
            ranked_candidates = self._resolver.rank_candidates(
                action,
                description,
                elements,
                golden_patterns=golden_patterns,
            )
            all_ranked.extend(ranked_candidates)
            logger.debug(
                "  PAGE %s: %d candidates, top_score=%s",
                url,
                len(ranked_candidates),
                ranked_candidates[0][0] if ranked_candidates else "N/A",
            )

        if excluded_selectors:
            before = len(all_ranked)
            all_ranked = [(score, elem) for score, elem in all_ranked if not _is_excluded(elem, excluded_selectors)]
            if len(all_ranked) < before:
                logger.debug(
                    "[RESOLVE] '%s' | excluded %d candidate(s) (step context)",
                    description,
                    before - len(all_ranked),
                )

        all_ranked.sort(key=lambda x: x[0], reverse=True)

        # B-016: soft role filtering for ASSERT
        if action == "ASSERT" and all_ranked:
            display_ranked = [(s, e) for s, e in all_ranked if is_display_role(e)]
            global_top_score_all = all_ranked[0][0]

            if display_ranked:
                best_display_score = display_ranked[0][0]
                gap = global_top_score_all - best_display_score

                if gap <= ROLE_FALLBACK_GAP:
                    logger.debug(
                        "[RESOLVE] '%s' | B-016 role filter: using display element "
                        "(score=%s, gap=%d from global top %s)",
                        description,
                        best_display_score,
                        gap,
                        global_top_score_all,
                    )
                    all_ranked = display_ranked
                else:
                    logger.warning(
                        "[RESOLVE] '%s' | B-016 low-confidence fallback: "
                        "best display score=%s is %d below global top=%s — using non-display element",
                        description,
                        best_display_score,
                        gap,
                        global_top_score_all,
                    )
            else:
                logger.debug(
                    "[RESOLVE] '%s' | B-016: no display-role candidates, scoring all %d elements",
                    description,
                    len(all_ranked),
                )

        if not all_ranked:
            return None

        global_top_score = all_ranked[0][0]
        logger.debug(
            "GLOBAL top_score=%s for '%s' (selector=%s)",
            global_top_score,
            description,
            all_ranked[0][1].get("selector", ""),
        )

        # B-020: ASSERT gets a semantic LLM pass with step context.
        if action == "ASSERT":
            return await self._resolve_assert_semantically(
                all_ranked=all_ranked,
                description=description,
                current_url=current_url,
                resolved_steps=resolved_steps,
            )

        # Non-ASSERT: threshold-based shortlist from global ranking.
        threshold = max(1, global_top_score - 2)
        shortlisted = [element for score, element in all_ranked if score >= threshold][:4]

        matched_element = None
        if len(shortlisted) > 1 and action in {"CLICK", "FILL"}:
            matched_element = await self._semantic_ranker.choose_best_candidate(
                action=action,
                description=description,
                current_url=current_url,
                candidates=shortlisted,
            )

        validated = _validate_text_match(matched_element, description, self._resolver) if matched_element else None
        if validated is not None:
            return validated

        for candidate in shortlisted:
            if _validate_text_match(candidate, description, self._resolver):
                return candidate

        if matched_element is not None:
            element_text = str(matched_element.get("text", "")).strip()
            logger.warning(
                "LLM-selected element '%s' fails text validation for '%s' — "
                "using anyway (diagnostic review recommended).",
                element_text,
                description,
            )
            return matched_element

        if shortlisted and global_top_score >= MIN_SCORE_FOR_TEXT_FALLBACK:
            top_candidate = shortlisted[0]
            validated = _validate_text_match(top_candidate, description, self._resolver)
            if validated is not None:
                return validated
            # Text validation failed: check if there's at least some word overlap
            # before returning a fallback match. Zero overlap means the score came
            # entirely from structural bonuses (e.g. button role for CLICK) with
            # no semantic relationship to the description.
            desc_words_check = SemanticMatcher.get_words(description)
            candidate_haystack = str(
                top_candidate.get("text", "")
                + " "
                + top_candidate.get("aria_label", "")
                + " "
                + top_candidate.get("id", "")
                + " "
                + top_candidate.get("name", "")
            ).lower()
            candidate_words = SemanticMatcher.get_words(candidate_haystack, expand_aliases=False)
            if not desc_words_check.intersection(candidate_words):
                logger.debug(
                    "Top-ranked element '%s' has zero word overlap with '%s' — returning None",
                    str(top_candidate.get("text", "")).strip(),
                    description,
                )
                return None
            logger.info(
                "Top-ranked element '%s' fails text validation for '%s' — "
                "using anyway (text validation is advisory for non-LLM path).",
                str(top_candidate.get("text", "")).strip(),
                description,
            )
            return top_candidate
        return None

    async def _resolve_assert_semantically(
        self,
        *,
        all_ranked: list[tuple[float, dict[str, str]]],
        description: str,
        current_url: str | None,
        resolved_steps: list[str] | None = None,
    ) -> dict[str, str] | None:
        """B-020: Resolve ASSERT using LLM semantic ranking with step context.

        Builds a curated candidate pool of display elements + top scorers,
        then delegates to the LLM which selects both the best element and
        the appropriate assertion type.
        """
        seen_selectors: set[str] = set()
        candidate_pool: list[dict[str, Any]] = []

        for _score, element in all_ranked[:3]:
            sel = element.get("selector", "")
            if sel and sel not in seen_selectors:
                seen_selectors.add(sel)
                candidate_pool.append(element)

        for _score, element in all_ranked:
            if len(candidate_pool) >= 6:
                break
            if is_display_role(element):
                sel = element.get("selector", "")
                if sel and sel not in seen_selectors:
                    seen_selectors.add(sel)
                    candidate_pool.append(element)

        logger.debug("[B-020] ASSERT semantic pass for '%s': %d candidates in pool", description, len(candidate_pool))

        if not candidate_pool:
            return None

        if len(candidate_pool) == 1:
            result = dict(candidate_pool[0])
            result["assertion_type"] = "toBeVisible"
            return result

        matched_element = await self._semantic_ranker.choose_best_candidate(
            action="ASSERT",
            description=description,
            current_url=current_url,
            candidates=candidate_pool,
            previous_steps=resolved_steps,
        )

        if matched_element is not None:
            assertion_type = matched_element.get("assertion_type", "toBeVisible")
            logger.info(
                "[B-020] ASSERT '%s' -> selector=%s, assertion_type=%s",
                description,
                matched_element.get("selector", ""),
                assertion_type,
            )
            return matched_element

        logger.warning(
            "[B-020] ASSERT '%s': LLM semantic pass failed, falling back to top scorer",
            description,
        )
        fallback = dict(all_ranked[0][1])
        fallback["assertion_type"] = "toBeVisible"
        return fallback


# ── Module-level helpers ─────────────────────────────────────


def _is_excluded(element: dict[str, str], excluded_selectors: set[str]) -> bool:
    """Check if an element should be excluded from consideration."""
    raw = str(element.get("selector", "")).strip()
    if raw in excluded_selectors:
        return True
    robust = build_robust_locator(element)
    if robust and robust in excluded_selectors:
        return True
    return False


def _validate_text_match(
    element: dict[str, str] | None,
    description: str,
    resolver: PlaceholderResolver,
) -> dict[str, str] | None:
    """Validate that the element's visible text plausibly matches the description.

    Returns the element if validation passes, None otherwise.
    """
    if element is None:
        return None
    element_text = str(element.get("text", "")).strip()
    if not element_text:
        return element
    if resolver.text_matches_description(element_text, description):
        return element
    logger.debug(
        "Text validation failed: element '%s' does not match description '%s'",
        element_text,
        description,
    )
    return None


def _log_resolve_pass(
    pass_number: int,
    pass_name: str,
    description: str,
    element: dict[str, str] | None,
) -> None:
    if element is None:
        return
    logger.info(
        "[RESOLVE] '%s' | pass=%d (%s) | selector=%s",
        description,
        pass_number,
        pass_name,
        element.get("selector", ""),
    )


def select_page_loaded_candidate(
    candidates: list[dict[str, str]],
    description: str = "",
) -> dict[str, str] | None:
    """Pick a stable visible page element for generic "page loaded" assertions.

    Only returns a candidate if the description contains specific keywords that
    we can match against element metadata. For generic descriptions, returns None
    so the placeholder remains unresolved and the test skips with a clear message.
    """
    lowered = description.lower()
    if "cart badge" in lowered or "badge updated" in lowered:
        for candidate in candidates:
            candidate_text = " ".join(
                str(candidate.get(field, "")).lower()
                for field in ("selector", "text", "classes", "data_test", "aria_label", "accessible_name")
            )
            if "cart" in candidate_text and ("badge" in candidate_text or str(candidate.get("text", "")).strip()):
                return candidate

    return None


__all__ = [
    "ElementMatcher",
    "select_page_loaded_candidate",
]
