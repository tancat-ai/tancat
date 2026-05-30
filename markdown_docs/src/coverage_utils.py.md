# `src/coverage_utils.py`

## High-Level Purpose
Centralizes logic for turning acceptance criteria and generated test code into structured coverage information. Reusable by Streamlit UI, CLI, and reports.

## Module Metadata
- **Lines:** 188
- **Imports:** `__future__`, `re`, `collections.abc`, `dataclasses`, `typing`

## Classes

### `RequirementCoverage` (dataclass)
Tracks coverage for a single requirement.
- Fields: `id`, `description`, `status`, `linked_tests`

### `CoverageRunResult` (Protocol)
Protocol for minimal test-run result objects.
- Properties: `name`, `status`, `duration`

### `CoverageDisplayRow` (dataclass)
Display-compatible coverage row for UI tables.
- Fields: `criterion`, `status`, `test_name`, `duration`, `notes`

## Functions

### `extract_test_names(generated_code: str) -> list[str]`
Extracts pytest-style test function names from Python source using regex.

### `compute_coverage(criteria: list[str], code: str, run_results: Sequence[CoverageRunResult] | None) -> list[RequirementCoverage]`
Maps criteria to test names by number-based matching (TC-001 → test_01_*) then keyword fallback.

### `coverage_to_display_rows(coverage: list[RequirementCoverage]) -> list[CoverageDisplayRow]`
Converts coverage data to UI-friendly display rows.

## Key Design Decisions
- Number-based matching before keyword fallback prevents false positives
- Protocol-based interface for run results enables duck typing
- Zero external dependencies — pure computation

## Dependencies
- None — stdlib only