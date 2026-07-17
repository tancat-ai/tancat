"""Run results display, failure classification, and locator repair panel."""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from src.coverage_utils import build_coverage_analysis, build_coverage_display_rows
from src.failure_classifier import FailureCategory, classify_failure
from src.locator_repair import run_codegen_session
from src.pytest_output_parser import RunResult, TestResult
from src.ui.ui_results import _handle_run_tests


def _get_generated_code_for_coverage() -> str:
    """Get generated test code for coverage analysis.

    Prefers reading the actual saved test file(s) over session state,
    because pipeline_results may be stale (e.g., from a previous run
    or empty when loading a saved package).
    """
    # First try session state (normal flow — just generated)
    code = st.session_state.get("pipeline_results") or ""
    if code.strip():
        return code
    # Fallback: read from the saved test file(s)
    saved_path = st.session_state.get("pipeline_saved_path", "")
    if saved_path:
        return _read_test_code_from_path(saved_path)
    return ""


def _read_test_code_from_path(saved_path: str) -> str:
    """Read test code from a saved test file or package directory.

    Handles both flat mode (single .py file) and POM mode (directory with
    multiple test files).
    """
    path = Path(saved_path)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    if path.is_dir():
        # POM mode: concatenate all .py test files (skip __init__.py, conftest.py)
        parts: list[str] = []
        for py_file in sorted(path.rglob("*.py")):
            if py_file.name in ("__init__.py", "conftest.py"):
                continue
            parts.append(py_file.read_text(encoding="utf-8"))
        return "\n".join(parts)
    return ""


def _find_skip_line_number(source: str, test_name: str) -> int | None:
    """Find the line number (1-based) of the pytest.skip() in a test function."""
    lines = source.splitlines()
    in_test = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"def {test_name}("):
            in_test = True
            continue
        if in_test:
            if stripped.startswith("def ") and not stripped.startswith(f"def {test_name}("):
                break
            if "pytest.skip(" in stripped:
                return i + 1  # 1-based
    return None


def _render_skipped_tests_info(results: list[TestResult]) -> None:
    """Render information about skipped tests, showing why they were skipped."""
    skipped = [r for r in results if r.status == "skipped"]
    if not skipped:
        return

    st.divider()
    st.subheader("⏭️ Skipped Tests")

    # Try to extract skip reasons from the test file source
    saved_path = st.session_state.get("pipeline_saved_path", "")
    skip_reasons: dict[str, str] = {}
    skip_lines: dict[str, int] = {}
    if saved_path:
        try:
            source = _read_test_code_from_path(saved_path)
            for test in skipped:
                # Find pytest.skip() inside this test function
                pattern = re.compile(
                    rf"def {re.escape(test.name)}\(.*?\).*?pytest\.skip\((.*?)\)",
                    re.DOTALL,
                )
                match = pattern.search(source)
                if match:
                    reason = match.group(1).strip().strip("'\"")
                    skip_reasons[test.name] = reason
                # Track line number too
                ln = _find_skip_line_number(source, test.name)
                if ln:
                    skip_lines[test.name] = ln
        except Exception:
            pass

    for test in skipped:
        reason = skip_reasons.get(test.name, "Unresolved placeholder — element could not be located on the page")
        is_unresolved = "unresolved" in reason.lower()
        with st.expander(f"⏭️ {test.name}", expanded=False):
            st.write(f"**Reason:** {reason}")
            if is_unresolved:
                st.info(
                    "This test contains steps that could not be mapped to elements on the page. "
                    "To fix this, you can:\n"
                    "1. Check that the target website matches the requirement description\n"
                    "2. Ensure the site is loaded correctly (check the base URL)\n"
                    "3. Re-run the pipeline with a more specific description for the unresolved steps"
                )
            if is_unresolved and saved_path:
                col1, col2 = st.columns([1, 4])
                with col1:
                    line_num = skip_lines.get(test.name, 1)
                    if st.button("🖱️ Capture Locator", key=f"fix_skip_{test.name}", type="primary"):
                        st.session_state.skip_repair_test_name = test.name
                        st.session_state.skip_repair_line = line_num
                        st.session_state.skip_repair_file = saved_path
                        st.session_state.skip_repair_status = "waiting"
                        st.rerun()


def _render_skip_repair_panel() -> None:
    """Render the skip repair panel — opens codegen and replaces pytest.skip() with a real action."""
    repair_status = st.session_state.get("skip_repair_status")
    if repair_status is None:
        return

    if repair_status == "waiting":
        _render_skip_repair_waiting()
    elif repair_status == "browser_opening":
        _render_skip_repair_capture()
    elif repair_status in ("patched", "error"):
        _render_skip_repair_result()


def _render_skip_repair_waiting() -> None:
    """Show explanation before opening the browser for skipped test fix."""
    test_name = st.session_state.get("skip_repair_test_name", "unknown")
    base_url = st.session_state.get("starting_url", "") or st.session_state.get("last_starting_url", "")
    st.divider()
    st.subheader("🖱️ Capture Locator for Skipped Test")

    st.write(f"**Test:** {test_name}")
    st.info(
        "The browser will open at the base URL. "
        "Click the element that was missing from the page. "
        "The `pytest.skip()` line will be replaced with the captured locator.\n\n"
        f"**Base URL:** {base_url}"
    )

    fix_col, cancel_col = st.columns([1, 1])
    with fix_col:
        if st.button("🌐 Open browser and click element", type="primary"):
            st.session_state.skip_repair_status = "browser_opening"
            st.rerun()
    with cancel_col:
        if st.button("Cancel"):
            st.session_state.skip_repair_status = None
            st.rerun()


def _render_skip_repair_capture() -> None:
    """Run codegen and capture the locator, then replace pytest.skip() in the test file."""
    base_url = st.session_state.get("starting_url", "") or st.session_state.get("last_starting_url", "")
    test_file = st.session_state.get("skip_repair_file", "")
    test_name = st.session_state.get("skip_repair_test_name", "")
    line_number = st.session_state.get("skip_repair_line", 1)

    if not base_url or not test_file or not test_name:
        st.session_state.skip_repair_status = "error"
        st.session_state.skip_repair_message = "❌ Missing base URL or test file path."
        st.rerun()

    with st.spinner(f"⏳ Browser is opening at `{base_url}` — click the element you want to use..."):
        replacement = run_codegen_session(base_url, timeout_seconds=120)

    if replacement:
        try:
            # Read the current source
            path = Path(test_file)
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
            line_idx = line_number - 1  # 0-based

            if line_idx >= len(lines):
                st.session_state.skip_repair_status = "error"
                st.session_state.skip_repair_message = f"❌ Line {line_number} does not exist in the test file."
                st.rerun()

            old_line = lines[line_idx]
            indent = " " * (len(old_line) - len(old_line.lstrip()))
            # Replace the pytest.skip() line with a capture locator click
            new_line = f"{indent}page.locator({replacement!r}).click()"
            lines[line_idx] = new_line
            path.write_text("\n".join(lines), encoding="utf-8")

            st.session_state.skip_repair_status = "patched"
            st.session_state.skip_repair_message = (
                f"✅ `pytest.skip()` replaced with `page.locator({replacement!r}).click()` "
                f"on line {line_number} of `{test_file}`.\n\n"
                "You may need to edit the action type (e.g. `.click()` → `.fill('value')`).\n"
                "Click **▶️ Run Generated Tests** to verify the fix."
            )
        except Exception as exc:
            st.session_state.skip_repair_status = "error"
            st.session_state.skip_repair_message = f"❌ Could not apply fix: {exc}"
    else:
        st.session_state.skip_repair_status = "error"
        st.session_state.skip_repair_message = "❌ No locator captured. The browser may have timed out or been closed."

    st.rerun()


def _render_skip_repair_result() -> None:
    """Show the skip repair result."""
    st.divider()
    st.subheader("🖱️ Capture Locator Result")

    message = st.session_state.get("skip_repair_message", "")
    status = st.session_state.get("skip_repair_status")

    if status == "patched":
        st.success(message)
        re_run_col, reset_col = st.columns([1, 1])
        with re_run_col:
            if st.button("▶️ Run Generated Tests", type="primary"):
                st.session_state.skip_repair_status = None
                _handle_run_tests()
        with reset_col:
            if st.button("Done"):
                st.session_state.skip_repair_status = None
                st.rerun()
    else:
        st.error(message)
        if st.button("Done"):
            st.session_state.skip_repair_status = None
            st.rerun()


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

        # Coverage table with runtime and evidence columns
        criteria_lines = [line.strip() for line in st.session_state.pipeline_criteria.splitlines() if line.strip()]
        # Prefer the actual saved test file(s) over session state —
        # pipeline_results may be stale (e.g., loaded from a different package).
        generated_code = _get_generated_code_for_coverage()
        coverage_analysis = build_coverage_analysis(criteria_lines, generated_code)
        coverage_rows = build_coverage_display_rows(coverage_analysis["requirements"], run_result.results)
        if coverage_rows:
            st.dataframe([row.to_dict() for row in coverage_rows], width="stretch", hide_index=True)

        # Failed tests repair section
        _render_failed_tests_repair(run_result.results)

        # Skipped tests info section
        _render_skipped_tests_info(run_result.results)

        # Repair panel (shown after user clicks repair button)
        _render_repair_panel()

        # Skip repair panel (shown after user clicks capture locator for skipped test)
        _render_skip_repair_panel()

        # Pytest output
        if st.session_state.get("pipeline_run_output"):
            with st.expander("Pytest Output", expanded=run_result.errors > 0):
                st.code(st.session_state.pipeline_run_output, language="text")

        # Download buttons
        from src.ui.ui_downloads import RenderDownloads

        RenderDownloads.render()


def _render_inline_evidence(run_result: RunResult) -> None:
    """Render evidence inline + link to the main Evidence Viewer tab."""
    from src.gantt_utils import safe_read_sidecar
    from src.report_utils import generate_annotated_journey

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

    # Sort sidecars to match run result order (using base test name — strip [param] suffix)
    sorted_sidecars: list[Path] = []
    for result in run_result.results:
        base_name = result.name.split("[")[0] if "[" in result.name else result.name
        for s in relevant_sidecars:
            sidecar_base = extract_test_name(s)
            if sidecar_base == base_name or sidecar_base.startswith(base_name) or base_name.startswith(sidecar_base):
                if s not in sorted_sidecars:
                    sorted_sidecars.append(s)

    # Also add any remaining sidecars not matched
    for s in relevant_sidecars:
        if s not in sorted_sidecars:
            sorted_sidecars.append(s)

    # Check if user clicked the 📸 button in the results table
    pre_selected = st.session_state.pop("_select_evidence_test", None)
    default_idx = 0
    if pre_selected:
        for i, s in enumerate(sorted_sidecars):
            if extract_test_name(s) == pre_selected:
                default_idx = i
                break

    # Build friendly labels for the selector
    sidecar_labels: list[str] = []
    for s in sorted_sidecars:
        data = safe_read_sidecar(s)
        if data is None:
            sidecar_labels.append(s.stem.replace("[chromium]", ""))
            continue
        test_info = data.get("test", {})
        if not isinstance(test_info, dict):
            test_info = {}
        status = str(test_info.get("status", "unknown"))
        label = s.stem.replace("[chromium]", "")
        condition_ref = str(test_info.get("condition_ref", ""))
        if condition_ref:
            label = f"{condition_ref} — {label}"
        icon = "✅" if status == "passed" else ("⏭️" if status == "skipped" else "❌")
        sidecar_labels.append(f"{icon} {label}")

    selected_idx = st.selectbox(
        "Select test to inspect",
        options=range(len(sorted_sidecars)),
        format_func=lambda i: sidecar_labels[i] if i < len(sidecar_labels) else "[unknown]",
        index=default_idx,
        key="inline_evidence_selector",
    )
    selected = sorted_sidecars[selected_idx]

    try:
        html = generate_annotated_journey(
            sidecar_path=selected,
            title=selected.stem,
            bug_report_mode=False,
        )
        import streamlit.components.v1 as components

        components.html(html, height=1100, scrolling=True)

        # Download button for plain-text bug report
        text_report = generate_annotated_journey(
            sidecar_path=selected,
            title=selected.stem,
            bug_report_mode=True,
        )
        filename = selected.stem.replace("[chromium]", "").strip()
        st.download_button(
            label="📥 Download Bug Report",
            data=text_report,
            file_name=f"{filename}_bug_report.txt",
            mime="text/plain",
            key="inline_download_bug_report",
        )
    except Exception as e:
        st.error(f"Failed to render evidence: {e}")


def _render_failed_tests_repair(results: list[TestResult]) -> None:
    """Render repair buttons for failed tests with locator issues."""
    failed_with_repair = []
    for result in results:
        if result.status == "failed" and result.error_message:
            detail = classify_failure(result.error_message)
            if detail.category in (FailureCategory.LOCATOR_TIMEOUT, FailureCategory.STRICT_VIOLATION):
                failed_with_repair.append((result, detail))

    if not failed_with_repair:
        return

    st.divider()
    st.subheader("🔧 Locator Repairs")

    for result, detail in failed_with_repair:
        locator_label = detail.raw_locator if detail.raw_locator else "unknown locator"
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{result.name}** — `{locator_label}`")
            if result.error_message:
                st.caption(result.error_message[:200] + ("..." if len(result.error_message) > 200 else ""))
        with col2:
            if st.button("Fix Locator", key=f"repair_{result.name}", type="primary"):
                st.session_state.repair_target = detail
                st.session_state.repair_status = "waiting"
                st.session_state.repair_test_name = result.name
                st.session_state.repair_test_file = result.file_path
                st.rerun()


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
    base_url = st.session_state.get("starting_url", "") or st.session_state.get("last_starting_url", "")
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
