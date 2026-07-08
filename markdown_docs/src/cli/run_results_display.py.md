# `src/cli/run_results_display.py` — Structured Run Results Display

## Purpose

ANSI-formatted rendering of pytest run results for the CLI. Includes metrics summary, per-test table, failure classification, and re-run suggestions.

## Functions

### `_status_badge(status: str) -> str`

Returns a coloured status badge: `[PASS]` (green), `[FAIL]` (red), `[ERROR]` (red), `[SKIP]` (yellow).

### `render_run_metrics(run: RunResult) -> None`

Single-line coloured summary:
```
✅ Run Results: ✅ 5 passed, 1 failed, 0 errors, 2 skipped in 12.34s
```

Uses `phosphor_green` for the overall badge when all tests pass.

### `render_results_table(run: RunResult) -> None`

ASCII table of per-test results:
```
  STATUS   TEST NAME                                DUR
  ──────────────────────────────────────────────────────
  [PASS]   test_01_navigate_to_home                0.45s
  [FAIL]   test_02_login_with_valid_credentials     1.23s
           AssertionError: Expected "Welcome" to be visible...
```

- Dynamic column width (clamped 40–80 chars)
- Failed tests show truncated error messages (3 lines max)

### `render_failure_details(run: RunResult) -> None`

Classified failure details using `classify_failure()`:
```
  Failure Classification:
  ─────────────────────────────────────
  [1] test_02_login_with_valid_credentials
      Category:  locator_timeout
      Locator:   `input[name="email"]`
      Suggestion: Check that the element exists on the page...
```

### `_suggestion_for_category(category: FailureCategory) -> str`

Returns human-readable remediation suggestions:

| Category | Suggestion |
|----------|-----------|
| `LOCATOR_TIMEOUT` | Check element existence; increase timeout or use fallback |
| `STRICT_VIOLATION` | Make locator more specific (add ID/data-testid) |
| `NAVIGATION_ERROR` | Verify URL, check redirects/auth requirements |
| `ASSERTION_FAILURE` | Check for page state changes or dynamic content |
| `OTHER` | Review error message |

### `render_raw_output(run: RunResult, expanded=False) -> None`

Prints raw pytest output. If `expanded=False`, prompts user with `[y/N]` first.

### `render_run_results(run: RunResult, show_raw=False) -> None`

Combined display: metrics → table → failure details → optional raw output.

### `render_run_history_summary() -> None`

Displays run history using `format_full_history_summary()` from `src.run_history_cli`.
