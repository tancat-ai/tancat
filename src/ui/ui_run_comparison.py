"""Run comparison view — pick two runs of a package and see per-test deltas."""

from __future__ import annotations

import re

import streamlit as st

from src.pipeline_artifact_manager import find_existing_packages
from src.run_result_persistence import PersistedRunResult, load_all_run_results
from src.storage import get_storage

_STATUS_ICON = {"passed": "✅", "failed": "❌", "skipped": "⏭️", "error": "💥"}


def _run_label(run: PersistedRunResult) -> str:
    """Human-readable run label from the ISO-8601 run_id."""
    ts = run.run_id
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})T?[\s_-]?(\d{2}):?(\d{2})", ts)
    if m:
        y, mo, d, h, mi = m.groups()
        return f"{mo}-{d} {h}:{mi} · {run.passed}✓ {run.failed}✗ {run.skipped}⏭ / {run.total}"
    return f"{ts[:16]} · {run.passed}✓ {run.failed}✗ / {run.total}"


def _delta_icon(sa: str, sb: str) -> str:
    if sa == sb:
        return "="
    if sb == "passed":
        return "⬆ fixed"
    if sa == "passed":
        return "⬇ regressed"
    return "↔ changed"


class RunComparison:
    """Compare two runs of the same package, per test."""

    def __init__(self) -> None:
        self._generated_tests_dir = get_storage().generated_tests_dir()

    def render(self) -> None:
        packages = find_existing_packages(self._generated_tests_dir)
        if not packages:
            return

        st.divider()
        st.subheader("🔀 Compare Runs")
        st.caption("Pick a package and two runs — per-test status deltas are shown below.")

        pkg_names = [p.package_name for p in packages]
        selected = st.selectbox("Package", pkg_names, key="compare_package_selector")

        # load_all_run_results ignores its directory arg — filter by package.
        all_runs = load_all_run_results()
        runs = [r for r in all_runs if str(r.test_package or "").replace("\\", "/").endswith(f"/{selected}")]
        if len(runs) < 2:
            st.info(
                f"Need at least two persisted runs of this package to compare "
                f"(found {len(runs)}). Run the suite from Run & Fix to persist results."
            )
            return
        runs_sorted = sorted(runs, key=lambda r: r.run_id, reverse=True)
        labels = [_run_label(r) for r in runs_sorted]

        col_a, col_b = st.columns(2)
        with col_a:
            idx_a = st.selectbox(
                "Run A",
                range(len(labels)),
                format_func=lambda i: labels[i],
                index=min(1, len(labels) - 1),
                key="compare_run_a",
            )
        with col_b:
            idx_b = st.selectbox(
                "Run B",
                range(len(labels)),
                format_func=lambda i: labels[i],
                index=0,
                key="compare_run_b",
            )
        if idx_a == idx_b:
            st.warning("Run A and Run B are the same run — pick two different runs.")
            return
        run_a = runs_sorted[idx_a]
        run_b = runs_sorted[idx_b]

        status_a = {r.name: r.status for r in run_a.results}
        status_b = {r.name: r.status for r in run_b.results}
        all_tests = sorted(set(status_a) | set(status_b))

        rows: list[dict[str, str]] = []
        for name in all_tests:
            sa = status_a.get(name, "missing")
            sb = status_b.get(name, "missing")
            rows.append(
                {
                    "Test": name,
                    f"A · {_status_label(run_a)}": f"{_STATUS_ICON.get(sa, '⏳')} {sa}",
                    f"B · {_status_label(run_b)}": f"{_STATUS_ICON.get(sb, '⏳')} {sb}",
                    "Δ": _delta_icon(sa, sb),
                }
            )
        st.dataframe(rows, width="stretch", hide_index=True)

        changed = [r for r in rows if r["Δ"] != "="]
        fixed = sum(1 for r in rows if r["Δ"] == "⬆ fixed")
        regressed = sum(1 for r in rows if r["Δ"] == "⬇ regressed")
        c1, c2, c3 = st.columns(3)
        c1.metric("Changed", len(changed))
        c2.metric("Fixed", fixed)
        c3.metric("Regressed", regressed)


def _status_label(run: PersistedRunResult) -> str:
    return f"{run.passed}✓/{run.failed}✗"
