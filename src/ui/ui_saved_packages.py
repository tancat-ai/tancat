"""Saved package loader — sidebar and main panel (AI-026)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import streamlit as st

from src.pytest_output_parser import RunResult
from src.storage import get_storage
from src.ui.shared import store_run_report


class SavedPackagePanel:
    """Renders the 'Load Saved Package' section in the sidebar."""

    def __init__(self) -> None:
        self._generated_tests_dir = get_storage().generated_tests_dir()

    def render_sidebar(self) -> None:
        from src.pipeline_artifact_manager import find_existing_packages
        from src.run_result_persistence import compute_run_history, get_flaky_tests, load_all_run_results

        st.sidebar.divider()
        st.sidebar.subheader("Saved Packages")

        packages = find_existing_packages(self._generated_tests_dir)

        if not packages:
            st.sidebar.info("No saved packages found in `generated_tests/`.")
            return

        labels: list[str] = []
        for pkg in packages:
            runs = pkg.run_results_count
            tests = len(pkg.generated_test_files)
            label = f"{pkg.package_name}\n  ({tests} tests, {runs} runs)"
            labels.append(label)

        selected_index = st.sidebar.selectbox(
            "Load package",
            options=range(len(labels)),
            format_func=lambda i: labels[i],
            key="saved_package_selector",
        )

        if st.sidebar.button("📂 Load Package", key="load_package_button"):
            chosen = packages[selected_index]
            st.session_state.loaded_package_manifest = chosen.to_dict()
            st.session_state.loaded_package_root = str(self._generated_tests_dir / chosen.package_name)

            package_root = self._generated_tests_dir / chosen.package_name
            all_runs = load_all_run_results(package_root)
            st.session_state.loaded_package_runs = [asdict(run_item) for run_item in all_runs]

            if all_runs:
                history = compute_run_history(all_runs)
                st.session_state.loaded_package_history = asdict(history)  # type: ignore[arg-type]
                flaky = get_flaky_tests(all_runs)
                st.session_state.loaded_package_flaky = [{"name": name, "counts": counts} for name, counts in flaky]
            else:
                st.session_state.loaded_package_history = None
                st.session_state.loaded_package_flaky = []

            st.rerun()

        loaded = st.session_state.get("loaded_package_manifest")
        if loaded:
            self._render_loaded_summary()

    def _render_loaded_summary(self) -> None:
        loaded = st.session_state.get("loaded_package_manifest")
        if not loaded:
            return

        st.sidebar.success(f"Loaded: {loaded['package_name']}")
        st.sidebar.caption(f"Created: {loaded.get('created_at', 'unknown')}")

        source_story = loaded.get("source_story", "N/A")
        if source_story and source_story != "unknown":
            st.sidebar.caption(f"Story: {source_story[:80]}...")

        starting_url = loaded.get("starting_url", "N/A")
        if starting_url and starting_url != "unknown":
            st.sidebar.caption(f"URL: {starting_url}")

        history = st.session_state.get("loaded_package_history")
        if history:
            st.sidebar.metric("Total Runs", history.get("total_runs", 0))
            st.sidebar.metric("Total Passed", history.get("total_passed", 0))
            st.sidebar.metric("Total Failed", history.get("total_failed", 0))

        flaky = st.session_state.get("loaded_package_flaky", [])
        if flaky:
            st.sidebar.warning(f"{len(flaky)} flaky test(s) detected")

        package_root = st.session_state.get("loaded_package_root", "")
        if package_root and Path(package_root).exists():
            if st.sidebar.button("▶️ Re-run Saved Suite", key="rerun_saved_package"):
                st.session_state.pipeline_saved_path = package_root
                st.rerun()

    def render_main_panel(self) -> bool:
        """Render detailed package info in the main column when a package is loaded."""
        loaded = st.session_state.get("loaded_package_manifest")
        if not loaded:
            return False

        st.divider()
        st.subheader(f"📦 Package: {loaded['package_name']}")

        meta_col1, meta_col2 = st.columns(2)
        with meta_col1:
            st.write(f"**Created:** {loaded.get('created_at', 'unknown')}")
            st.write(f"**Provider:** {loaded.get('provider', 'unknown')}")
            st.write(f"**Model:** {loaded.get('model', 'unknown')}")
        with meta_col2:
            st.write(f"**URL:** {loaded.get('starting_url', 'unknown')}")
            test_files = loaded.get("generated_test_files", [])
            page_files = loaded.get("page_object_files", [])
            st.write(f"**Test files:** {len(test_files)}")
            st.write(f"**Page objects:** {len(page_files)}")

        source_story = loaded.get("source_story", "")
        if source_story and source_story != "unknown":
            with st.expander("User Story"):
                st.markdown(source_story)

        with st.expander(f"Test Files ({len(test_files)})", expanded=False):
            for tf in test_files:
                st.code(tf, language="python")

        if page_files:
            with st.expander(f"Page Objects ({len(page_files)})", expanded=False):
                for pf in page_files:
                    st.code(pf, language="python")

        additional_urls = loaded.get("additional_urls", [])
        if additional_urls:
            with st.expander("Additional URLs"):
                for url in additional_urls:
                    st.write(f"- `{url}`")

        runs_data = st.session_state.get("loaded_package_runs", [])
        if runs_data:
            self._render_run_history(runs_data)

        flaky = st.session_state.get("loaded_package_flaky", [])
        if flaky:
            self._render_flaky_tests(flaky)

        reports = loaded.get("reports", [])
        if reports:
            with st.expander("Report Paths"):
                for report_path in reports:
                    st.write(f"- `{report_path}`")

        evidence_paths = loaded.get("evidence_paths", [])
        if evidence_paths:
            with st.expander("Evidence Paths"):
                for ev_path in evidence_paths:
                    st.write(f"- `{ev_path}`")

        st.divider()
        package_root = st.session_state.get("loaded_package_root", "")
        if package_root and Path(package_root).exists():
            run_col, rerun_col = st.columns(2)
            with run_col:
                if st.button("▶️ Run Saved Suite", key="main_rerun_saved", type="primary"):
                    self._handle_rerun_saved_suite(package_root)
            with rerun_col:
                previous_run = self._load_previous_run(package_root)
                if st.button(
                    "🔄 Re-run Failed Only",
                    key="main_rerun_failed_only",
                    disabled=previous_run is None,
                ):
                    self._handle_rerun_failed_only(package_root, previous_run)

        return True

    # -- private helpers --

    def _render_run_history(self, runs_data: list[dict]) -> None:
        with st.expander(f"Run History ({len(runs_data)})", expanded=len(runs_data) <= 5):
            rows = []
            for run in runs_data:
                rows.append(
                    {
                        "Run ID": run.get("run_id", "N/A"),
                        "Total": run.get("total", 0),
                        "Passed": run.get("passed", 0),
                        "Failed": run.get("failed", 0),
                        "Skipped": run.get("skipped", 0),
                        "Duration": f"{run.get('duration', 0):.1f}s",
                    }
                )
            st.dataframe(rows, width="stretch")

    def _render_flaky_tests(self, flaky: list[dict]) -> None:
        with st.expander(f"⚠️ Flaky Tests ({len(flaky)})", expanded=True):
            st.warning("The following tests have inconsistent pass/fail results across runs:")
            for item in flaky:
                name = item.get("name", "unknown")
                counts = item.get("counts", {})
                bar = (
                    f"✅ {counts.get('passed', 0)} passed, "
                    f"❌ {counts.get('failed', 0)} failed, "
                    f"⏭️ {counts.get('skipped', 0)} skipped"
                )
                st.write(f"- **{name}** — {bar}")

    def _handle_rerun_saved_suite(self, package_root: str) -> None:
        from src.pipeline_run_service import PipelineRunService

        st.session_state.pipeline_saved_path = package_root
        try:
            with st.spinner("Running saved test suite..."):
                execution_result = PipelineRunService().run_saved_test(package_root)
                st.session_state.pipeline_run_result = execution_result.run_result
                st.session_state.pipeline_run_output = execution_result.display_output
                st.session_state.pipeline_run_command = " ".join(execution_result.command)
                st.session_state.pipeline_run_return_code = execution_result.return_code
                self._store_run_report()
        except Exception as exc:
            st.session_state.pipeline_error = f"Failed to run saved suite: {exc}"
            st.rerun()

    def _handle_rerun_failed_only(self, package_root: str, previous_run: Any | None) -> None:
        from src.pipeline_run_service import PipelineRunService

        st.session_state.pipeline_saved_path = package_root
        previous = None
        if previous_run and hasattr(previous_run, "to_run_result"):
            previous = previous_run.to_run_result()

        try:
            with st.spinner("Re-running failed tests..."):
                execution_result = PipelineRunService().run_saved_test(
                    package_root,
                    rerun_failed_only=True,
                    previous_run=previous,
                )
                st.session_state.pipeline_run_result = execution_result.run_result
                st.session_state.pipeline_run_output = execution_result.display_output
                st.session_state.pipeline_run_command = " ".join(execution_result.command)
                st.session_state.pipeline_run_return_code = execution_result.return_code
                self._store_run_report()
        except Exception as exc:
            st.session_state.pipeline_error = f"Failed to rerun failed tests: {exc}"
            st.rerun()

    def _load_previous_run(self, package_root: str) -> Any | None:
        from src.run_result_persistence import load_all_run_results

        runs = load_all_run_results(Path(package_root))
        return runs[-1] if runs else None

    def _store_run_report(self) -> None:
        store_run_report(
            criteria_text=st.session_state.get("pipeline_criteria", ""),
            generated_code=st.session_state.get("pipeline_results", ""),
            run_result=st.session_state.get("pipeline_run_result") or RunResult(),
            saved_path=st.session_state.get("pipeline_saved_path", ""),
        )
