# `src/ui/ui_saved_packages.py` — Saved Package Loader (AI-026)

## Purpose

Streamlit sidebar and main panel components for loading and re-running saved test packages. Discovers packages in `generated_tests/` via `package_manifest.json`.

## Class: `SavedPackagePanel`

### `render_sidebar() -> None`

Sidebar section:
- Lists all packages with test/run counts
- Selectable dropdown + "Load Package" button
- On load: populates session state with manifest, run results, history, and flaky tests
- Shows loaded summary with metrics and flaky warnings
- "Re-run Saved Suite" button (sets `pipeline_saved_path` and reruns)

### `_render_loaded_summary() -> None`

Sidebar summary of loaded package: name, creation date, story, URL, total runs/passed/failed, flaky test warnings.

### `render_main_panel() -> bool`

Main column detail view (returns `True` if a package is loaded):

**Sections:**
- Package metadata (created, provider, model, URL, file counts)
- User story (expandable)
- Test files (expandable, per-file code viewer)
- Page objects (expandable)
- Additional URLs (expandable)
- Run history table (expandable)
- Flaky tests list (expandable)
- Report paths (expandable)
- Evidence paths (expandable)
- Run buttons: "Run Saved Suite" / "Re-run Failed Only"

### `_render_run_history(runs_data) -> None`

Table with columns: Run ID, Total, Passed, Failed, Skipped, Duration.

### `_render_flaky_tests(flaky) -> None`

Per-test breakdown with pass/fail/skip counts.

### `_handle_rerun_saved_suite(package_root) -> None`

Runs the full saved suite via `PipelineRunService().run_saved_test()`. Stores results and calls `_store_run_report()`.

### `_handle_rerun_failed_only(package_root, previous_run) -> None`

Re-runs only failed tests from the previous run. Passes `rerun_failed_only=True`.

### `_load_previous_run(package_root) -> Any | None`

Loads the most recent run result from the package directory.

### `_store_run_report() -> None`

Delegates to `src.ui.shared.store_run_report()`.
