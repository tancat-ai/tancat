"""Report download buttons."""

from __future__ import annotations

import streamlit as st


class RenderDownloads:
    """Render report download buttons."""

    @staticmethod
    def render() -> None:
        download_cols = st.columns(4)
        from src.ui_pipeline import safe_read_text

        download_cols[0].download_button(
            label="Download Manifest",
            data=safe_read_text(st.session_state.get("pipeline_manifest_path", "")),
            file_name="scrape_manifest.json",
            mime="application/json",
            disabled=not bool(st.session_state.get("pipeline_manifest_path")),
        )
        download_cols[1].download_button(
            label="Download Local Report",
            data=st.session_state.get("pipeline_local_report", ""),
            file_name="report_local.md",
            mime="text/markdown",
            disabled=not bool(st.session_state.get("pipeline_local_report")),
        )
        download_cols[2].download_button(
            label="Download Jira Report",
            data=st.session_state.get("pipeline_jira_report", ""),
            file_name="report_jira.md",
            mime="text/markdown",
            disabled=not bool(st.session_state.get("pipeline_jira_report")),
        )
        download_cols[3].download_button(
            label="Download HTML Report",
            data=st.session_state.get("pipeline_html_report", ""),
            file_name="report.html",
            mime="text/html",
            disabled=not bool(st.session_state.get("pipeline_html_report")),
        )

        # Report paths
        if st.session_state.get("pipeline_local_report_path"):
            st.caption(f"Local report: {st.session_state.pipeline_local_report_path}")
        if st.session_state.get("pipeline_jira_report_path"):
            st.caption(f"Jira report: {st.session_state.pipeline_jira_report_path}")
        if st.session_state.get("pipeline_html_report_path"):
            st.caption(f"HTML report: {st.session_state.pipeline_html_report_path}")
