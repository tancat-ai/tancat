# `src/run_history_chart.py` — Plotly Figure Factory for Run History

## Purpose

Pure Plotly figure builder with no Streamlit or CLI dependencies. Consumes `PersistedRunResult` objects from `src.run_result_persistence` and produces stacked bar charts with pass-rate line overlay and flaky-test markers.

Also provides `build_chart_from_db()` for direct SQLite-backed chart building using SQL aggregation queries — avoids loading all objects into memory.

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `COLOR_PASS` | `"#2ecc71"` | Green |
| `COLOR_FAIL` | `"#e74c3c"` | Red |
| `COLOR_SKIP` | `"#f1c40f"` | Yellow |
| `COLOR_ERROR` | `"#95a5a6"` | Grey |
| `COLOR_LINE` | `"#2c3e50"` | Dark blue (pass-rate line) |

## Private Helpers

### `_parse_run_id(run_id: str) -> datetime`

Best-effort ISO-8601 parse. Falls back to `datetime.min` on failure.

### `_format_timestamp(dt: datetime) -> str`

Formats a datetime as `"YYYY-MM-DD HH:MM"` for x-axis labels.

## Public API

### `build_run_history_chart(runs: list[PersistedRunResult], include_flaky_markers: bool = True) -> go.Figure`

Builds a stacked bar chart from an in-memory list of run results.

**Chart elements:**
- X-axis: run timestamp (chronological, oldest-first)
- Primary Y-axis: stacked bars (pass/fail/skip/error counts)
- Secondary Y-axis: pass rate % line overlay (0–100)
- Flaky markers (`❗`): placed above bars for runs containing tests that passed in some runs and failed in others

**Flaky detection logic:** A test is flaky if `"passed" in statuses` AND any status is `"failed"` or `"error"`.

### `build_chart_from_db(date_from: str | None = None, date_to: str | None = None, include_flaky_markers: bool = True) -> go.Figure`

Builds the same chart type but reads directly from SQLite via `_get_db()`, using `get_run_stats_for_chart()` and `get_flaky_tests()` SQL queries. Ideal for large datasets with date-range filtering.

## Architecture

- **Pure function design**: No I/O or side effects — returns Plotly `go.Figure` objects consumed by `st.plotly_chart()` or `fig.show()`.
- **Two entry points**: In-memory (`build_run_history_chart`) vs. SQL-backed (`build_chart_from_db`) to handle different data volume scenarios.
- **Empty state handling**: Both functions return a placeholder figure with "No run history available" text when no data exists.
