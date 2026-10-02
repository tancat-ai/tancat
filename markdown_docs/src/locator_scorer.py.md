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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `LocatorScorer.score_locator` (method of `LocatorScorer`): `LocatorScorer.score_locator(selector: str, element: dict[str, Any] | None = None, action_description: str = '') -> dict[str, Any]` - Score a single locator and return metadata. Args: selector: The Playwright selector string to score. element: Optional scraped element dict for additional context. action_description: Optional action description for t...
- `LocatorScorer.score_candidates` (method of `LocatorScorer`): `LocatorScorer.score_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]` - Score a list of locator candidates and return sorted by score descending. Each candidate is a dict with 'selector' and optionally 'element' (scraped element data with fields like id, aria_label, classes, etc.). Args:...
- `LocatorScorer.get_fallback_candidates` (method of `LocatorScorer`): `LocatorScorer.get_fallback_candidates(failed_locator: str, all_candidates: list[dict[str, Any]], max_fallbacks: int = 2) -> list[dict[str, Any]]` - Get the top N fallback candidates that are higher-scoring than the failed locator. Args: failed_locator: The selector that failed. all_candidates: All available locator candidates from the page. max_fallbacks: Maximum...


## How It Works (Internals)

Private `_`-helpers - the module's real logic (4 items). Grouped under the public function that calls them.

### `LocatorScorer.score_locator(selector: str, element: dict[str, Any] | None = None, action_description: str = '') -> dict[str, Any]` - method of `LocatorScorer`

- `_text_matches_description(element_text: str, action_description: str) -> bool` (method of `LocatorScorer`): Check if element text plausibly matches the action description. Used to apply a bonus when the element's visible text aligns with what the test step is trying to do.
- `_determine_locator_type(selector: str, element: dict[str, Any]) -> tuple[str, int]` (method of `LocatorScorer`): Determine the locator type and base score from a selector string. Priority: Check for the most specific/reliable locator type first. Args: selector: The Playwright selector string. element: Scraped element data for ad...
- `_apply_specificity_modifier(base_score: int, selector: str, loc_type: str) -> int` (method of `LocatorScorer`): Apply modifiers to the base score based on selector specificity. More specific selectors get a small bonus; overly broad ones get a penalty. Args: base_score: The base score for this locator type. selector: The full s...
- `_score_to_confidence(score: int) -> str` (method of `LocatorScorer`): Convert a numeric score to a confidence level label.
