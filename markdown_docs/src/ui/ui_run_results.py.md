# `src/ui/ui_run_results.py` — Run Results Display, Failure Classification, and Locator Repair

## Purpose

Streamlit component for displaying test run results with failure classification, coverage analysis, locator repair panel, and inline evidence viewer.

## Class: `RunResultsDisplay`

### `render(run_result: RunResult) -> None` (static)

Full run results display:

1. **Command caption**: Shows the pytest command used
2. **Error banner**: If pytest hit collection/import errors
3. **Metrics row**: Total, Passed, Failed, Skipped, Errors (5 columns)
4. **Coverage table**: Criteria-level coverage analysis with pass/fail mapping
5. **Results table**: Per-test results with repair buttons (see `_render_results_table`)
6. **Repair panel**: Shown when user clicks a repair button (see `_render_repair_panel`)
7. **Inline evidence**: Annotated screenshots for just-run tests (see `_render_inline_evidence`)
8. **Pytest output**: Expandable raw output (auto-expanded on errors)
9. **Downloads**: Report download buttons via `RenderDownloads.render()`

## Functions

### `_render_inline_evidence(run_result) -> None`

Renders inline evidence viewer:
- Loads evidence sidecars from `evidence/` directory
- Filters to only tests that just ran (matches test names from `RunResult`)
- Selectable sidecar with view modes: annotated, heatmap, clean
- Shows step details with pass/fail icons

### `_render_results_table(results) -> None`

Per-test results table with repair buttons:

| Status | Display |
|--------|---------|
| Passed | ✅ icon |
| Failed | ❌ icon + error caption + repair button (if locator failure) |
| Skipped | ⏭️ icon |

**Repair button logic:**
- `LOCATOR_TIMEOUT` / `STRICT_VIOLATION`: Shows 🔧 Fix locator button → opens repair panel
- `ASSERTION_FAILURE`: Shows info caption (no repair)
- `NAVIGATION_ERROR`: Shows info caption (no repair)

### `_render_repair_panel() -> None`

Dispatcher based on `st.session_state.repair_status`:
- `"waiting"` → `_render_repair_waiting_panel()`
- `"browser_requested"` → `_render_repair_browser_session()`
- `"patched"` / `"error"` → `_render_repair_result_panel()`

### `_render_repair_waiting_panel() -> None`

Shows repair mode UI with failed locator info, test file path, and "Open browser and fix locator" button. Sets `repair_status = "browser_requested"` on click.

### `_render_repair_browser_session() -> None`

Runs a headed browser session via `run_codegen_session()`:
1. Opens browser at the failure URL
2. Waits up to 120s for user to click the correct element
3. Applies the new locator via `LocatorPatch` + `apply_patch_to_file()`
4. Sets `repair_status = "patched"` or `"error"` based on outcome

### `_render_repair_result_panel() -> None`

Shows success/error message with:
- Updated test file viewer (expanded)
- "Run Generated Tests" button (enabled only if patched)
- "Done" button to reset repair state
