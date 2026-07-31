# `src/skip_manager.py` — Skip Insertion Helpers

## Purpose
Code cleanup and skip-insertion helpers for placeholder resolution. Extracted from `placeholder_orchestrator.py`. Handles removing raw placeholder lines, old per-placeholder skip lines, and inserting consolidated `pytest.skip()` calls.

## Functions
- `insert_consolidated_skips(code: str, unresolved: list[str]) -> str` — insert single pytest.skip for all unresolved placeholders
- `remove_raw_placeholder_lines(code: str) -> str` — strip unresolved {{PLACEHOLDER}} lines
- `remove_old_placeholder_skips(code: str) -> str` — remove stale per-placeholder skip lines

## Related
- `src/placeholder_orchestrator.py` — consumer
