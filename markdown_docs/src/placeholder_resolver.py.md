# `src/placeholder_resolver.py`

## High-Level Purpose
Core placeholder resolution engine that matches `{{TOKEN:description}}` tokens against scraped DOM candidates using semantic matching, confidence scoring, and page-context validation.

## Module Metadata
- **Lines:** ~530
- **Imports:** `re`, `logging`, `dataclasses`, `typing`, `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`
- **RAG update:** 2026-07-21 — `golden_patterns` optional kwarg on `rank_candidates()`

## Classes

### `PlaceholderContext` (dataclass)
Holds token, description, and resolved selector for a single placeholder.

### `PlaceholderResolver`
Main resolution class.
| Method | Description |
|--------|-------------|
| `resolve(code: str, pages: list[PageData]) -> list[PlaceholderContext]` | Finds all placeholder tokens and resolves each against page candidates |
| `resolve_single(token: str, candidates: list[Element]) -> ScoreResult` | Resolves one token against candidate elements |
| `resolve_url(description, pages_data, known_urls=None)` | Resolve navigation placeholders to the best matching scraped URL (direct URL → known_urls substring → discovered hrefs → semantic word scoring) |
| `_find_candidates(token: str, pages: list[PageData]) -> list[Element]` | Scrapes matching elements across pages |
| `_apply_page_context(token: str, candidates: list[Element]) -> list[Element]` | Filters candidates by page-context rules |
| `rank_candidates(candidates, description, *, golden_patterns=None)` | Scores and ranks candidates; `golden_patterns` (Phase 3 RAG) adds bonus for golden pattern matches |

## Key Design Decisions
- Token-only placeholders in skeleton phase (no real selectors)
- Page-context validation prevents cross-page mismatches
- Confidence threshold gate before accepting a match
- `resolve_url` scoring gives +4 bonuses for product/cart/checkout path words; the product bonus set includes `inventory` (2026-08-03) so saucedemo's `/inventory.html` wins "products page loaded" style resolutions
- **RAG golden_patterns (2026-07-21):** Optional kwarg passed through to `PlaceholderScorer.compute_element_score()` — advisory bonus, zero behaviour change when None

## Dependencies
- `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`
