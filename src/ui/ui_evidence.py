"""Evidence viewer — hierarchical dashboard, search, single test view, heatmap & Gantt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.evidence_export import export_csv, export_junit_xml, export_ndjson
from src.evidence_index import EvidenceIndex
from src.gantt_utils import (
    build_gantt_chart,
    build_gantt_summary_sentences,
    load_gantt_entries,
)
from src.heatmap_utils import build_confidence_heatmap, build_story_confidence
from src.report_utils import generate_annotated_journey
from src.storage import get_storage


def _format_indexed_at(iso_string: str) -> str:
    """Format an ISO-8601 timestamp — always show date + time."""
    if not iso_string:
        return "–"
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M")
    except ValueError, TypeError:
        return iso_string[:16] if len(iso_string) >= 16 else iso_string


def _short_package_name(raw: str) -> str:
    """Turn a long auto-generated package dir name into something readable.

    e.g. ``test_20260720_132120_as_a_shopper…`` → ``Jul 20, 13:21``
    """
    import re

    m = re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})", raw)
    if m:
        y, mo, d, h, mi = m.groups()
        from datetime import date

        month_abbr = date(int(y), int(mo), 1).strftime("%b")
        return f"{month_abbr} {int(d)}, {h}:{mi}"
    return raw[:30] + ("…" if len(raw) > 30 else "")


class EvidenceViewer:
    """Renders the redesigned evidence viewer section."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def render(self) -> None:
        from src.ui_pipeline import find_all_evidence_dirs, find_evidence_sidecars

        sidecars = find_evidence_sidecars(self.base_dir)
        evidence_dirs = find_all_evidence_dirs(self.base_dir)

        if not self.base_dir.exists() or not sidecars:
            st.info(
                "No evidence sidecars found yet. Run generated tests to produce "
                "`generated_tests/test_xxx/evidence/*.evidence.json`."
            )
            return

        top_tabs = st.tabs(["📊 Dashboard & Search", "🌡️ Coverage Heatmap", "⏱️ Gantt Timeline"])

        with top_tabs[0]:
            self._render_dashboard(evidence_dirs)
            st.divider()
            self._render_advanced_search(sidecars)

        with top_tabs[1]:
            self._render_coverage_heatmap(evidence_dirs)

        with top_tabs[2]:
            self._render_gantt_timeline(evidence_dirs)

    # ── Level 1: Dashboard ───────────────────────────────────────────────

    def _render_dashboard(self, evidence_dirs: list[Path]) -> None:
        from src.run_history_chart import build_run_history_chart
        from src.run_result_persistence import get_flaky_tests, load_all_run_results

        st.subheader("📊 Test Pack Overview")

        generated_tests_dir = get_storage().generated_tests_dir()
        runs = load_all_run_results(generated_tests_dir)
        if not runs:
            st.info("No run history available. Run tests first to see trends here.")
            return

        packages: list[str] = list({r.test_package for r in runs if r.test_package}) or ["All"]
        packages_sorted = sorted(packages)
        scope_options = ["All"] + packages_sorted if packages_sorted != ["All"] else ["All"]
        scope_labels = {p: _short_package_name(p) for p in scope_options}

        col_scope, col_metrics = st.columns([1, 3])
        with col_scope:
            scope = st.selectbox(
                "Test Pack",
                options=scope_options,
                format_func=lambda p: scope_labels.get(p, p),
                help="Filter the dashboard to a specific generated test package.",
                key="dashboard_scope",
            )

        filtered_runs = self._filter_runs_by_package(runs, scope)

        total_runs = len(filtered_runs)
        total_passed = sum(r.passed for r in filtered_runs)
        total_failed = sum(r.failed for r in filtered_runs)
        total_tests = total_passed + total_failed
        avg_pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0.0

        with col_metrics:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Runs", total_runs)
            m2.metric("Avg Pass Rate", f"{avg_pass_rate:.1f}%")
            m3.metric("Total Passed", total_passed)
            m4.metric("Total Failed", total_failed)

        col_trend, col_coverage = st.columns([2, 1])
        with col_trend:
            st.markdown("**Health Trend** — pass rate across runs over time")
            if total_runs > 1:
                chart = build_run_history_chart(filtered_runs, include_flaky_markers=False)
                chart.update_layout(height=280, margin={"l": 0, "r": 0, "t": 20, "b": 0})
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info(
                    "The trend chart appears once you have **2 or more** test runs recorded. "
                    "Each time you run the test suite, a new data point is added here."
                )

        with col_coverage:
            st.markdown("**Coverage** — story confidence at a glance")
            stories = build_story_confidence(
                evidence_dirs[0] if evidence_dirs else Path("."),
                test_plan_state=self._get_test_plan_state(),
            )
            if stories:
                confirmed = len([s for s in stories if s.level == "tester_confirmed"])
                gaps = len([s for s in stories if s.level == "gap_open_question"])
                unreviewed = len([s for s in stories if s.level == "ai_covered_unreviewed"])
                import plotly.graph_objects as go

                pie_labels = ["Confirmed", "Gaps/Failures", "Unreviewed"]
                pie_values = [confirmed, gaps, unreviewed]
                pie_colors = ["#10b981", "#ef4444", "#94a3b8"]
                fig = go.Figure(
                    data=[
                        go.Pie(
                            labels=pie_labels,
                            values=pie_values,
                            marker_colors=pie_colors,
                            hole=0.6,
                            textinfo="percent",
                        )
                    ]
                )
                fig.update_layout(
                    margin={"t": 0, "b": 0, "l": 0, "r": 0},
                    height=280,
                    showlegend=True,
                    legend={"orientation": "h", "yanchor": "bottom", "y": -0.25, "xanchor": "center", "x": 0.5},
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No story coverage data yet.")

        flaky = get_flaky_tests(filtered_runs)
        if flaky:
            with st.expander(f"⚠️ Flaky Tests ({len(flaky)})", expanded=True):
                rows = []
                for test_name, counts in flaky:
                    p = counts.get("passed", 0)
                    f = counts.get("failed", 0)
                    t = p + f
                    rows.append(
                        {
                            "Test Name": test_name.replace("[chromium]", ""),
                            "Passed": p,
                            "Failed": f,
                            "Flakiness": f"{(f / t):.0%}" if t else "–",
                        }
                    )
                st.dataframe(rows, use_container_width=True, hide_index=True)

    # ── Level 2: Advanced Search ─────────────────────────────────────────

    def _render_advanced_search(self, sidecars: list[Path]) -> None:
        st.subheader("🔍 Search Tests")

        index = self._get_evidence_index_v2()
        filter_opts = index.get_filter_options()

        # Always-visible controls
        col_search, col_status, col_refresh = st.columns([3, 1, 1])
        with col_search:
            query = st.text_input(
                "Search (test name, step label, condition…)",
                key="search_query",
                placeholder="e.g.  cart  or  TC01.05",
            )
        with col_status:
            status_filter = st.selectbox(
                "Status",
                ["All"] + filter_opts.statuses,
                key="filter_status",
            )
        with col_refresh:
            st.markdown("<div style='padding-top:28px;'>", unsafe_allow_html=True)
            if st.button("🔄 Refresh", use_container_width=True, help="Re-index evidence files from disk"):
                index.build_or_refresh(force=True)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        # Less-used filters collapsed
        with st.expander("More filters & export"):
            f1, f2, f3 = st.columns(3)
            with f1:
                domain_filter = st.selectbox("Domain", ["All"] + filter_opts.domains, key="filter_domain")
            with f2:
                prefix_filter = st.selectbox(
                    "Condition Prefix", ["All"] + filter_opts.condition_prefixes, key="filter_prefix"
                )
            with f3:
                locator = st.text_input(
                    "Locator (e.g. .text-center, #submit)",
                    key="search_locator",
                    placeholder=".text-center",
                )

            st.markdown("**Export current results**")
            e1, e2, e3 = st.columns(3)
            with e1:
                csv_data = export_csv(
                    index,
                    query=query,
                    status=status_filter if status_filter != "All" else None,
                    url_domain=domain_filter if domain_filter != "All" else None,
                    condition_prefix=prefix_filter if prefix_filter != "All" else None,
                )
                st.download_button(
                    "📥 CSV", data=csv_data, file_name="evidence_export.csv", mime="text/csv", use_container_width=True
                )
            with e2:
                ndjson_data = export_ndjson(
                    index,
                    query=query,
                    status=status_filter if status_filter != "All" else None,
                    url_domain=domain_filter if domain_filter != "All" else None,
                    condition_prefix=prefix_filter if prefix_filter != "All" else None,
                )
                st.download_button(
                    "📥 NDJSON",
                    data=ndjson_data,
                    file_name="evidence_export.ndjson",
                    mime="application/x-ndjson",
                    use_container_width=True,
                )
            with e3:
                junit_data = export_junit_xml(
                    index,
                    query=query,
                    status=status_filter if status_filter != "All" else None,
                    url_domain=domain_filter if domain_filter != "All" else None,
                    condition_prefix=prefix_filter if prefix_filter != "All" else None,
                )
                st.download_button(
                    "📥 JUnit XML",
                    data=junit_data,
                    file_name="evidence_junit.xml",
                    mime="application/xml",
                    use_container_width=True,
                )

        results = index.search(
            query=query,
            status=status_filter if status_filter != "All" else None,
            url_domain=domain_filter if domain_filter != "All" else None,
            condition_prefix=prefix_filter if prefix_filter != "All" else None,
            locator=locator if locator else None,
            limit=200,
        )

        st.caption(f"{len(results)} of {filter_opts.total_indexed} tests indexed.")
        if not results:
            st.info("No evidence matches your search.")
            return

        df_data = []
        for i, r in enumerate(results):
            icon = "❌" if r.status == "failed" else "✅" if r.status == "passed" else "⏭️"
            df_data.append(
                {
                    "": icon,
                    "Test Name": r.test_name.replace("[chromium]", ""),
                    "Condition": r.condition_ref,
                    "Last Run": _format_indexed_at(r.indexed_at),
                    "Pack": _short_package_name(r.test_package),
                    "_idx": i,
                }
            )

        df = pd.DataFrame(df_data)
        st.markdown(
            "<small>👆 Click a <strong>checkbox</strong> on the left to open the detailed debug view below.</small>",
            unsafe_allow_html=True,
        )
        event = st.dataframe(
            df.drop(columns=["_idx"]),
            use_container_width=True,
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True,
            column_config={
                "": st.column_config.TextColumn(width="small"),
                "Condition": st.column_config.TextColumn(width="small"),
                "Last Run": st.column_config.TextColumn(width="small"),
                "Pack": st.column_config.TextColumn(width="medium"),
            },
        )

        selected_idx = None
        if event and event.get("selection") and event["selection"].get("rows"):
            selected_idx = int(df.iloc[event["selection"]["rows"][0]]["_idx"])

        if selected_idx is not None:
            selected = results[selected_idx]
            self._render_single_test_view(selected, index)

    # ── Level 3: Single Test View ────────────────────────────────────────

    def _render_single_test_view(self, selected_result: Any, index: EvidenceIndex) -> None:
        st.divider()
        clean_name = selected_result.test_name.replace("[chromium]", "").strip()
        st.subheader(f"🔎 {clean_name}")
        st.caption(
            f"**URL:** {selected_result.page_url}  "
            f"·  **Story:** {selected_result.story_ref}  "
            f"·  **Pack:** {_short_package_name(selected_result.test_package)}"
        )

        debug_tab, history_tab = st.tabs(["📋 Execution Detail", "📈 Run History"])

        sidecar_path = index.get_test_package_path(selected_result.sidecar_path)

        with debug_tab:
            if not sidecar_path.exists():
                st.warning(f"Sidecar file not found on disk: `{selected_result.sidecar_path}`")
            else:
                try:
                    html = generate_annotated_journey(
                        sidecar_path=sidecar_path,
                        title=clean_name,
                        bug_report_mode=False,
                    )
                    st.html(html)

                    # Single clear export button
                    text_report = generate_annotated_journey(
                        sidecar_path=sidecar_path,
                        title=clean_name,
                        bug_report_mode=True,
                    )
                    filename = clean_name.replace(" ", "_")
                    st.download_button(
                        label="📥 Download Bug Report (.txt) — ready to paste into Jira/email",
                        data=text_report,
                        file_name=f"{filename}_bug_report.txt",
                        mime="text/plain",
                        key="btn_download_bug",
                    )
                except Exception as e:
                    st.error(f"Failed to render evidence: {e}")

        with history_tab:
            self._render_test_run_history(selected_result.test_name)

    def _render_test_run_history(self, test_name: str) -> None:
        from src.run_result_persistence import load_all_run_results

        runs = load_all_run_results(get_storage().generated_tests_dir())
        history_data = []
        for run in runs:
            for test in run.results:
                if test.name == test_name:
                    history_data.append(
                        {
                            "Run Date": run.run_id,
                            "Status": test.status,
                            "Duration (s)": test.duration,
                            "Error": test.error_message or "",
                        }
                    )

        if not history_data:
            st.info("No historical data found. This test appears only in the current run.")
            return

        df = pd.DataFrame(history_data)
        df["Run Date"] = pd.to_datetime(df["Run Date"]).dt.strftime("%Y-%m-%d %H:%M")

        import plotly.express as px

        fig = px.bar(
            df,
            x="Run Date",
            y="Duration (s)",
            color="Status",
            color_discrete_map={
                "passed": "#10b981",
                "failed": "#ef4444",
                "skipped": "#94a3b8",
                "error": "#f97316",
            },
            title=f"Execution history — {test_name.replace('[chromium]', '').strip()}",
        )
        fig.update_layout(margin={"t": 40, "b": 0, "l": 0, "r": 0})
        st.plotly_chart(fig, use_container_width=True)

        st.caption("Full run log:")
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Coverage Heatmap tab ─────────────────────────────────────────────

    def _render_coverage_heatmap(self, evidence_dirs: list[Path]) -> None:
        st.subheader("🌡️ Coverage Heatmap")
        st.caption(
            "Each story's confidence level is based on how many of its acceptance criteria "
            "have been tested and whether those tests passed."
        )

        stories = build_story_confidence(
            evidence_dirs[0] if evidence_dirs else Path("."),
            test_plan_state=self._get_test_plan_state(),
        )
        if not stories:
            st.info("No heatmap data yet. Run generated tests to produce `.evidence.json` sidecars.")
            return

        total = len(stories)
        confirmed = len([s for s in stories if s.level == "tester_confirmed"])
        gaps = len([s for s in stories if s.level == "gap_open_question"])
        unreviewed = len([s for s in stories if s.level == "ai_covered_unreviewed"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Stories", total)
        m2.metric("✅ Confirmed", confirmed)
        m3.metric("❌ Gaps / Failures", gaps)
        m4.metric("🕐 Unreviewed", unreviewed)

        fig = build_confidence_heatmap(stories)
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Story detail table"):
            st.dataframe(
                [
                    {
                        "Story Ref": s.story_ref,
                        "Confidence": s.level,
                        "Passed": s.passed_conditions,
                        "Failed": s.failed_conditions,
                        "Skipped": s.skipped_conditions,
                    }
                    for s in stories
                ],
                use_container_width=True,
                hide_index=True,
            )

    # ── Gantt Timeline tab ───────────────────────────────────────────────

    def _render_gantt_timeline(self, evidence_dirs: list[Path]) -> None:
        st.subheader("⏱️ Gantt Timeline")
        st.caption(
            "Each bar represents one test condition. Width = duration. "
            "Hover for details. Use Grouping to re-arrange by condition type, sprint, or source."
        )

        if not evidence_dirs:
            st.info("No evidence data yet.")
            return

        entries = load_gantt_entries(evidence_dirs[0])
        if not entries:
            st.info("No Gantt data yet. Run generated tests to produce `.evidence.json` sidecars.")
            return

        col_group, col_summary = st.columns([1, 3])
        with col_group:
            group_mode = st.selectbox(
                "Group by",
                options=["condition_type", "sprint", "source"],
                key="gantt_group_mode",
                help="Re-arrange the chart rows by this attribute.",
            )
            fastest, slowest, coverage = build_gantt_summary_sentences(entries)
            st.markdown(f"- {fastest}")
            st.markdown(f"- {slowest}")
            st.markdown(f"- {coverage}")

        with col_summary:
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
            st.plotly_chart(fig, use_container_width=True)

        with st.expander("Raw timing data"):
            st.dataframe(
                sorted(
                    [
                        {
                            "Condition": e.condition_ref,
                            "Status": e.status,
                            "Duration (s)": round(e.duration_s, 2),
                            "Test Name": e.test_name.replace("[chromium]", ""),
                        }
                        for e in entries
                    ],
                    key=lambda r: float(r["Duration (s)"]),  # type: ignore[arg-type, return-value]
                    reverse=True,
                ),
                use_container_width=True,
                hide_index=True,
            )

    # ── Shared helpers ───────────────────────────────────────────────────

    @staticmethod
    @st.cache_resource
    def _get_evidence_index_v2() -> EvidenceIndex:
        """Return a cached EvidenceIndex, refreshed incrementally."""
        index = EvidenceIndex()
        index.build_or_refresh()
        return index

    @staticmethod
    def _get_test_plan_state() -> dict[str, list[str]] | None:
        if st.session_state.get("test_plan"):
            return {"confirmed_ids": list(st.session_state.test_plan.reviewed_ids)}
        return None

    def _filter_runs_by_package(self, runs: list, scope: str) -> list:
        if scope == "All":
            return runs
        return [r for r in runs if r.test_package == scope]
