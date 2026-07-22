# `src/rag_retriever.py`

## High-Level Purpose

Bridges `RAGStore` into the placeholder resolution pipeline. Provides a resolver-friendly API: takes a placeholder description + action type, queries the vector store, returns `RetrievedPattern` objects. The `scoring_bonus_for()` method evaluates whether a DOM element matches a retrieved golden pattern (by selector overlap), returning the bonus amount to add to the element's score.

When the store is `None` (RAG disabled), every method returns empty/no-op — zero overhead.

## Module Metadata

- **Lines:** ~100
- **Imports:** `typing.TYPE_CHECKING`, `src.rag_store.RetrievedPattern`, `src.placeholder_scorers.PlaceholderScorer`
- **Spec:** `docs/specs/FEATURE_SPEC_phase3_rag.md` §3b
- **Shipped:** 2026-07-21

## Class: `RAGRetriever`

### `__init__(self, store: RAGStore | None) -> None`
Initialise with an optional `RAGStore`. Pass `None` to disable RAG.

### `enabled` (property) → `bool`
Whether RAG is enabled (store is not `None` and not empty).

### `retrieve(description, *, action_type="", k=5, min_confidence=0.6) -> list[RetrievedPattern]`
Retrieve golden patterns and doc chunks for a placeholder. Returns empty list when RAG is disabled or the store is empty. Prepends `action_type:` to the query for better embedding discrimination.

### `scoring_bonus_for(element: dict[str, str], patterns: list[RetrievedPattern]) -> float`
Compute a scoring bonus for an element based on golden pattern overlap:

| Match type | Bonus |
|---|---|
| **Direct selector match** | `GOLDEN_PATTERN_BONUS (20) × pattern.confidence` |
| **Tolerance/substring match** | `GOLDEN_PATTERN_BONUS (20) × 0.5 × pattern.confidence` |
| **No match / doc-only patterns** | `0.0` |

Only considers patterns with `source == "golden"`. The bonus is designed to tip the scale between similarly-scored candidates (e.g. two elements scoring ~25 each) without overriding strong structural matches (+80) or visibility penalties (-40).

## Key Design Decisions

- **Null-object pattern:** When `store is None`, all methods return empty/no-op — the resolver doesn't need to check `enabled` before calling.
- **Selector-based matching:** `scoring_bonus_for()` compares the element's CSS selector against golden pattern selectors (exact and substring). Does not re-embed — fast enough for per-candidate evaluation.
- **Bonus magnitude +20:** Mirrors `_vision_enriched_bonus` — strong enough to break ties but won't override structural/id matches. Tunable via `PlaceholderScorer.GOLDEN_PATTERN_BONUS`.

## Dependencies

- `src.rag_store.RAGStore`, `src.rag_store.RetrievedPattern` — storage and data models
- `src.placeholder_scorers.PlaceholderScorer.GOLDEN_PATTERN_BONUS` — bonus constant

## Depended On By

- `src/placeholder_orchestrator.py` — calls `retrieve()` + passes patterns to resolver
- `src/orchestrator.py` — calls `_build_rag_retriever()` to construct
- `tests/test_rag_retriever.py` — 16 unit tests

## Usage

```python
from src.rag_retriever import RAGRetriever
from src.rag_store import RAGStore, MilvusLiteBackend, SentenceTransformerEmbedder
from src.storage import get_storage

embedder = SentenceTransformerEmbedder()
backend = MilvusLiteBackend(str(get_storage().rag_path()), embedder.dimension)
store = RAGStore(backend, embedder)
retriever = RAGRetriever(store)

patterns = retriever.retrieve("Add to cart button", action_type="CLICK")
for elem in candidates:
    bonus = retriever.scoring_bonus_for(elem, patterns)
```
