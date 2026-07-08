# `src/ui/ui_results.py` — Results Display Panel and Run Handlers

## Purpose

Streamlit component for displaying pipeline results and running generated tests.

## Class: `ResultsPanel`

### `render_tabs(results, skeleton, saved_path, manifest_path) -> None` (static)

Renders 3 tabs:

| Tab | Content |
|-----|---------|
| Final Code | Python code display + download button + saved path/manifest captions |
| Skeleton | Pre-resolution skeleton code display |
| Scrape Summary | List of scraped URLs with element counts + unresolved placeholders warning |

### `render_run_section() -> None` (static)

Renders "Run Generated Tests" and "Re-run Failed Only" buttons. Both are disabled when `pipeline_saved_path` is empty. Re-run also requires a previous `pipeline_run_result`.

## Functions

### `_handle_run_tests() -> None`

Handles the "Run Generated Tests" button:
1. Calls `PipelineRunService().run_saved_test()`
2. Stores results in `st.session_state` (`pipeline_run_result`, `pipeline_run_output`, etc.)
3. Calls `_store_run_report()`
4. Triggers `st.rerun()`

### `_handle_rerun_failed() -> None`

Handles the "Re-run Failed Only" button:
1. Passes `rerun_failed_only=True` and `previous_run` to `run_saved_test()`
2. Same storage and rerun logic as `_handle_run_tests()`

### `_store_run_report() -> None`

Delegates to `src.ui.shared.store_run_report()` with current session state values.
