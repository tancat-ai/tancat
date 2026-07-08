# `src/run_history_cli.py` — CLI Run History Formatter

## Purpose

ASCII table formatters for run history data, designed for terminal/CLI display. Complements the Plotly-based chart builder in `run_history_chart.py` for environments without GUI capabilities.

## Constants

| Constant | Value |
|----------|-------|
| `_HEADER` | `"=== Run History ==="` |
| `_FLAKY_HEADER_PREFIX` | `"=== Flaky Tests"` |
| `_COMPARISON_HEADER` | `"=== Last Run Comparison ==="` |

## Functions

### `format_run_history_table(runs: list[PersistedRunResult], max_rows: int = 10) -> str`

Returns an ASCII table of recent test runs (most recent first).

**Columns:** Date, Package, Pass, Fail, Skip, Err, Rate (%)

**Table format:**
```
=== Run History ===
last 10 of 25 runs

Date             Package              Pass   Fail   Skip    Err    Rate
---------------- -------------------- ----- ----- ----- ----- -------
2026-06-11 20:30 saucedemo-login        12     3     0     1   75.0%
...
```

### `format_flaky_tests_table(flaky_tests: list[tuple[str, dict[str, int]]]) -> str`

Returns an ASCII table of flaky tests with pass/fail counts and flakiness percentage.

**Columns:** Test Name, Pass, Fail, Flaky%

### `format_run_comparison(comparison: RunComparison | None) -> str`

Returns an ASCII summary comparing two consecutive runs.

**Sections:**
- Pass rate delta (`old% → new% (±Δ%)`)
- Improved tests (✓)
- Regressed tests (✗)
- New failures (⚠)

Returns "insufficient data (need 2+ runs)" when comparison is `None`.

### `format_full_history_summary(directory: str | None = None, max_rows: int = 10) -> str`

Composite function that loads all run results and produces a complete history summary combining:
1. Run history table
2. Flaky tests table (if 2+ runs exist)
3. Last-run comparison (if 2+ runs exist)

### `_format_run_date(run_id: str) -> str`

Converts ISO timestamp to `"YYYY-MM-DD HH:MM"` format.

### `_truncate(text: str, max_width: int) -> str`

Truncates text with ellipsis (`…`) when exceeding `max_width`.

## Design Patterns

- **Formatter pattern**: Pure string-building functions with no I/O — returns formatted strings for consumption by any CLI renderer.
- **Composable design**: Individual formatters can be used independently or combined via `format_full_history_summary`.
