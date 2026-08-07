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

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 3 items):

### `RunResult` (class)

Aggregated result for a full pytest run.

### `is_run_result(obj: object) -> TypeGuard[RunResult]` (function)

Reload-safe check for :class:`RunResult` instances.

### `format_pytest_output_for_display(raw: str, max_lines: int = 80) -> str` (function)

Return a concise, high-signal pytest output snippet for UI display.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### `parse_pytest_output`
- `_parse_duration(value: str | None, unit: str | None = None) -> float` (function) — Parse a duration value with optional unit to seconds.
