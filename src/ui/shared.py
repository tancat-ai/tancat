"""Shared UI constants and helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pytest_output_parser import RunResult
    from src.ui_pipeline import PipelineSessionState

# Whitelist of session state keys the pipeline is allowed to overwrite.
# Avoids Streamlit crash: "st.session_state.<key> cannot be modified after
# the widget with key <key> is instantiated".
PIPELINE_KEYS: set[str] = {
    "pipeline_results",
    "pipeline_skeleton",
    "pipeline_saved_path",
    "pipeline_manifest_path",
    "pipeline_error",
    "pipeline_unresolved",
    "pipeline_scraped_pages",
    "pipeline_urls",
    "pipeline_criteria",
    "pipeline_conditions",
    "pipeline_run_result",
    "pipeline_run_output",
    "pipeline_run_command",
    "pipeline_run_return_code",
    "pipeline_local_report",
    "pipeline_jira_report",
    "pipeline_html_report",
    "pipeline_local_report_path",
    "pipeline_jira_report_path",
    "pipeline_html_report_path",
}


def sync_pipeline_keys(session: PipelineSessionState) -> None:
    """Sync pipeline-managed keys from a session wrapper back to st.session_state.

    Uses PIPELINE_KEYS whitelist to avoid overwriting widget-owned keys.
    """
    import streamlit as st

    for key in PIPELINE_KEYS:
        value = session.get(key)
        if value is not None:
            st.session_state[key] = value


def store_run_report(
    *,
    criteria_text: str,
    generated_code: str,
    run_result: RunResult,
    saved_path: str,
) -> None:
    """Build and store the report bundle after a test run."""
    import streamlit as st

    from src.ui_pipeline import PipelineSessionState, build_report_bundle, store_report_bundle

    session = PipelineSessionState({str(k): v for k, v in st.session_state.items()})
    bundle = build_report_bundle(
        criteria_text=criteria_text,
        generated_code=generated_code,
        run_result=run_result,
        saved_path=saved_path,
    )
    store_report_bundle(bundle, session)
    sync_pipeline_keys(session)
