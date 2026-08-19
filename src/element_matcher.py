"""Multi-pass element matching engine for placeholder resolution.

Extracted from ``placeholder_orchestrator.py``. Implements a 4-pass
resolution pipeline (Pass 0–3) for matching placeholder descriptions
to scraped DOM elements, plus LLM-based semantic ASSERT resolution (B-020).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.intent_matcher import SemanticFillStrategy, _is_fillable
from src.locator_builder import build_robust_locator
from src.placeholder_resolver import PlaceholderResolver
from src.placeholder_scorers import PlaceholderScorer
from src.role_mapper import (
    ROLE_FALLBACK_GAP,
    is_display_role,
    normalise_element_text,
)
from src.semantic_candidate_ranker import (
    DEFAULT_RESOLUTION_TIMEOUT,
    AsyncGeneratorLike,
    SemanticCandidateRanker,
)
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

# B-045: Descriptions that name a clickable role must not fast-match a
# different role's element. Maps description role words → scraped roles.
# Only strong role words gate ("button", "link") — "icon" is used loosely
# ("cart icon" often refers to a link) and would exclude the real target.
# Submit-intent verbs ("pay", "submit", "place"...) also gate toward the
# form's submit control: a header nav link ("Pay Bills") must not win a
# "Pay Bill" description purely by substring overlap.
_NAMED_ROLE_MAP: dict[str, set[str]] = {
    "button": {"button", "submit"},
    "link": {"a", "link"},
    "submit": {"button", "submit"},
}

# Verbs that describe submitting a form (as opposed to navigating to a page).
_SUBMIT_INTENT_VERBS: tuple[str, ...] = ("submit", "place", "pay", "register", "send", "confirm")


def _named_role_in_description(norm_description: str) -> str | None:
    """Return the single named clickable role in a description, if any.

    ``"pay bill button"`` → ``"button"``; ``"cart link"`` → ``"link"``;
    ``"add to cart"`` → ``None`` (no role word). Only the FIRST role word
    found is used — descriptions rarely name more than one role, and a
    specific role gate beats a vague one.

    Submit-intent verbs also gate to the submit control — but only when the
    description is NOT a navigation phrase ("go to", "navigate", "open",
    "page", "link"), which target a nav link instead.
    """
    for role_word in ("button", "link"):
        if role_word in norm_description:
            return role_word
    is_navigation = any(
        term in norm_description for term in ("go to", "navigate", "open", "page", "link", "menu", "tab")
    )
    if not is_navigation:
        for verb in _SUBMIT_INTENT_VERBS:
            if verb in norm_description:
                return "submit"
    return None


# B-020: Minimum score for text fallback when no LLM selection is available.
MIN_SCORE_FOR_TEXT_FALLBACK = 5

#: Description-side dialog/dismiss/confirm intent. Generic ARIA dialog
#: vocabulary (the actions a dialog's buttons perform) — NOT a site-specific
#: element list. Word-boundary matched so "ok" doesn't fire on "token".
DIALOG_INTENT_TERMS: tuple[str, ...] = (
    "ok",
    "okay",
    "close",
    "dismiss",
    "confirm",
    "cancel",
    "accept",
    "done",
    "continue",
    "got it",
    "gotit",
)

#: Interactive ARIA roles a dialog-action may target.
DIALOG_SCOPED_ROLES: frozenset[str] = frozenset({"button", "link", "submit", "a", "menuitem", "checkbox", "radio"})


class ElementMatcher:
    """Multi-pass element matching engine for placeholder resolution.

    Implements a staged resolution pipeline:
    - Pass 0: Exact text match for ASSERT:"exact text here"
    - Pass 1: Fast text match (CLICK/FILL) or text-bearing ASSERT match
    - Pass 2: Structural attribute match (id, data-test, aria)
    - Pass 3: Scoring + LLM semantic ranking (B-020 for ASSERT)
    """

    def __init__(
        self,
        resolver: PlaceholderResolver,
        generator: AsyncGeneratorLike | None = None,
        *,
        resolution_timeout: float = DEFAULT_RESOLUTION_TIMEOUT,
    ) -> None:
        """Initialize the element matcher.

        Args:
            resolver: PlaceholderResolver instance for text matching and ranking.
            generator: B-020 LLM generator for semantic candidate ranking.
            resolution_timeout: Hard limit (seconds) for each resolution LLM call.
        """
        self._resolver = resolver
        self._semantic_ranker = SemanticCandidateRanker(generator, timeout=resolution_timeout)

        # Batching state for Pass 3 LLM calls
        self._pass3_batch: list[dict[str, Any]] = []
        self._pass3_results: dict[int, dict[str, Any] | None] = {}

    async def flush_pass3_batch(self) -> None:
        """Flush any pending Pass 3 batch, sending all in one LLM call.

        Call this after resolving a group of placeholders to batch their
        semantic ranking into a single LLM prompt.
        """
        if not self._pass3_batch:
            return

        batch = self._pass3_batch
        self._pass3_batch = []

        results = await self._semantic_ranker.choose_best_candidates_batch(items=batch)
        for i, result in enumerate(results):
            idx = batch[i].get("_batch_idx", i)
            self._pass3_results[idx] = result

    def _queue_pass3(
        self,
        batch_idx: int,
        action: str,
        description: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        """Queue a Pass 3 resolution for batch flushing."""
        self._pass3_batch.append(
            {
                "action": action,
                "description": description,
                "candidates": candidates,
                "_batch_idx": batch_idx,
            }
        )

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

    # ── Pass D: Dialog-action scoping (CLICK) ──────────────────

    def pass_dialog_action(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass D — dialog-action scoping for CLICK placeholders.

        When the description implies a dialog/dismiss/confirm action
        ("OK", "close popup", "dismiss", "Continue Shopping"), resolve it
        against the modal/dialog's OWN interactive elements instead of the
        whole page. Without this, a 2-char description like "OK" matches
        substrings inside unrelated elements ("csrfmiddlewareTOKen",
        "Kookie Kids") and short-circuits to the wrong target.

        The candidate scope is purely structural (ARIA): elements inside a
        modal (the scraper's ``in_modal`` flag) or carrying a
        dialog/alertdialog role, restricted to interactive roles. No
        site-specific lists.

        Returns None when the description is not dialog-intent or no
        in-modal candidate exists — the caller falls through to the normal
        resolution passes.
        """
        if action != "CLICK":
            return None

        lowered = description.replace("_", " ").lower()
        words = set(lowered.split())
        intent = any((" " in term and term in lowered) or term in words for term in DIALOG_INTENT_TERMS)
        if not intent:
            return None

        # Dismiss-intent descriptions ("OK", "close", "dismiss", "done",
        # "cancel", "got it") target the modal's DISMISSAL control — prefer
        # elements whose selector/classes carry close-modal semantics (the
        # button that closes the dialog without navigating away).
        dismiss_intent = any(
            term in words for term in ("ok", "okay", "close", "dismiss", "done", "cancel", "got", "gotit")
        )

        best_element: dict[str, str] | None = None
        best_score = -1
        for elements in pages_data.values():
            for element in elements:
                role = str(element.get("role", "")).lower()
                if role not in DIALOG_SCOPED_ROLES:
                    continue
                if not (element.get("in_modal") or role in {"dialog", "alertdialog"}):
                    continue
                selector = str(element.get("selector", "")).strip() or str(element.get("tag", ""))
                if not selector:
                    continue
                score = PlaceholderScorer.compute_element_score(
                    "CLICK", description, element, selector, match_threshold=0.0
                )
                if score is None:
                    continue
                if dismiss_intent:
                    classes = str(element.get("classes", "")).lower()
                    if any(
                        mark in f"{classes} {selector.lower()}"
                        for mark in ("close-modal", "modal-close", "btn-close", "dismiss")
                    ):
                        score += 10
                if score > best_score:
                    best_score = score
                    best_element = element

        if best_element is not None:
            logger.info(
                "[RESOLVE] '%s' | pass=D (dialog-action scoping) | selector=%s | score=%s",
                description,
                best_element.get("selector"),
                best_score,
            )
        return best_element

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

        # B-045: exact-text pre-sweep — when an element's normalized text is
        # EXACTLY the description, it wins over substring matches regardless
        # of DOM order. "Pay Bills" (nav link) must beat the "Pay Bill"
        # submit button for a "Pay Bills" click, and vice versa — exact
        # equality is the strongest signal of intent.
        for elements in pages_data.values():
            for element in elements:
                if element.get("synthetic_id"):
                    continue
                if action == "FILL" and not _is_fillable(element):
                    continue
                norm_text = normalise_element_text(element)
                if not norm_text or norm_text != norm_description:
                    continue
                _heading_roles = {"h1", "h2", "h3", "h4", "h5", "h6", "heading"}
                role = str(element.get("role", "")).strip().lower()
                computed = str(element.get("computed_role", "")).strip().lower()
                if action == "CLICK" and (role in _heading_roles or computed in _heading_roles):
                    continue
                # No role gate here: exact text equality is the strongest
                # intent signal and already disambiguates "Pay Bills" (nav)
                # from "Pay Bill" (submit button) without needing role hints.
                if has_action_verb:
                    text_words = set(norm_text.split())
                    action_words_in_desc = desc_words & PlaceholderResolver.ACTION_VERBS
                    if not (text_words & action_words_in_desc):
                        continue
                return element

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
                # AI-037: skip synthetic ARIA-only containers (Pass 2 of the
                # hybrid scraper) — they have no real DOM id and are not
                # interactive targets. Their snake_case ids/text (e.g.
                # "Vehicle Usage") otherwise win fast-text matching over the
                # real radio/button (which may have empty text).
                if element.get("synthetic_id"):
                    continue
                # FILL gate: containers whose accessible_name collides with a
                # field label (e.g. a div wrapping the username input reports
                # accessible_name="Username") must not win over the real input.
                # rank_candidates() already applies this gate — Pass 1 must too.
                if action == "FILL" and not _is_fillable(element):
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

                # B-024g: FILL fields often label with separator-heavy placeholders
                # (saucedemo "Zip/Postal Code"). If every description word appears
                # as a word in the element text (separators normalized), it's the
                # field: "zip code" → {zip, code} ⊆ {zip, postal, code}.
                if not matched and action == "FILL" and len(norm_description.split()) >= 2:
                    elem_words = set(norm_text.replace("/", " ").replace("-", " ").replace("_", " ").split())
                    desc_words_clean = set(
                        norm_description.replace("/", " ").replace("-", " ").replace("_", " ").split()
                    )
                    if desc_words_clean and desc_words_clean <= elem_words:
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
                    # B-045: When the description names a role ("button",
                    # "link", "icon"), Pass 1 must respect it — a header nav
                    # link ("Pay Bills") text-matches "pay bill button" and
                    # appears earlier in the DOM than the real submit button
                    # ("Pay Bill"), so DOM-order fast-matching picked the
                    # nav link and the click never navigated. Elements whose
                    # role disagrees with the named role are skipped here;
                    # if no role-named element matches, we fall through to
                    # scoring which applies its own role bonus.
                    if action == "CLICK":
                        desc_role = _named_role_in_description(norm_description)
                        if desc_role is not None:
                            el_role = role or computed
                            if el_role != desc_role:
                                continue
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
        # B-045: same role gate as Pass 1 — a description that names a role
        # ("pay bill button") must not structurally fast-match a different
        # role's element (header nav link) before scoring runs.
        named_role = _named_role_in_description(description.lower()) if action == "CLICK" else None

        for elements in pages_data.values():
            for element in elements:
                if action == "ASSERT" and not is_display_role(element):
                    continue
                # CLICK/FILL: hidden elements are not valid targets — parity
                # with rank_candidates. Without this, a short description like
                # "OK" can substring-match "csrfmiddlewareTOKen" via the
                # element's name attribute and win on the fast path.
                if action in {"CLICK", "FILL"} and (
                    str(element.get("role", "")).lower() == "hidden" or element.get("is_visible") is False
                ):
                    continue
                if named_role is not None:
                    el_role = (
                        str(element.get("role", "")).strip().lower()
                        or str(element.get("computed_role", "")).strip().lower()
                    )
                    if el_role not in _NAMED_ROLE_MAP[named_role]:
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
                    # 2-char substrings are noise ("ok" inside "token") —
                    # only trust >= 3-char substring containment.
                    if len(desc_normalized) >= 3 and desc_normalized in normalized_field:
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
        site_hash: str | None = None,
    ) -> dict[str, str] | None:
        """Return the best element match across the supplied page mapping.

        IMPORTANT: Collects candidates from ALL pages first, then selects the global
        best match. This prevents returning a low-quality match from an early page
        when a much better match exists on a later page.

        Args:
            excluded_selectors: Selectors to exclude from consideration (B-014).
            resolved_steps: B-020 list of compressed prior step descriptions.
            golden_patterns: Optional RAG RetrievedPattern list for scoring bonus.
            site_hash: Current site's one-way domain hash (AI-035 Phase 2) —
                enables the same-site learned-pattern bonus.
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

        # Pass D — dialog-action scoping (CLICK descriptions implying
        # dismiss/confirm resolve to the modal's own controls)
        pass_dialog_result = self.pass_dialog_action(action, description, pages_data)
        if pass_dialog_result is not None:
            if not excluded_selectors or not _is_excluded(pass_dialog_result, excluded_selectors):
                return pass_dialog_result
            logger.debug("[RESOLVE] '%s' | pass=D dialog EXCLUDED (step context)", description)

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
                site_hash=site_hash,
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

    async def find_best_elements_batch(
        self,
        requests: list[dict[str, Any]],
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
        excluded_selectors: set[str] | None = None,
    ) -> list[dict[str, str] | None]:
        """Batch-resolve multiple placeholders, batching Pass 3 LLM calls.

        Each request dict should have:
            - action: str (CLICK, FILL, ASSERT, etc.)
            - description: str

        Returns a list of resolved element dicts (or None) in the same order.
        """
        # Phase 1: Pass 0-2 for all requests (fast, no LLM)
        pass3_requests: list[tuple[int, str, str, list[Any]]] = []
        results: list[dict[str, str] | None] = [None] * len(requests)

        for i, req in enumerate(requests):
            action = req.get("action", "CLICK")
            description = req.get("description", "")

            # Pass 0 — exact text match
            pass0_result = self.pass0_exact_text_match(action, description, pages_data)
            if pass0_result is not None and (
                not excluded_selectors or not _is_excluded(pass0_result, excluded_selectors)
            ):
                pass0_result["assertion_type"] = "toHaveText"
                pass0_result["expected_value"] = description.strip("'\"")
                results[i] = pass0_result
                continue

            # Pass 1 — text match
            pass1_result = self.pass1_text_match(action, description, pages_data)
            if pass1_result is not None and (
                not excluded_selectors or not _is_excluded(pass1_result, excluded_selectors)
            ):
                results[i] = pass1_result
                continue

            # Pass 1 — ASSERT text
            pass1_assert = self.pass1_assert_text_match(action, description, pages_data)
            if pass1_assert is not None and (
                not excluded_selectors or not _is_excluded(pass1_assert, excluded_selectors)
            ):
                results[i] = pass1_assert
                continue

            # Pass 2 — structural match
            pass2_result = self.pass2_structural_match(action, description, pages_data)
            if pass2_result is not None and (
                not excluded_selectors or not _is_excluded(pass2_result, excluded_selectors)
            ):
                results[i] = pass2_result
                continue

            # Collect Pass 3 candidates
            all_ranked: list[tuple[float, dict[str, str]]] = []
            for _url, elements in pages_data.items():
                ranked = self._resolver.rank_candidates(action, description, elements)
                all_ranked.extend(ranked)

            if excluded_selectors:
                all_ranked = [(s, e) for s, e in all_ranked if not _is_excluded(e, excluded_selectors)]

            all_ranked.sort(key=lambda x: x[0], reverse=True)
            if not all_ranked:
                continue

            pass3_requests.append((i, action, description, all_ranked))  # type: ignore

        if not pass3_requests:
            return results

        # Phase 2: Batch Pass 3 LLM calls
        batch_items: list[dict[str, Any]] = []
        for i, action, description, ranked in pass3_requests:
            top_score = ranked[0][0]

            if action == "ASSERT":
                shortlisted = [e for _s, e in ranked[:8]]
            else:
                threshold = max(1, top_score - 2)
                shortlisted = [e for _s, e in ranked if _s >= threshold][:4]

            if len(shortlisted) <= 1:
                if shortlisted:
                    results[i] = shortlisted[0]
                continue

            batch_items.append(
                {
                    "action": action,
                    "description": description,
                    "candidates": shortlisted,
                    "_batch_idx": i,
                }
            )

        if batch_items:
            batch_results = await self._semantic_ranker.choose_best_candidates_batch(items=batch_items)
            for j, result in enumerate(batch_results):
                idx = batch_items[j].get("_batch_idx", j)
                if result is not None:
                    results[idx] = result

        return results

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
