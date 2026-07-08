# `src/ui/shared.py` — Shared UI Constants and Helpers

## Purpose

Shared constants and helper functions for Streamlit UI modules. Manages session state key whitelisting to prevent Streamlit's "cannot be modified after widget instantiation" crash.

## Constants

### `PIPELINE_KEYS: set[str]`

Whitelist of session state keys the pipeline is allowed to overwrite. Includes all `pipeline_*` keys:
- `pipeline_results`, `pipeline_skeleton`, `pipeline_saved_path`, `pipeline_manifest_path`
- `pipeline_error`, `pipeline_unresolved`, `pipeline_scraped_pages`, `pipeline_urls`
- `pipeline_criteria`, `pipeline_conditions`
- `pipeline_run_result`, `pipeline_run_output`, `pipeline_run_command`, `pipeline_run_return_code`
- `pipeline_local_report`, `pipeline_jira_report`, `pipeline_html_report`
- `pipeline_local_report_path`, `pipeline_jira_report_path`, `pipeline_html_report_path`

## Functions

### `sync_pipeline_keys(session: PipelineSessionState) -> None`

Syncs pipeline-managed keys from a `PipelineSessionState` wrapper back to `st.session_state`. Uses the `PIPELINE_KEYS` whitelist to avoid overwriting widget-owned keys (which would crash Streamlit).

### `store_run_report(*, criteria_text, generated_code, run_result, saved_path) -> None`

Builds and stores the report bundle after a test run:
1. Persists `RunResult` to SQLite via `persist_run_result()`
2. Creates a `PipelineSessionState` from current `st.session_state`
3. Builds report bundle via `build_report_bundle()`
4. Stores bundle via `store_report_bundle()`
5. Syncs keys back to `st.session_state`
