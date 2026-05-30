# semantic_matcher.py

## Purpose
Token-based semantic similarity scoring extracted from placeholder_resolver. Computes overlap between a description (e.g., placeholder action text) and an element's textual representation using normalized token sets.

## Location
`src/semantic_matcher.py`

## Dependencies
- `re` (standard library)
- `string` (standard library)

## Module Constants
- `STOP_WORDS: set[str]` — Common English stop words removed before token comparison
- `MIN_TOKEN_LENGTH: int` — Minimum token length (2) to ignore single characters

## Public API

### `normalize_text(text: str) -> str`
Lowercase, strip whitespace, and remove punctuation from input text.

### `tokenize(text: str) -> set[str]`
Split text into a set of meaningful tokens, filtering out stop words and short tokens.

### `semantic_similarity(description: str, element_text: str) -> float`
Compute Jaccard-like similarity between description tokens and element text tokens. Returns a float in [0.0, 1.0] where 1.0 means all description tokens appear in element text.

### `tokens_match(description: str, target: str, threshold: float = 0.3) -> bool`
Convenience wrapper that returns `True` when `semantic_similarity` meets or exceeds the threshold.

## Design Notes
- Pure functions — no side effects, fully testable
- Token-based approach avoids expensive NLP dependencies
- Threshold of 0.3 is the default; callers can adjust for stricter/looser matching
- Used by both `semantic_candidate_ranker.py` and `placeholder_resolver.py`

## Related Files
- `src/semantic_candidate_ranker.py` — uses similarity scoring for candidate ranking
- `src/placeholder_resolver.py` — parent module from which this was extracted
- `src/intent_matcher.py` — sibling matching module for placeholder intent classification