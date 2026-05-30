# locator_scorer.py

## Purpose
Score Playwright selectors by reliability/fragility based on locator type to enable controlled fallbacks, coverage validation, and suite heatmaps.

## Location
`src/locator_scorer.py` (321 lines)

## Dependencies
- `re` (standard library)
- `typing.Any` (standard library)

## Public API

### `LocatorScorer.score_locator(selector: str, element: dict | None = None, action_description: str = "") -> dict[str, Any]`
Score a single locator and return metadata including `selector`, `type`, `score`, `confidence`, and `fragility_reason`.

### `LocatorScorer.score_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]`
Score a list of locator candidates and return them sorted by score descending (shorter selectors preferred as tiebreaker).

### `LocatorScorer.get_fallback_candidates(failed_locator: str, all_candidates: list[dict[str, Any]], max_fallbacks: int = 2) -> list[dict[str, Any]]`
Return the top N fallback candidates that score higher than the failed locator.

## Scoring Hierarchy
| Locator Type | Base Score | Confidence |
|--------------|------------|------------|
| data-testid  | 100        | Excellent  |
| id           | 85         | High       |
| name         | 70         | Good       |
| aria-label   | 60         | Good       |
| role         | 55         | Fair       |
| css-class    | 40         | Fair       |
| text         | 35         | Low        |
| xpath        | 20         | Low        |

## Design Notes
- Higher score = more stable selector
- Specificity modifier penalizes overly-specific CSS paths
- Confidence labels derived from score ranges
- Used by `locator_fallback.py` at runtime and `failure_reporter.py` for diagnostics
- NOT used by design-time `placeholder_resolver.py` (uses `placeholder_scorers.py` instead)

## Related Files
- `src/locator_fallback.py` — consumes scores for runtime fallback selection
- `src/failure_reporter.py` — uses scores for diagnostic alternatives
- `src/placeholder_scorers.py` — sibling scoring module for design-time resolution (separate concern)