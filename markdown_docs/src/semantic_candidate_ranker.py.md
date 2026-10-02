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

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 2 items):

### `AsyncGeneratorLike` (class)

Minimal protocol for async text generation used by the ranker.

### `SemanticCandidateRanker` (class)

Use an LLM to rank a tiny candidate list without inventing selectors.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `AsyncGeneratorLike.generate` (method of `AsyncGeneratorLike`): `AsyncGeneratorLike.generate(prompt: str, timeout: int = 300, system_prompt: str | None = None, *, enable_thinking: bool | None = None) -> str` - Generate text from a prompt.
- `SemanticCandidateRanker.__init__` (method of `SemanticCandidateRanker`): `SemanticCandidateRanker.__init__(generator: AsyncGeneratorLike | None = None, *, timeout: float = DEFAULT_RESOLUTION_TIMEOUT, enable_thinking: bool | None = False, cache: Any | None = None) -> None`
- `SemanticCandidateRanker.choose_best_candidate` (method of `SemanticCandidateRanker`): `SemanticCandidateRanker.choose_best_candidate(*, action: str, description: str, current_url: str | None, candidates: list[dict[str, Any]], previous_steps: list[str] | None = None) -> dict[str, Any] | None` - Return the best candidate from a short list, or None on failure. B-020: Returns additional keys for ASSERT actions: - assertion_type: e.g. "toBeVisible", "toHaveText" - expected_value: optional, for toHaveText/toConta...
- `SemanticCandidateRanker.choose_best_candidates_batch` (method of `SemanticCandidateRanker`): `SemanticCandidateRanker.choose_best_candidates_batch(*, items: list[dict[str, Any]]) -> list[dict[str, Any] | None]` - Batch-resolve multiple placeholder-candidate sets in one LLM call. Each item in items should be a dict with keys: - action: str - description: str - candidates: list of candidate dicts Returns a list of the same l...
- `DEFAULT_RESOLUTION_TIMEOUT` (constant): `DEFAULT_RESOLUTION_TIMEOUT = float(os.getenv('AITEST_RESOLUTION_TIMEOUT', '120.0'))`
- `ASSERTION_TYPES` (constant): `ASSERTION_TYPES = frozenset({'toBeVisible', 'toHaveText', 'toContainText',...`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (3 items). Grouped under the public function that calls them.

### `SemanticCandidateRanker.choose_best_candidate(*, action: str, description: str, current_url: str | None, candidates: list[dict[str, Any]], previous_steps: list[str] | None = None) -> dict[str, Any] | None` - method of `SemanticCandidateRanker`

- `_is_timeout_error(exc: BaseException) -> bool` (function): True if exc (or anything in its cause chain) is a timeout. LLMClient.generate wraps provider errors in RuntimeError, so the underlying httpx timeout may sit one level down the cause chain.
- `_build_prompt(*, action: str, description: str, current_url: str | None, candidates: list[dict[str, Any]], previous_steps: list[str] | None = None) -> str` (method of `SemanticCandidateRanker`): Return a compact ranking prompt for the candidate shortlist.

### `SemanticCandidateRanker.choose_best_candidates_batch(*, items: list[dict[str, Any]]) -> list[dict[str, Any] | None]` - method of `SemanticCandidateRanker`

- `_build_batch_prompt(batch_items: list[tuple[int, dict[str, Any]]]) -> str` (method of `SemanticCandidateRanker`): Build a batch prompt for multiple placeholder-candidate groups. The LLM returns JSON with a "results" array, one entry per placeholder: {"results": [{"id": 0, "selected_index": 1, ...}, ...]}
