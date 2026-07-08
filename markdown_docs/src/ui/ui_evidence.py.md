# `src/ui/ui_evidence.py` — Evidence Viewer

## Purpose

Streamlit component for viewing test execution evidence: annotated screenshots, Gantt timelines, coverage heatmaps, and run history charts.

## Class: `EvidenceViewer`

### `__init__(base_dir: Path)`

Initialises with the base output directory (typically `generated_tests/`).

### `render() -> None`

Renders the evidence viewer section with 4 tabs:

1. **Annotated Screenshot**: Selectable evidence sidecars with view modes (annotated/heatmap/clean)
2. **Gantt Timeline**: Plotly Gantt chart with grouping modes and execution details
3. **Coverage Heat Map**: Story confidence heatmap with tester-confirmed/unreviewed/gap metrics
4. **Run History**: Stacked bar chart with pass-rate overlay and flaky test detection

Plus a suite heatmap overview section.

### `_render_annotated_screenshot(sidecars) -> None`

Dropdown to select an evidence sidecar. View modes:
- **annotated**: Numbered step overlays on screenshots
- **heatmap**: Density rings showing interaction hotspots
- **clean**: Screenshot only, no annotations

Uses `generate_annotated_journey()` to produce HTML rendered via `st.components.v1.html()`.

### `_render_gantt_timeline(evidence_dirs) -> None`

Gantt chart from evidence data:
- **Grouping modes**: `condition_type`, `sprint`, `source`
- Summary metrics: fastest test, slowest test, coverage
- Condition metadata from `test_plan.conditions` (type, sprint, source)
- Test execution details panel with sidecar step-by-step view
- Raw execution data table (sortable)

### `_render_sidecar_details(sidecar) -> None`

Detailed view of a single evidence sidecar:
- Condition ref, story ref, status, duration, test name
- Step-by-step breakdown with pass/fail icons and error messages

### `_render_coverage_heatmap(evidence_dirs) -> None`

Story confidence heatmap:
- Metrics: total stories, tester confirmed, gaps/failures, unreviewed
- Plotly heatmap visualisation
- Detailed dataframe with per-story pass/fail/skip counts

### `_render_suite_heatmap(sidecars, evidence_dirs) -> None`

Suite-wide coverage overview:
- Extracts unique URLs from all evidence sidecars (navigate steps)
- Selectable page URL with full-page heatmap rendering

### `_render_run_history() -> None`

Run history with Plotly chart:
- Scope selector: All packages or individual package
- Metrics: total runs, avg pass rate, total passed/failed
- Flaky test checkbox with expanded dataframe
- Last run comparison (improved/regressed/new failures)

### `_filter_runs_by_package(runs, scope) -> list`

Filters runs by test package scope. Returns all runs when scope is `"All"`.

### `_render_run_comparison(comparison) -> None`

Renders improved (✓), regressed (✗), and new failures (⚠) lists.
