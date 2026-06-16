"""Run History Chart — Plotly Figure factory for persisted test-run trends.

Pure Plotly figure builder with no Streamlit or CLI dependencies.
Consumes :class:`PersistedRunResult` objects from
:mod:`src.run_result_persistence` and produces stacked bar charts with
pass-rate line overlay and flaky-test markers.

Also provides ``build_chart_from_db()`` for direct SQLite-backed chart
building using SQL aggregation queries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import plotly.graph_objects as go

from src.run_result_persistence import PersistedRunResult, _get_db

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

COLOR_PASS = "#2ecc71"
COLOR_FAIL = "#e74c3c"
COLOR_SKIP = "#f1c40f"
COLOR_ERROR = "#95a5a6"
COLOR_LINE = "#2c3e50"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_run_id(run_id: str) -> datetime:
    """Best-effort parse of an ISO-8601 run_id into a datetime.

    Falls back to epoch if parsing fails (should not happen with well-formed
    data from :func:`persist_run_result`).
    """
    try:
        return datetime.fromisoformat(run_id)
    except ValueError, TypeError:
        return datetime.min


def _format_timestamp(dt: datetime) -> str:
    """Human-friendly timestamp for x-axis labels."""
    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Public API — from PersistedRunResult list
# ---------------------------------------------------------------------------


def build_run_history_chart(
    runs: list[PersistedRunResult],
    include_flaky_markers: bool = True,
) -> go.Figure:
    """Build a stacked bar chart with pass-rate line overlay.

    X-axis: run timestamp (chronological, oldest-first).
    Primary Y-axis: test count (stacked bars: pass/fail/skip/error).
    Secondary Y-axis: pass rate percentage (line).

    Args:
        runs: Sorted list of run results (oldest first).
        include_flaky_markers: Add ❗ annotations for runs containing
            tests that appear flaky across the full history.

    Returns:
        Plotly Figure ready for ``st.plotly_chart()`` or ``fig.show()``.
    """

    # --- Empty state -------------------------------------------------------
    if not runs:
        fig = go.Figure()
        fig.add_annotation(
            text="No run history available",
            showarrow=False,
            font={"size": 16},
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
        )
        fig.update_layout(title="Run History", height=300)
        return fig

    # --- Sort chronologically (defensive) ----------------------------------
    sorted_runs = sorted(runs, key=lambda r: _parse_run_id(r.run_id))

    # --- Compute flaky-set across all runs (for markers) -------------------
    flaky_test_names: set[str] = set()
    if include_flaky_markers and len(sorted_runs) >= 2:
        test_statuses: dict[str, list[str]] = {}
        for run in sorted_runs:
            for tr in run.results:
                test_statuses.setdefault(tr.name, []).append(tr.status)
        for name, statuses in test_statuses.items():
            has_pass = "passed" in statuses
            has_fail = any(s in ("failed", "error") for s in statuses)
            if has_pass and has_fail:
                flaky_test_names.add(name)

    # --- Determine which runs have flaky tests -----------------------------
    run_has_flaky: list[bool] = []
    for run in sorted_runs:
        if include_flaky_markers:
            run_has_flaky.append(any(t.name in flaky_test_names for t in run.results))
        else:
            run_has_flaky.append(False)

    # --- Build data arrays -------------------------------------------------
    labels = [_format_timestamp(_parse_run_id(r.run_id)) for r in sorted_runs]
    pass_counts = [r.passed for r in sorted_runs]
    fail_counts = [r.failed for r in sorted_runs]
    skip_counts = [r.skipped for r in sorted_runs]
    error_counts = [r.errors for r in sorted_runs]

    pass_rates: list[float] = []
    for r in sorted_runs:
        total = r.passed + r.failed + r.errors
        if total > 0:
            pass_rates.append(round(r.passed / total * 100, 1))
        else:
            pass_rates.append(0.0)

    # --- Build figure ------------------------------------------------------
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Passed",
            x=labels,
            y=pass_counts,
            marker_color=COLOR_PASS,
            hovertemplate="Run: %{x}<br>Passed: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Failed",
            x=labels,
            y=fail_counts,
            marker_color=COLOR_FAIL,
            hovertemplate="Run: %{x}<br>Failed: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Skipped",
            x=labels,
            y=skip_counts,
            marker_color=COLOR_SKIP,
            hovertemplate="Run: %{x}<br>Skipped: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Error",
            x=labels,
            y=error_counts,
            marker_color=COLOR_ERROR,
            hovertemplate="Run: %{x}<br>Error: %{y}<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            name="Pass Rate %",
            x=labels,
            y=pass_rates,
            mode="lines+markers",
            line={"color": COLOR_LINE, "width": 2},
            marker={"color": COLOR_LINE, "size": 8},
            yaxis="y2",
            hovertemplate="Run: %{x}<br>Pass Rate: %{y}%<extra></extra>",
        )
    )

    # Flaky-test markers
    if include_flaky_markers:
        max_bar_height = max((r.passed + r.failed + r.skipped + r.errors for r in sorted_runs), default=0)
        for i, has_flaky in enumerate(run_has_flaky):
            if has_flaky:
                fig.add_annotation(
                    text="❗", x=labels[i], y=max_bar_height + 1, yshift=8, showarrow=False, font={"size": 14}
                )

    fig.update_layout(
        title="Run History — Pass/Fail/Skip/Error Trends",
        barmode="stack",
        xaxis_title="Run Timestamp",
        yaxis={"title": "Test Count"},
        yaxis2={"title": "Pass Rate (%)", "overlaying": "y", "side": "right", "range": [0, 100]},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hovermode="x unified",
        height=max(400, 250 + len(sorted_runs) * 20),
    )

    return fig


# ---------------------------------------------------------------------------
# Public API — direct-from-DB chart builder
# ---------------------------------------------------------------------------


def build_chart_from_db(
    date_from: str | None = None,
    date_to: str | None = None,
    include_flaky_markers: bool = True,
) -> go.Figure:
    """Build run history chart directly from SQLite using SQL aggregation.

    Avoids loading all ``PersistedRunResult`` objects into memory — ideal
    for large datasets where only a date range is needed.

    Parameters
    ----------
    date_from / date_to :
        ISO-8601 date range boundaries (inclusive).
    include_flaky_markers :
        Add ❗ annotations for runs containing flaky tests (detected via SQL).

    Returns
    -------
    Plotly Figure ready for ``st.plotly_chart()`` or ``fig.show()``.
    """
    db = _get_db()

    stats_rows: list[dict[str, Any]] = db.get_run_stats_for_chart(date_from=date_from, date_to=date_to)

    if not stats_rows:
        fig = go.Figure()
        fig.add_annotation(
            text="No run history available",
            showarrow=False,
            font={"size": 16},
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
        )
        fig.update_layout(title="Run History", height=300)
        return fig

    # Build data arrays from SQL results
    labels: list[str] = []
    pass_counts: list[int] = []
    fail_counts: list[int] = []
    skip_counts: list[int] = []
    error_counts: list[int] = []
    pass_rates: list[float] = []

    for row in stats_rows:
        labels.append(_format_timestamp(_parse_run_id(row["run_id"])))
        pass_counts.append(row["passed"])
        fail_counts.append(row["failed"])
        skip_counts.append(row["skipped"])
        error_counts.append(row["errors"])
        pass_rates.append(row["pass_rate"])

    # Flaky test detection from SQL
    run_has_flaky: list[bool] = [False] * len(stats_rows)
    if include_flaky_markers and len(stats_rows) >= 2:
        flaky = db.get_flaky_tests(min_runs=2)
        flaky_test_names = {name for name, _ in flaky}

        if flaky_test_names:
            flaky_rows = db.query_test_history(
                test_name_pattern="%",
                date_from=date_from,
                date_to=date_to,
                include_flaky=True,
            )
            flaky_run_ids = {row["run_id"] for row in flaky_rows}
            run_has_flaky = [
                True if stats_rows[i]["run_id"] in flaky_run_ids else False for i in range(len(stats_rows))
            ]

    # --- Build figure ------------------------------------------------------
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Passed",
            x=labels,
            y=pass_counts,
            marker_color=COLOR_PASS,
            hovertemplate="Run: %{x}<br>Passed: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Failed",
            x=labels,
            y=fail_counts,
            marker_color=COLOR_FAIL,
            hovertemplate="Run: %{x}<br>Failed: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Skipped",
            x=labels,
            y=skip_counts,
            marker_color=COLOR_SKIP,
            hovertemplate="Run: %{x}<br>Skipped: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Error",
            x=labels,
            y=error_counts,
            marker_color=COLOR_ERROR,
            hovertemplate="Run: %{x}<br>Error: %{y}<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            name="Pass Rate %",
            x=labels,
            y=pass_rates,
            mode="lines+markers",
            line={"color": COLOR_LINE, "width": 2},
            marker={"color": COLOR_LINE, "size": 8},
            yaxis="y2",
            hovertemplate="Run: %{x}<br>Pass Rate: %{y}%<extra></extra>",
        )
    )

    # Flaky-test markers
    if include_flaky_markers:
        max_bar_height = max(
            (
                pc + fc + sc + ec
                for pc, fc, sc, ec in zip(pass_counts, fail_counts, skip_counts, error_counts, strict=True)
            ),
            default=0,
        )
        for i, has_flaky in enumerate(run_has_flaky):
            if has_flaky:
                fig.add_annotation(
                    text="❗", x=labels[i], y=max_bar_height + 1, yshift=8, showarrow=False, font={"size": 14}
                )

    fig.update_layout(
        title="Run History — Pass/Fail/Skip/Error Trends",
        barmode="stack",
        xaxis_title="Run Timestamp",
        yaxis={"title": "Test Count"},
        yaxis2={"title": "Pass Rate (%)", "overlaying": "y", "side": "right", "range": [0, 100]},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hovermode="x unified",
        height=max(400, 250 + len(stats_rows) * 20),
    )

    return fig
