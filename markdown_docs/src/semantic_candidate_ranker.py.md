# semantic_candidate_ranker.py

## Purpose
Context candidate prioritization engine for placeholder resolution. Scores and ranks DOM element candidates based on their relevance to a placeholder's semantic description, using token overlap, attribute quality, and positional heuristics.

## Location
`src/semantic_candidate_ranker.py`

## Dependencies
- `src.semantic_matcher` — token-based semantic similarity scoring
- `dataclasses` (standard library)
- `logging` (standard library)

## Module Constants
- `TEXT_MATCH_WEIGHT: float` — Weight for text-content overlap score
- `ATTRIBUTE_MATCH_WEIGHT: float` — Weight for attribute-based similarity
- `POSITION_PENALTY: float` — Penalty for elements deep in the DOM tree

## Public API

### `rank_candidates(action_description: str, candidates: list[dict[str, Any]], page_url: str | None = None) -> list[dict[str, Any]]`
Score and rank a list of element candidates by their suitability for resolving a placeholder. Returns candidates sorted by descending score, each enriched with a `_rank_score` key.

### `compute_candidate_score(description_tokens: set[str], element: dict[str, Any]) -> float`
Compute a raw relevance score for a single candidate element based on token overlap with element attributes (text, attributes, tag name).

### `apply_positional_bonus(score: float, depth: int) -> float`
Apply a small bonus for shallow DOM elements (preferred for stability).

## Design Notes
- Token-based approach: splits action description into words, counts overlap with element text and attribute values
- Page-aware: candidates from the expected page get a small bonus
- Positional bonus: shallow elements score higher (more stable across page changes)
- Used by `placeholder_orchestrator.py` during candidate selection phase

## Related Files
- `src/semantic_matcher.py` — provides low-level token similarity used by ranker
- `src/placeholder_orchestrator.py` — consumer of ranked candidates
- `src/placeholder_resolver.py` — sibling resolution module