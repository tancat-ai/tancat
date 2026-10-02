# `src/skip_manager.py` — Skip Insertion Helpers

## Purpose
Code cleanup and skip-insertion helpers for placeholder resolution. Extracted from `placeholder_orchestrator.py`. Handles removing raw placeholder lines, old per-placeholder skip lines, and inserting consolidated `pytest.skip()` calls.

## Functions
- `insert_consolidated_skips(code: str, unresolved: list[str]) -> str` — insert single pytest.skip for all unresolved placeholders
- `remove_raw_placeholder_lines(code: str) -> str` — strip unresolved {{PLACEHOLDER}} lines
- `remove_old_placeholder_skips(code: str) -> str` — remove stale per-placeholder skip lines

## Related
- `src/placeholder_orchestrator.py` — consumer

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `build_test_resolution_counts` (function): `build_test_resolution_counts(journeys: list[TestJourney], unresolved_occurrences: dict[str, set[tuple[int, str]]]) -> list[TestResolutionCounts]` - Return per-test resolved/unresolved placeholder counts (B-097). unresolved_occurrences is built from every place the resolver decided a placeholder would emit a skip: the consolidated per-test skip AND the survivi...


## How It Works (Internals)

Private `_`-helpers - the module's real logic (1 item). Grouped under the public function that calls them.

### `insert_consolidated_skips(lines: list[str], journeys: list[TestJourney], journey_unresolved: dict[str, list[str]], original_lines: list[str], test_counts: dict[str, TestResolutionCounts] | None = None) -> list[str]` - function

- `_counts_suffix(counts: TestResolutionCounts | None) -> str` (function): Return the B-097 count suffix for a skip message, or '' when unknown. No closing parenthesis: naive parsers that read pytest.skip((.*?)) (e.g. the skipped-test UI panel) would stop at the first ) and truncate...
