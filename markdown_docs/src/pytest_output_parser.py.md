# `src/pytest_output_parser.py`

## High-Level Purpose
Parses raw pytest output to extract test results, failures, durations, and error classifications for reporting.

## Module Metadata
- **Lines:** ~200
- **Imports:** `re`, `dataclasses`, `typing`

## Classes

### `TestResult` (dataclass)
Parsed result: test_id, status (PASSED/FAILED/SKIPPED), duration, error_message, error_type.

### `SuiteSummary` (dataclass)
Aggregate: total, passed, failed, skipped, errors list.

## Functions

### `parse_pytest_output(output: str) -> SuiteSummary`
Main parser — processes full pytest text output into structured results.

### `extract_failure_details(output: str) -> list[dict]`
Extracts per-test failure details: traceback, error type, error message.

### `parse_duration(line: str) -> float`
Extracts test duration from pytest result line (e.g., `0.42s`).

## Key Design Decisions
- Regex-based parsing — no dependency on pytest internal APIs
- Handles both verbose and quiet pytest output formats
- Error classification by type (TimeoutError, NoTimeout, etc.)

## Dependencies
- None from `src/` — stdlib only