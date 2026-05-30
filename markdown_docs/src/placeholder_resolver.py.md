# `src/placeholder_resolver.py`

## High-Level Purpose
Core placeholder resolution engine that matches `{{TOKEN:description}}` tokens against scraped DOM candidates using semantic matching, confidence scoring, and page-context validation.

## Module Metadata
- **Lines:** ~520
- **Imports:** `re`, `logging`, `dataclasses`, `typing`, `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`

## Classes

### `PlaceholderContext` (dataclass)
Holds token, description, and resolved selector for a single placeholder.

### `PlaceholderResolver`
Main resolution class.
| Method | Description |
|--------|-------------|
| `resolve(code: str, pages: list[PageData]) -> list[PlaceholderContext]` | Finds all placeholder tokens and resolves each against page candidates |
| `resolve_single(token: str, candidates: list[Element]) -> ScoreResult` | Resolves one token against candidate elements |
| `_find_candidates(token: str, pages: list[PageData]) -> list[Element]` | Scrapes matching elements across pages |
| `_apply_page_context(token: str, candidates: list[Element]) -> list[Element]` | Filters candidates by page-context rules |

## Functions

### `resolve_placeholders(code: str, pages: list[PageData]) -> tuple[str, list[PlaceholderContext]]`
Top-level function — returns resolved code and context list.

### `extract_placeholders(code: str) -> list[PlaceholderContext]`
Regex-based extraction of `{{TOKEN:description}}` patterns.

## Key Design Decisions
- Token-only placeholders in skeleton phase (no real selectors)
- Page-context validation prevents cross-page mismatches
- Confidence threshold gate before accepting a match

## Dependencies
- `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`