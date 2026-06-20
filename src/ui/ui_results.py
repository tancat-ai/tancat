"""Results display panel and run handlers."""

from __future__ import annotations

import streamlit as st


class ResultsPanel:
    """Renders the pipeline results section."""

    @staticmethod
    def render_tabs(results: str, skeleton: str, saved_path: str, manifest_path: str) -> None:
        """Render the final code and skeleton tabs."""
        results_tab, skeleton_tab, scrape_tab = st.tabs(["Final Code", "Skeleton", "Scrape Summary"])

        with results_tab:
            st.code(results, language="python")
            if saved_path:
                st.success(f"Saved to: {saved_path}")
            if manifest_path:
                st.caption(f"Manifest: {manifest_path}")
            st.download_button(
                label="Download Final Test Script",
                data=results,
                file_name="generated_test.py",
                mime="text/x-python",
            )

        with skeleton_tab:
            st.code(skeleton, language="python")

        with scrape_tab:
            st.write("Pages scraped:")
            urls = st.session_state.get("pipeline_urls", [])
            scraped_pages = st.session_state.get("pipeline_scraped_pages", {})
            if urls:
                for url in urls:
                    element_count = len(scraped_pages.get(url, []))
                    st.write(f"- {url} ({element_count} elements)")
            else:
                st.write("- No URLs were available to scrape.")

            unresolved = st.session_state.get("pipeline_unresolved", [])
            if unresolved:
                st.warning("Some placeholders were unresolved and were converted into explicit pytest skips.")
                for unresolved_ph in unresolved:
                    st.code(unresolved_ph, language="python")

    @staticmethod
    def render_run_section() -> None:
        """Render the 'Run Generated Tests' buttons."""
        st.divider()
        st.subheader("Run Generated Tests")
        run_col, rerun_col = st.columns(2)
        saved_path = st.session_state.get("pipeline_saved_path", "")

        with run_col:
            if st.button("Run Generated Tests", disabled=not bool(saved_path)):
                _handle_run_tests()

        with rerun_col:
            previous_run_result = st.session_state.get("pipeline_run_result")
            rerun_disabled = not bool(saved_path) or previous_run_result is None
            if st.button("Re-run Failed Only", disabled=rerun_disabled):
                _handle_rerun_failed()


def _handle_run_tests() -> None:
    """Handle the 'Run Generated Tests' button click."""
    from src.pipeline_run_service import PipelineRunService

    try:
        with st.spinner("Running generated tests with pytest. This can take a couple of minutes..."):
            execution_result = PipelineRunService().run_saved_test(st.session_state.pipeline_saved_path)
            st.session_state.pipeline_run_result = execution_result.run_result
            st.session_state.pipeline_run_output = execution_result.display_output
            st.session_state.pipeline_run_command = " ".join(execution_result.command)
            st.session_state.pipeline_run_return_code = execution_result.return_code
            _store_run_report()
    except Exception as exc:
        st.session_state.pipeline_error = f"Failed to run generated tests: {exc}"


def _handle_rerun_failed() -> None:
    """Handle the 'Re-run Failed Only' button click."""
    from src.pipeline_run_service import PipelineRunService

    previous_run_result = st.session_state.pipeline_run_result
    try:
        with st.spinner("Re-running failed generated tests with pytest..."):
            execution_result = PipelineRunService().run_saved_test(
                st.session_state.pipeline_saved_path,
                rerun_failed_only=True,
                previous_run=previous_run_result,
            )
            st.session_state.pipeline_run_result = execution_result.run_result
            st.session_state.pipeline_run_output = execution_result.display_output
            st.session_state.pipeline_run_command = " ".join(execution_result.command)
            st.session_state.pipeline_run_return_code = execution_result.return_code
            _store_run_report()
    except Exception as exc:
        st.session_state.pipeline_error = f"Failed to rerun generated tests: {exc}"


def _store_run_report() -> None:
    """Build and store the report bundle after a test run."""
    from src.ui.shared import store_run_report as _shared_store

    _shared_store(
        criteria_text=st.session_state.pipeline_criteria,
        generated_code=st.session_state.pipeline_results,
        run_result=st.session_state.pipeline_run_result,
        saved_path=st.session_state.pipeline_saved_path,
    )
