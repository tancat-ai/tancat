# `src/placeholder_scorers.py`

## High-Level Purpose
Composite scoring engine for placeholder resolution — provides individual testable scoring functions that evaluate candidate elements against placeholder descriptions.

## Module Metadata
- **Lines:** ~570
- **Imports:** `re`, `math`, `dataclasses`, `typing`, `src.semantic_matcher`
- **RAG updates:** 2026-07-21 — `GOLDEN_PATTERN_BONUS` constant, `_golden_pattern_bonus()` method, optional `golden_patterns` parameter on `compute_element_score()`
- **B-025 updates:** 2026-07-23 — Heading penalty (-20) in `_click_role_bonus()` for CLICK on elements with heading role and no ID. Container bonus (+10) for generic/group/region elements with an ID.

## Classes

### `ScoreResult` (dataclass)
Single scoring result: selector, score, breakdown dict, matched_attributes.

### `ScoreBreakdown` (dataclass)
Individual score components: attribute_score, text_score, specificity_bonus, etc.

## Functions

### `aggregate_score(candidates: list[Element], description: str) -> list[ScoreResult]`
Main entry — scores all candidates, returns sorted list.

### `score_attribute_match(element: Element, description: str) -> float`
Scores based on attribute overlap (id, name, class, data-*).

### `score_text_match(element: Element, description: str) -> float`
Semantic text-content matching using token overlap.

### `score_specificity(selector: str) -> float`
Locator specificity bonus: data-testid > id > name > css-class > xpath.

### `score_proximity(element: Element, context: str) -> float`
Proximity bonus for elements near related context elements.

## RAG Integration (2026-07-21)

### `GOLDEN_PATTERN_BONUS` (class constant, `int = 20`)
Module-level constant matching `_vision_enriched_bonus` (+20). Strong enough to break ties between similarly scored candidates; won't override structural/id matches (+80) or visibility penalties (-40).

### `_golden_pattern_bonus(element, golden_patterns) -> int`
Static method. Evaluates whether an element's selector matches any retrieved golden pattern:
- **Direct selector match:** `+GOLDEN_PATTERN_BONUS × pattern.confidence`
- **Tolerance/substring match:** `+GOLDEN_PATTERN_BONUS × 0.5 × pattern.confidence`
- **No match:** `0`

### `compute_element_score()` — `golden_patterns` parameter
Optional `list[RetrievedPattern]` kwarg. When non-empty, `_golden_pattern_bonus()` is called and the result added to the element's total score.

## Key Design Decisions
- Composable scoring functions — each testable in isolation
- Weighted sum model with configurable weights
- Locator type hierarchy mirrors strict-mode reliability
- Golden pattern bonus is advisory — zero behaviour change when patterns list is empty/None

## Dependencies
- `src.semantic_matcher`
---

## AI-035 / B-036 Update (2026-08-03)

### Same-site learned-pattern bonus
- New constant `SAME_SITE_LEARNED_BONUS: int = 5` (next to `GOLDEN_PATTERN_BONUS = 20`).
- New static `_learned_pattern_bonus(element, patterns, site_hash) -> int`:
  +5 for a **same-site** learned pattern match (direct; half for substring,
  scaled by confidence), **0** for cross-site learned or golden sources.
- `compute_element_score(..., golden_patterns=None, site_hash=None)` gained a
  `site_hash` kwarg; the learned bonus is added alongside the golden bonus.
  Without `site_hash` (or with none set), behavior is unchanged — zero bonus.

### Rationale
Learned patterns are only trusted on the site they were verified on. A
saucedemo-learned `username → #user-name` must not win ties on a foreign site —
the +5/+0 split is the main poisoning guard.


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `PlaceholderScorer` (class)

Stateless scoring utilities for placeholder candidate ranking.

## How It Works (Internals)

Private `_`-helpers - the module's real logic (33 items). Grouped under the public function that calls them.

### `PlaceholderScorer.compute_element_score(action: str, description: str, element: dict[str, Any], selector: str, match_threshold: float, golden_patterns: list | None = None, site_hash: str | None = None) -> int | None` - method of `PlaceholderScorer`

- `_build_haystack(element: dict[str, Any]) -> str` (method of `PlaceholderScorer`): Build the haystack string for an element. Includes text attributes, element id, and CDP-accessible name. Splits camelCase tokens so quoteRef matches quote reference.
- `_kind_bonus(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): B-092: lift a kind-matching candidate above the match threshold. An image criterion ("the hero product screenshot loaded") is scoped to <img> elements, but their alt text rarely overlaps the criterion's words - wi...
- `_container_aggregate_penalty(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): AI-064: penalize a generic container that matched only via merged text. A main/body/div/section/nav/form container's haystack is the concatenated text of every descendant, so it matches ANY des...
- `_is_fillable(element: dict[str, Any]) -> bool` (method of `PlaceholderScorer`): Check if an element is a fillable input. B-028: role set aligned with IntentMatcher._is_fillable so journey discovery accepts the same elements the resolver does (e.g. role="number" quantity steppers).
- `_haystack_score(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Compute score for fast-path haystack matches.
- `_structural_bonus(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Structural match bonus when data-test or id contains description keywords.
- `_href_bonus(action: str, description: str, desc_words: set[str], element: dict[str, Any], element_words: set[str]) -> int` (method of `PlaceholderScorer`): Href bonus; returns int.
- `_product_id_bonus(action: str, description: str, desc_words: set[str], element: dict[str, Any], element_words: set[str]) -> int` (method of `PlaceholderScorer`): Product id bonus; calls `get_words`, `intersection`, `issubset`; returns int.
- `_assert_cart_penalty(action: str, description: str, desc_words: set[str], element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Assert cart penalty; calls `intersection`; returns int.
- `_assert_empty_state_rejects(description: str, element: dict[str, Any]) -> bool` (method of `PlaceholderScorer`): True when an empty-state element cannot satisfy a content ASSERT. B-037: on the e-commerce mock, #empty_cart ("Cart is empty! Please add some products.") scored as the top ASSERT candidate for "product name and pr...
- `_assertion_candidate_bonus(action: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Assertion candidate bonus; returns int.
- `_role_bonus(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Role bonus; returns int.
- `_journey_discovered_bonus(element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Journey discovered bonus; returns int.
- `_click_role_bonus(action: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Click role bonus; calls `_is_fillable`; returns int.
- `_fill_bonus(action: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Fill bonus; calls `_is_fillable`; returns int.
- `_assert_visibility_penalty(action: str, element: dict[str, Any], description: str = '') -> int` (method of `PlaceholderScorer`): Assert visibility penalty; calls `is_image_criterion`, `is_image_element`; returns int.
- `_hidden_element_penalty(action: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Penalise hidden elements for interactive actions (non-ASSERT). In the real pipeline, pages are scraped per-URL so hidden sections aren't in the haystack. This penalty only applies to eval scenarios (single-page scrape...
- `_click_text_penalty(action: str, description: str, desc_words: set[str], element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Click text penalty; returns int.
- `_assert_single_class_penalty(action: str, selector: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Assert single class penalty; returns int.
- `_visual_enrichment_bonus(action: str, description: str, element: dict[str, Any], lowered: str, icon_classes: str, visual_desc: str, parent_text: str) -> int` (method of `PlaceholderScorer`): Visual enrichment bonus; calls `intersection`; returns int.
- `_vision_enriched_bonus(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Score boost for elements enriched by the vision LLM. Uses vision-derived fields (product_name, price, visual_label, enrichment_note) to match placeholder descriptions that reference specific products or visual charact...
- `_golden_pattern_bonus(element: dict[str, Any], golden_patterns: list, site_hash: str | None = None) -> int` (method of `PlaceholderScorer`): Apply a bonus when the element's selector matches a golden pattern. Full selector match -> +GOLDEN_PATTERN_BONUS (20). Substring/tolerance match -> scaled to 10. B-047 residual: once seeded with a site_hash, a golde...
- `_learned_net_evidence(element: dict[str, Any], patterns: list | None, site_hash: str | None, *, action: str, description: str) -> int` (method of `PlaceholderScorer`): Net learned-pattern evidence: positives MINUS negatives (AI-058). A (action, description, selector, site) pair resolves to ONE net signal (AI-063 step scoping): - positives only -> +bonus (unchanged behavior) - neg...
- `_assert_action_penalty(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Penalize interactive elements for ASSERT targeting message-like descriptions. ASSERT for "confirmation message" should not resolve to buttons or action-oriented links. This penalty ensures display elements are preferr...
- `_assert_message_bonus(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Reward display elements for ASSERT targeting message-like descriptions. Dialog/alert roles and content elements with confirmation-like text are ideal targets for ASSERT tokens seeking messages.
- `_text_content_bonus(description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Reward elements whose text content overlaps with the description.
- `_page_level_assert_bonus(action: str, description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Bonus for page-level semantic assertions (e.g., 'order summary displayed'). These assertions don't map to specific element text but describe the presence of content on a page. We reward content-bearing elements when t...

### Internal utilities

- `_kind_token_overlap(description: str, element: dict[str, Any]) -> int` (method of `PlaceholderScorer`): Token overlap between the criterion and the element's identity. For images the identity lives in alt (already in the haystack), so "Noir Art artwork" ranks the Neon-noir illustration image above the product sc...
- `_learned_pattern_bonus(element: dict[str, Any], learned_patterns: list | None, site_hash: str | None) -> int` (method of `PlaceholderScorer`): Apply a bonus for same-site learned patterns (AI-035/B-036 Phase 3). A learned pattern is only trusted for the site it was verified on: full selector match -> +SAME_SITE_LEARNED_BONUS (5) scaled by confidence; substrin...
- `_learned_amount_for(element: dict[str, Any], pattern: Any, *, negative: bool) -> int` (method of `PlaceholderScorer`): Contribution of ONE learned / learned_negative pattern to an element. Full selector match -> base x confidence; substring/tolerance -> half. Negative contributions scale by hit_count up to LEARNED_NEGATIVE_MAX_HIT...
- `_step_scope_matches(pattern: Any, *, action: str, description: str) -> bool` (method of `PlaceholderScorer`): AI-063: does a learned/negative pattern apply to the CURRENT step? A pattern is step-scoped by (action_type, description) - it only feeds the score of the step it was recorded on. Previously the matcher keyed on '...
- `_learned_negative_penalty(element: dict[str, Any], patterns: list | None, site_hash: str | None, *, action: str, description: str) -> int` (method of `PlaceholderScorer`): Raw accumulated negative penalty for a same-site learned_negative. AI-058 mirror of _learned_pattern_bonus: full match 5 x conf, substring 2 x conf, scaled by hit_count up to LEARNED_NEGATIVE_MAX_HITS. R...
- `_is_message_like_assertion(description: str) -> bool` (method of `PlaceholderScorer`): Return True if the description signals a message-like assertion target.
