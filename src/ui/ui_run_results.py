"""Run results display, failure classification, and locator repair panel."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.coverage_utils import build_coverage_analysis, build_coverage_display_rows
from src.failure_classifier import FailureCategory, classify_failure
from src.gantt_utils import safe_read_sidecar
from src.locator_repair import run_codegen_session
from src.pytest_output_parser import RunResult, TestResult
from src.report_utils import generate_annotated_journey
from src.ui.ui_results import _handle_run_tests


class RunResultsDisplay:
    """Renders the test run results with failure classification and repair buttons."""

    @staticmethod
    def render(run_result: RunResult) -> None:
        """Display run metrics, coverage, results table with repair buttons, and downloads."""
        if st.session_state.get("pipeline_run_command"):
            st.caption(f"Command: {st.session_state.pipeline_run_command}")

        if run_result.errors > 0:
            st.error("Pytest hit a collection or import error before the generated tests could run.")

        metric_cols = st.columns(5)
        metric_cols[0].metric("Total", run_result.total)
        metric_cols[1].metric("Passed", run_result.passed)
        metric_cols[2].metric("Failed", run_result.failed)
        metric_cols[3].metric("Skipped", run_result.skipped)
        metric_cols[4].metric("Errors", run_result.errors)

        # Coverage table
        criteria_lines = [line.strip() for line in st.session_state.pipeline_criteria.splitlines() if line.strip()]
        coverage_analysis = build_coverage_analysis(criteria_lines, st.session_state.pipeline_results)
        coverage_rows = build_coverage_display_rows(coverage_analysis["requirements"], run_result.results)
        if coverage_rows:
            st.dataframe([row.to_dict() for row in coverage_rows], width="stretch")

        # Results table with repair buttons
        _render_results_table(run_result.results)

        # Repair panel (shown after user clicks repair button)
        _render_repair_panel()

        # Inline evidence viewer for just-run tests
        _render_inline_evidence(run_result)

        # Pytest output
        if st.session_state.get("pipeline_run_output"):
            with st.expander("Pytest Output", expanded=run_result.errors > 0):
                st.code(st.session_state.pipeline_run_output, language="text")

        # Download buttons
        from src.ui.ui_downloads import RenderDownloads

        RenderDownloads.render()


def _render_inline_evidence(run_result: RunResult) -> None:
    """Render inline evidence viewer for the tests that just ran."""
    st.divider()
    st.subheader("📸 Test Evidence")

    saved_path = st.session_state.get("pipeline_saved_path", "")
    if not saved_path:
        st.info("No test file path available.")
        return

    package_dir = Path(saved_path).parent
    evidence_dir = package_dir / "evidence"

    if not evidence_dir.exists():
        st.info(f"No evidence found at {evidence_dir}. Run tests to generate evidence.")
        return

    sidecars = sorted(evidence_dir.glob("*.evidence.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not sidecars:
        st.info("No evidence sidecars found for this test run.")
        return

    # Filter sidecars to only those for tests that just ran
    test_names = {result.name for result in run_result.results}

    def extract_test_name(s: Path) -> str:
        name = s.name
        if name.endswith(".evidence.json"):
            name = name[:-14]
        return name.split("[")[0]

    relevant_sidecars = [s for s in sidecars if extract_test_name(s) in test_names]

    if not relevant_sidecars:
        st.info("No evidence found for the tests that just ran.")
        return

    selected_sidecar = st.selectbox(
        "Select test evidence",
        options=relevant_sidecars,
        format_func=lambda p: p.stem,
    )

    if selected_sidecar:
        view_mode = st.selectbox(
            "View mode",
            options=["annotated", "heatmap", "clean"],
            index=0,
            help="annotated = numbered steps; heatmap = density rings; clean = screenshot only.",
        )
        try:
            html = generate_annotated_journey(
                sidecar_path=selected_sidecar,
                view_mode=view_mode,  # type: ignore[arg-type]
                title=selected_sidecar.stem,
            )
            components.html(html, height=900, scrolling=True)

            # Show sidecar details
            sidecar_data = safe_read_sidecar(selected_sidecar)
            if sidecar_data:
                st.divider()
                with st.expander("Step Details"):
                    for step in sidecar_data.get("steps", []):
                        status_icon = "✅" if step.get("result", {}).get("status") == "passed" else "❌"
                        st.write(f"- {status_icon} **{step.get('type').upper()}**: {step.get('label')}")
                        if step.get("result", {}).get("error"):
                            st.error(step.get("result", {}).get("error"))
        except Exception as e:
            st.error(f"Failed to render evidence: {e}")


def _render_results_table(results: list[TestResult]) -> None:
    """Render per-test results as a table with repair buttons for locator failures."""
    for result in results:
        status_icon = "✅" if result.status == "passed" else ("❌" if result.status == "failed" else "⏭️")
        row_col1, row_col2, row_col3 = st.columns([0.05, 3, 0.5])

        with row_col1:
            st.write(status_icon)
        with row_col2:
            st.write(f"**{result.name}**")
            if result.error_message:
                st.caption(result.error_message[:200] + ("..." if len(result.error_message) > 200 else ""))
        with row_col3:
            st.caption(f"{result.duration:.2f}s")

        # AI-023: Show repair button for locator failures
        if result.status == "failed" and result.error_message:
            detail = classify_failure(result.error_message)
            if detail.category in (FailureCategory.LOCATOR_TIMEOUT, FailureCategory.STRICT_VIOLATION):
                locator_label = detail.raw_locator if detail.raw_locator else "unknown locator"
                if st.button(
                    f"🔧 Fix locator: `{locator_label}`",
                    key=f"repair_{result.name}",
                    help="Open a browser to click the correct element",
                ):
                    st.session_state.repair_target = detail
                    st.session_state.repair_status = "waiting"
                    st.session_state.repair_test_name = result.name
                    st.session_state.repair_test_file = result.file_path
                    st.rerun()
            elif detail.category == FailureCategory.ASSERTION_FAILURE:
                st.caption("ℹ️ Assertion failure — the element was found but page content was unexpected.")
            elif detail.category == FailureCategory.NAVIGATION_ERROR:
                st.caption("ℹ️ Navigation error — check the URL and network connectivity.")


def _render_repair_panel() -> None:
    """Render the locator repair panel when in repair mode."""
    repair_status = st.session_state.get("repair_status")

    if repair_status == "waiting":
        _render_repair_waiting_panel()
    elif repair_status == "browser_requested":
        _render_repair_browser_session()
    elif repair_status in ("patched", "error"):
        _render_repair_result_panel()


def _render_repair_waiting_panel() -> None:
    """Show the 'waiting' repair panel with explanation and action buttons."""
    detail = st.session_state.get("repair_target")
    test_file = st.session_state.get("repair_test_file", "unknown")

    st.divider()
    st.subheader("🔧 Locator Repair Mode")

    locator_label = detail.raw_locator if detail and detail.raw_locator else "unknown"
    st.write(f"**Failed locator:** `{locator_label}`")
    st.write(f"**Test file:** `{test_file}`")
    st.write(f"**Error:** {detail.error_message[:300] if detail else 'Unknown'}")

    st.info(
        "The browser will open at the page where this test got stuck. "
        "Click the element you want to use as the locator. "
        "The test file will be updated automatically."
    )

    fix_col, cancel_col = st.columns([1, 1])
    with fix_col:
        if st.button("🌐 Open browser and fix locator", type="primary"):
            st.session_state.repair_status = "browser_requested"
            st.rerun()
    with cancel_col:
        if st.button("Cancel"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            st.rerun()


def _render_repair_browser_session() -> None:
    """Run the headed browser codegen session and apply the patch."""
    from src.locator_repair import LocatorPatch, apply_patch_to_file

    detail = st.session_state.get("repair_target")
    base_url = st.session_state.get("base_url", "")
    failure_url = detail.failure_url if detail and detail.failure_url else base_url

    if not failure_url:
        st.session_state.repair_status = "error"
        st.session_state.repair_message = "❌ No URL available for browser session."
        st.rerun()

    with st.spinner(f"⏳ Browser is opening at `{failure_url}` — click the element you want to use..."):
        replacement = run_codegen_session(failure_url, timeout_seconds=120)

    if replacement:
        patch = LocatorPatch(
            original_locator=detail.raw_locator if detail and detail.raw_locator else "",
            repaired_locator=replacement,
            line_number=detail.line_number if detail and detail.line_number else 1,
            test_file=st.session_state.get("repair_test_file", st.session_state.get("pipeline_saved_path", "")),
        )
        try:
            apply_patch_to_file(patch)
            st.session_state.repair_status = "patched"
            st.session_state.repair_message = (
                f"✅ Locator patched: `{replacement}`\n"
                f"Changed line(s) in `{patch.test_file}`\n"
                "Click **▶️ Run Generated Tests** to verify the fix."
            )
        except Exception as exc:
            st.session_state.repair_status = "error"
            st.session_state.repair_message = f"❌ Could not patch: {exc}"
    else:
        st.session_state.repair_status = "error"
        st.session_state.repair_message = "❌ No locator captured. The browser may have timed out or been closed."

    st.rerun()


def _render_repair_result_panel() -> None:
    """Show the repair result (success or error) with actions."""
    st.divider()
    st.subheader("🔧 Locator Repair Result")

    message = st.session_state.get("repair_message", "")
    status = st.session_state.get("repair_status")

    if status == "patched":
        st.success(message)
    else:
        st.error(message)

    # Show updated test code if patched
    if status == "patched":
        test_file = st.session_state.get("repair_test_file", "")
        if test_file and Path(test_file).exists():
            with st.expander("Updated test file", expanded=True):
                st.code(Path(test_file).read_text(encoding="utf-8"), language="python")

    re_run_col, reset_col = st.columns([1, 1])
    with re_run_col:
        if st.button("▶️ Run Generated Tests", disabled=(status != "patched"), type="primary"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            _handle_run_tests()
    with reset_col:
        if st.button("Done"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            st.session_state.repair_message = None
            st.rerun()
