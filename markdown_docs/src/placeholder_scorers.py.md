# `src/placeholder_scorers.py`

## High-Level Purpose
Composite scoring engine for placeholder resolution — provides individual testable scoring functions that evaluate candidate elements against placeholder descriptions.

## Module Metadata
- **Lines:** ~520
- **Imports:** `re`, `math`, `dataclasses`, `typing`, `src.semantic_matcher`
- **RAG updates:** 2026-07-21 — `GOLDEN_PATTERN_BONUS` constant, `_golden_pattern_bonus()` method, optional `golden_patterns` parameter on `compute_element_score()`

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