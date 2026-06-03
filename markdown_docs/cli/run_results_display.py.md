# cli/run_results_display.py

**Path:** `cli/run_results_display.py`  
**Created:** 2026-06-02  
**Status:** Stable — part of Run Results feature (AI-008)

---

## Overview

Provides structured, ANSI-colored CLI output for pytest run results. This module fills Gap 1 of the Run Results feature spec ([FEATURE_SPEC_run_results.md](../../docs/specs/FEATURE_SPEC_run_results.md)), bringing CLI run output to parity with the Streamlit UI's `RunResultsDisplay`.

## Purpose

When the CLI executes tests via `PipelineRunService.run_saved_test()`, it receives a `RunResult` object. Previously, this data was not presented in a structured way in the CLI — users saw raw pytest output. This module renders:
- A colored metrics summary line
- An ASCII table of per-test results
- Failure classification with actionable suggestions
- Optional raw pytest output view

## Dependencies

| Import | Source | Purpose |
|--------|--------|---------|
| `src.pytest_output_parser.RunResult` | `src/pytest_output_parser.py` | Dataclass containing test results |
| `src.pytest_output_parser.TestResult` | `src/pytest_output_parser.py` | Individual test result dataclass |
| `src.failure_classifier` | `src/failure_classifier.py` | `classify_failure()` and `FailureCategory` enum |
| `cli.color` | `cli/color.py` | ANSI color helper functions |

## Type Signatures

```python
def render_run_metrics(run: RunResult) -> None
def render_results_table(run: RunResult) -> None
def render_failure_details(run: RunResult) -> None
def render_raw_output(run: RunResult, expanded: bool = False) -> None
def render_run_results(run: RunResult, show_raw: bool = True) -> None
def _status_badge(status: str) -> str
def _suggestion_for_category(category: FailureCategory) -> str
```

## Functions

### `render_run_metrics(run: RunResult) -> None`

Renders a single-line colored summary of run outcomes.

**Format:** `🎯 Run Results: {pass_icon} Passed: X  {fail_icon} Failed: Y  {error_icon} Errors: Z  {skip_icon} Skipped: W — Duration: X.Xs`

**Color coding:**
- Pass count: green
- Fail count: red
- Error count: yellow
- Skipped count: cyan
- Duration: bold

**Example output:**
```
  🎯 Run Results:  ✅ Passed: 5  ❌ Failed: 1  ⚠️ Errors: 0  ⏭️ Skipped: 0 — Duration: 12.34s
```

### `render_results_table(run: RunResult) -> None`

Renders an ASCII table with columns: Test Name, Status Badge, Duration.

**Table format:**
```
  ──────────────────────────────────────────────────────────
  Test Name                    Status   Duration
  ──────────────────────────────────────────────────────────
  test_01_login_page_...       [PASS]   0.50s
  test_02_add_to_cart_...      [FAIL]   1.23s
                               AssertionError: Expected 'OK'...
  ──────────────────────────────────────────────────────────
```

**Truncation rules:**
- Test names truncated to 30 chars with `...` suffix
- Error messages truncated to 80 chars with `...` suffix
- Max 3 error message lines shown per test

### `render_failure_details(run: RunResult) -> None`

Classifies each failed test using `classify_failure()` and displays categorized failures with suggestions.

**Format:**
```
  🔍 Failure Classification:
  ──────────────────────────────────────────────────────────
  • test_timeout (locator_timeout)
    Message: TimeoutError: waiting for locator('#btn')
    Suggestion: Check the locator exists on the page, or increase timeout

  • test_strict (strict_violation)
    Message: strict mode violation: resolved to 2 elements
    Suggestion: Use a more specific selector
  ──────────────────────────────────────────────────────────
```

**Failure categories mapped (from `FailureCategory` enum):**
- `locator_timeout` → "Check the locator exists on the page, or increase timeout"
- `strict_violation` → "Use a more specific selector to avoid matching multiple elements"
- `navigation_error` → "Check the URL is correct and the server is running"
- `assertion_failure` → "Review the assertion — the page state may have changed"
- `other` → "Review test output for details"

### `render_raw_output(run: RunResult, expanded: bool = False) -> None`

Optionally displays raw pytest output in a code block.

**Behavior:**
- If `expanded=True`: always show raw output
- If `expanded=False` and raw output exists: prompt user with "Show raw pytest output? [y/N]: "
- If no raw output: silently skip

### `render_run_results(run: RunResult, show_raw: bool = True) -> None`

Main entry point. Orchestrates all rendering functions in sequence:
1. Title separator
2. `render_run_metrics()`
3. `render_results_table()`
4. `render_failure_details()` (only if failures exist)
5. `render_raw_output()` (controlled by `show_raw`)
6. Bottom separator

### `_status_badge(status: str) -> str`

Internal helper. Maps test status strings to colored badge text.

| Status | Badge | Color |
|--------|-------|-------|
| `passed` | `[PASS]` | Green |
| `failed` | `[FAIL]` | Red |
| `error` | `[ERROR]` | Yellow |
| `skipped` | `[SKIP]` | Cyan |
| other | `[UNKNOWN]` | White |

### `_suggestion_for_category(category: FailureCategory) -> str`

Internal helper. Maps `FailureCategory` enum values to human-readable fix suggestions.

## Integration Points

### CLI Pipeline Runner

Called from `cli/pipeline_runner.py` after `PipelineRunService.run_saved_test()` returns:

```python
from cli.run_results_display import render_run_results

result = run_service.run_saved_test(...)
render_run_results(result.run_result, show_raw=False)
```

### Relationship to Streamlit UI

This module is the CLI equivalent of `src/ui_renderers.py` → `RunResultsDisplay.render()`. Both consume the same `RunResult` type from `src/pytest_output_parser.py`, ensuring consistent output across interfaces.

## Design Decisions

1. **No dependency on Terminal classes** — Uses `print()` directly rather than `TestingTerminal.write()` to keep the module standalone and testable.
2. **Failure classification via existing module** — Reuses `src/failure_classifier.py` rather than duplicating logic.
3. **ANSI colors via `cli.color`** — Consistent with other CLI modules.
4. **Proportional column width** — Table adapts to terminal width (default 80, min 40).

## Testing

Covered by `tests/test_cli_run_results_display.py` (31 tests):
- Status badge rendering for all statuses
- Metrics line rendering (all passed, mixed, zero)
- Results table rendering (empty, single, long names, truncation)
- Failure classification (timeout, strict violation, assertion, navigation)
- Suggestion mapping for all categories
- Raw output display (expanded, interactive yes/no)
- Full integration tests (all passed, empty run)

## Error Handling

- Gracefully handles empty `RunResult` (0 tests) by displaying a "No test results" message
- Truncates long test names and error messages to prevent terminal overflow
- Strips trailing whitespace from error messages for clean output

## Related Files

- `src/pytest_output_parser.py` — `RunResult`, `TestResult` dataclasses
- `src/failure_classifier.py` — `classify_failure()`, `FailureCategory`
- `src/ui_renderers.py` — `RunResultsDisplay` (Streamlit equivalent)
- `cli/pipeline_runner.py` — Integration caller
- `cli/color.py` — ANSI color utilities

---

*Document created: 2026-06-02*