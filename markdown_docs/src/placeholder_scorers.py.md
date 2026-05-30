# `src/placeholder_scorers.py`

## High-Level Purpose
Composite scoring engine for placeholder resolution — provides individual testable scoring functions that evaluate candidate elements against placeholder descriptions.

## Module Metadata
- **Lines:** ~380
- **Imports:** `re`, `math`, `dataclasses`, `typing`, `src.semantic_matcher`

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

## Key Design Decisions
- Composable scoring functions — each testable in isolation
- Weighted sum model with configurable weights
- Locator type hierarchy mirrors strict-mode reliability

## Dependencies
- `src.semantic_matcher`