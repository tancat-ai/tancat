# `src/failure_classifier.py`

## High-Level Purpose
Classifies test failures into machine-readable categories for dashboard and trend analysis.

## Module Metadata
- **Lines:** 178
- **Imports:** `__future__`, `re`, `enum`, `dataclasses`, `typing`

## Enums

### `FailureCategory` (str, Enum)
Values: `NO_MATCH`, `MULTI_MATCH`, `TIMEOUT`, `ERROR`, `ASSERTION`, `PHANTOM`, `UNKNOWN`

## Functions

### `classify_failure(text: str, category: str | None = None) -> FailureCategory`
Maps pytest failure text to `FailureCategory` using keyword heuristics.

### `classify_failure_pattern(message: str) -> FailureCategory`
Pattern-based classifier for structured error messages.

### `classify_test_result(test: dict, *, category: str | None = None) -> FailureCategory`
Classifies a single test result dict.

### `summarize_failures(results: list[dict]) -> FailureSummary`
Aggregates categorized failures into counts and sorted lists.

## Classes

### `FailureSummary` (dataclass)
Aggregated failure summary: total_passed, total_failed, category_counts, top_categories.

## Key Design Decisions
- Keyword-based heuristics (no ML dependency)
- Categories align with strict-mode pytest errors
- Stateless pure functions — easy to test and compose

## Dependencies
- None — stdlib only