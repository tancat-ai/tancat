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
