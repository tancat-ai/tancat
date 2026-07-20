"""Evidence viewer — annotated screenshots, Gantt, heatmaps, run history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.gantt_utils import (
    build_gantt_chart,
    build_gantt_summary_sentences,
    load_gantt_entries,
    safe_read_sidecar,
)
from src.heatmap_utils import build_confidence_heatmap, build_story_confidence
from src.report_utils import generate_annotated_journey, generate_suite_heatmap
from src.storage import get_storage


class EvidenceViewer:
    """Renders the evidence viewer section."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def render(self) -> None:
        st.divider()
        st.subheader("Evidence Viewer")

        from src.ui_pipeline import find_all_evidence_dirs, find_evidence_sidecars

        sidecars = find_evidence_sidecars(self.base_dir)
        evidence_dirs = find_all_evidence_dirs(self.base_dir)

        if not self.base_dir.exists() or not sidecars:
            st.info(
                "No evidence sidecars found yet. Run generated tests to produce "
                "`generated_tests/test_xxx/evidence/*.evidence.json`."
            )
            return

        evidence_tabs = st.tabs(["Debug & Export", "Gantt Timeline", "Coverage Heat Map", "Run History"])

        with evidence_tabs[0]:
            self._render_debug_export(sidecars)

        with evidence_tabs[1]:
            self._render_gantt_timeline(evidence_dirs)

        with evidence_tabs[2]:
            self._render_coverage_heatmap(evidence_dirs)

        with evidence_tabs[3]:
            self._render_run_history()

        st.divider()
        self._render_suite_heatmap(sidecars, evidence_dirs)

    def _render_debug_export(self, sidecars: list[Path]) -> None:
        """Render the Debug & Export tab — focused on failure investigation."""
        st.subheader("🔍 Debug & Export")

        # Build a friendly list: test name + status + pass/fail count
        sidecar_options: list[dict[str, Any]] = []
        for sp in sidecars:
            data = safe_read_sidecar(sp)
            if data is None:
                sidecar_options.append({"path": sp, "label": sp.stem, "status": "unknown", "has_failure": False})
                continue
            test_info = data.get("test", {})
            if not isinstance(test_info, dict):
                test_info = {}
            status = str(test_info.get("status", "unknown"))
            # Check if any step failed
            has_failure = False
            for step in data.get("steps", []):
                if isinstance(step, dict):
                    result = step.get("result", {})
                    if isinstance(result, dict) and result.get("status") in ("failed", "error"):
                        has_failure = True
                        break

            label = sp.stem
            # Remove [chromium] suffix for readability
            label = label.replace("[chromium]", "")
            # Build a clean label showing order + status
            condition_ref = str(test_info.get("condition_ref", ""))
            if condition_ref:
                label = f"{condition_ref} — {label}"

            icon = "❌" if has_failure else "✅"
            label = f"{icon} {label}"

            sidecar_options.append({"path": sp, "label": label, "status": status, "has_failure": has_failure})

        if not sidecar_options:
            st.info("No evidence sidecars found.")
            return

        # Selector
        selected_idx = st.selectbox(
            "Select test evidence",
            options=range(len(sidecar_options)),
            format_func=lambda i: sidecar_options[i]["label"],
            key="debug_export_selector",
        )
        selected = sidecar_options[selected_idx]

        # Render the journey view
        try:
            html = generate_annotated_journey(
                sidecar_path=selected["path"],
                title=selected["path"].stem,
                bug_report_mode=False,
            )
            st.html(html)

            # Download button for plain-text bug report
            text_report = generate_annotated_journey(
                sidecar_path=selected["path"],
                title=selected["path"].stem,
                bug_report_mode=True,
            )
            filename = selected["path"].stem.replace("[chromium]", "").strip()
            st.download_button(
                label="📥 Download Bug Report (text)",
                data=text_report,
                file_name=f"{filename}_bug_report.txt",
                mime="text/plain",
                key="download_bug_report",
            )
        except Exception as e:
            st.error(f"Failed to render evidence: {e}")

    def _render_annotated_screenshot(self, sidecars: list[Path]) -> None:
        """Legacy entry point kept for backwards compatibility — delegates to _render_debug_export."""
        self._render_debug_export(sidecars)

    def _render_gantt_timeline(self, evidence_dirs: list[Path]) -> None:
        from src.ui_pipeline import find_sidecar_for_test

        entries = load_gantt_entries(evidence_dirs[0] if evidence_dirs else Path("."))
        if not entries:
            st.info("No Gantt data yet. Run generated tests to produce `.evidence.json` sidecars.")
            return

        col1, col2 = st.columns([1, 3])
        with col1:
            group_mode = st.selectbox(
                "Grouping Mode",
                options=["condition_type", "sprint", "source"],
                index=0,
                key="gantt_group_mode",
            )
            fastest, slowest, coverage = build_gantt_summary_sentences(entries)
            st.write(f"- {fastest}")
            st.write(f"- {slowest}")
            st.write(f"- {coverage}")

        with col2:
            # Extract condition metadata from test_plan if available
            condition_meta: dict[str, dict[str, str]] = {}
            if st.session_state.get("test_plan"):
                for c in st.session_state.test_plan.conditions:
                    condition_meta[c.id] = {
                        "type": c.type,
                        "sprint": getattr(st.session_state.test_plan, "sprint", "Backlog"),
                        "source": c.src,
                    }

            fig = build_gantt_chart(
                entries,
                grouping_mode=group_mode,  # type: ignore[arg-type]
                condition_meta=condition_meta,
            )
            st.plotly_chart(fig, width="stretch")

        st.divider()
        st.subheader("Test Execution Details")
        selected_test = st.selectbox(
            "Select test for details",
            options=sorted(entries, key=lambda e: e.condition_ref),
            format_func=lambda e: f"{e.condition_ref} ({e.status})",
        )

        if selected_test:
            sidecar_path = find_sidecar_for_test(self.base_dir, selected_test.test_name)
            if sidecar_path is None:
                st.warning(f"Sidecar not found for {selected_test.test_name}")
            else:
                sidecar = safe_read_sidecar(sidecar_path)
                if sidecar:
                    self._render_sidecar_details(sidecar)

        st.divider()
        st.subheader("Raw Execution Data")
        st.dataframe(
            [
                {
                    "condition_ref": e.condition_ref,
                    "story_ref": e.story_ref,
                    "status": e.status,
                    "duration_s": e.duration_s,
                    "test_name": e.test_name,
                }
                for e in sorted(entries, key=lambda e: (-e.duration_s, e.condition_ref))
            ],
            width="stretch",
        )

    def _render_sidecar_details(self, sidecar: dict[str, Any]) -> None:
        """Render detailed view of a single sidecar."""
        test_info = sidecar.get("test", {})
        col_a, colb = st.columns(2)
        with col_a:
            st.write(f"**Condition Ref:** {test_info.get('condition_ref')}")
            st.write(f"**Story Ref:** {test_info.get('story_ref')}")
            st.write(f"**Status:** {test_info.get('status')}")
        with colb:
            st.write(f"**Duration:** {test_info.get('duration_s')}s")
            st.write(f"**Test Name:** {test_info.get('name')}")

        st.write("**Steps:**")
        for step in sidecar.get("steps", []):
            status_icon = "✅" if step.get("result", {}).get("status") == "passed" else "❌"
            st.write(f"- {status_icon} **{step.get('type').upper()}**: {step.get('label')}")
            if step.get("result", {}).get("error"):
                st.error(step.get("result", {}).get("error"))

    def _render_coverage_heatmap(self, evidence_dirs: list[Path]) -> None:
        test_plan_state: dict[str, list[str]] | None = None
        if st.session_state.get("test_plan"):
            test_plan_state = {"confirmed_ids": list(st.session_state.test_plan.reviewed_ids)}

        stories = build_story_confidence(
            evidence_dirs[0] if evidence_dirs else Path("."),
            test_plan_state=test_plan_state,
        )
        if not stories:
            st.info("No heat map data yet. Run generated tests to produce `.evidence.json` sidecars.")
            return

        total_stories = len(stories)
        confirmed = len([s for s in stories if s.level == "tester_confirmed"])
        gaps = len([s for s in stories if s.level == "gap_open_question"])
        unreviewed = len([s for s in stories if s.level == "ai_covered_unreviewed"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Stories", total_stories)
        m2.metric("Tester Confirmed", confirmed)
        m3.metric("Gaps/Failures", gaps)
        m4.metric("Unreviewed", unreviewed)

        fig = build_confidence_heatmap(stories)
        st.plotly_chart(fig, width="stretch")

        st.divider()
        st.subheader("Story Confidence Details")
        st.dataframe(
            [
                {
                    "story_ref": s.story_ref,
                    "confidence": s.level,
                    "color": s.color,
                    "conditions_with_evidence": s.total_conditions_with_evidence,
                    "passed": s.passed_conditions,
                    "failed": s.failed_conditions,
                    "skipped": s.skipped_conditions,
                }
                for s in stories
            ],
            width="stretch",
        )

    def _render_suite_heatmap(self, sidecars: list[Path], evidence_dirs: list[Path]) -> None:
        st.subheader("Suite Heatmap (Coverage Overview)")

        url_options: set[str] = set()
        for sidecar_path in sidecars:
            try:
                sidecar_obj = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            steps = sidecar_obj.get("steps", [])
            if not isinstance(steps, list):
                continue
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if str(step.get("type", "")).lower() != "navigate":
                    continue
                val = str(step.get("value", "") or "").rstrip("/")
                if val.startswith("http"):
                    url_options.add(val)
        url_list = sorted(url_options)

        if not url_list:
            st.info("No navigated URLs found in sidecars yet.")
            return

        selected_url = st.selectbox("Select page URL", options=url_list)
        suite_html = generate_suite_heatmap(
            evidence_dir=evidence_dirs[0] if evidence_dirs else Path("."),
            page_url=selected_url,
        )
        st.html(suite_html)

    def _render_run_history(self) -> None:
        from src.run_history_chart import build_run_history_chart
        from src.run_result_persistence import (
            compare_latest_runs,
            compare_runs,
            get_flaky_tests,
            load_all_run_results,
        )

        st.subheader("Run History")

        generated_tests_dir = get_storage().generated_tests_dir()
        runs = load_all_run_results(generated_tests_dir)
        if not runs:
            st.info("No run history available. Run tests first to see trends here.")
            return

        packages: list[str] = list({r.test_package for r in runs if r.test_package}) or ["All"]
        packages_sorted = sorted(packages)
        scope_options = ["All"] + packages_sorted if packages_sorted != ["All"] else ["All"]
        scope = st.selectbox(
            "Scope",
            options=scope_options,
            key="run_history_scope",
        )
        filtered_runs = self._filter_runs_by_package(runs, scope)

        total_runs = len(filtered_runs)
        total_passed = sum(r.passed for r in filtered_runs)
        total_failed = sum(r.failed for r in filtered_runs)
        total_tests = total_passed + total_failed
        avg_pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0.0

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total Runs", total_runs)
        s2.metric("Avg Pass Rate", f"{avg_pass_rate:.1f}%")
        s3.metric("Total Passed", total_passed)
        s4.metric("Total Failed", total_failed)

        show_flaky = st.checkbox("Show Flaky Test Markers", value=True, key="run_history_show_flaky")
        chart = build_run_history_chart(filtered_runs, include_flaky_markers=show_flaky)
        st.plotly_chart(chart, width="stretch")

        flaky = get_flaky_tests(filtered_runs)
        flaky_count = len(flaky)
        with st.expander(f"Flaky Tests ({flaky_count})", expanded=flaky_count > 0):
            if flaky:
                flaky_rows = []
                for test_name, counts in flaky:
                    passed_c = counts.get("passed", 0)
                    failed_c = counts.get("failed", 0)
                    total_c = passed_c + failed_c
                    flakiness = (failed_c / total_c) if total_c > 0 else 0.0
                    flaky_rows.append(
                        {
                            "Test Name": test_name,
                            "Passed": passed_c,
                            "Failed": failed_c,
                            "Flakiness Score": f"{flakiness:.2f} ",
                        }
                    )
                st.dataframe(flaky_rows, width="stretch")
            else:
                st.success("No flaky tests detected ✅")

        if len(filtered_runs) >= 2:
            comparison = compare_runs(filtered_runs[-2], filtered_runs[-1])
            with st.expander("Last Run Comparison", expanded=True):
                self._render_run_comparison(comparison)
        else:
            comparison_none = compare_latest_runs(directory=None)
            if comparison_none:
                with st.expander("Last Run Comparison", expanded=True):
                    self._render_run_comparison(comparison_none)

    def _filter_runs_by_package(self, runs: list, scope: str) -> list:
        if scope == "All":
            return runs
        return [r for r in runs if r.test_package == scope]

    def _render_run_comparison(self, comparison: Any) -> None:
        improved = comparison.improved
        if improved:
            st.success(f"Improved ({len(improved)}):")
            for test in improved:
                st.write(f"- ✓ {test}")
        else:
            st.success("Improved: (none)")

        regressed = comparison.regressed
        if regressed:
            st.error(f"Regressed ({len(regressed)}):")
            for test in regressed:
                st.write(f"- ✗ {test}")
        else:
            st.info("Regressed: (none)")

        new_failures = comparison.new_failures
        if new_failures:
            st.warning(f"New Failures ({len(new_failures)}):")
            for test in new_failures:
                st.write(f"- ⚠ {test}")
        else:
            st.info("New Failures: (none)")
