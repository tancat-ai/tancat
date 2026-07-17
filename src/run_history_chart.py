"""Run History Chart — Clean Plotly Figure factory for test-suite health trends.

Consumes :class:`PersistedRunResult` objects from
:mod:`src.run_result_persistence` and produces a clean dual-axis chart
that tells one clear story: **how healthy is my test suite over time**.

Primary visual  → Pass Rate % line (color-coded by health threshold).
Secondary axis → Total Test Count bars (subtle, for volume context).
Hover tooltips → Full breakdown (passed/failed/skipped/errors).

Also provides ``build_chart_from_db()`` for direct SQLite-backed chart
building using SQL aggregation queries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import plotly.graph_objects as go

from src.run_result_persistence import PersistedRunResult, _get_db

# ---------------------------------------------------------------------------
# Colour palette — clean, minimal, green/amber/red for health
# ---------------------------------------------------------------------------

COLOR_PASS_GREEN = "#2ecc71"
COLOR_AMBER = "#f39c12"
COLOR_FAIL_RED = "#e74c3c"
COLOR_BAR_FILL = "#5b6abf"  # subtle slate-blue for total-test bars
COLOR_BAR_LINE = "#3f4a8a"
COLOR_LINE = COLOR_BAR_FILL  # pass-rate line matches the bar accent
COLOR_RANGE_100 = "rgba(39, 174, 96, 0.2)"  # transparent green for area fill
COLOR_GRID = "#eaeef2"
COLOR_TEXT = "#2c3e50"

# Health thresholds
THRESHOLD_GREEN = 90.0  # >= 90% → green markers
THRESHOLD_AMBER = 70.0  # >= 70% → amber markers
# below 70% → red markers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_run_id(run_id: str) -> datetime:
    """Best-effort parse of an ISO-8601 run_id into a datetime."""
    try:
        return datetime.fromisoformat(run_id)
    except ValueError, TypeError:
        return datetime.min


def _format_timestamp(dt: datetime) -> str:
    """Human-friendly timestamp for x-axis labels."""
    return dt.strftime("%Y-%m-%d\n%H:%M")


def _health_color(pass_rate: float) -> str:
    """Return marker colour based on pass-rate threshold."""
    if pass_rate >= THRESHOLD_GREEN:
        return COLOR_PASS_GREEN
    if pass_rate >= THRESHOLD_AMBER:
        return COLOR_AMBER
    return COLOR_FAIL_RED


def _health_label(pass_rate: float) -> str:
    """Short text description of health level."""
    if pass_rate >= THRESHOLD_GREEN:
        return "Healthy"
    if pass_rate >= THRESHOLD_AMBER:
        return "At Risk"
    return "Unhealthy"


# ---------------------------------------------------------------------------
# Public API — from PersistedRunResult list
# ---------------------------------------------------------------------------


def build_run_history_chart(
    runs: list[PersistedRunResult],
    include_flaky_markers: bool = True,
) -> go.Figure:
    """Build a clean pass-rate trend chart with test-count volume bars.

    X-axis: run timestamp (chronological, oldest-first).
    Left Y-axis: Pass Rate % (line with health-coloured markers).
    Right Y-axis: Total Test Count (subtle bars for volume context).

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
        fig.update_layout(title="Test Suite Health Trend", height=300)
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

    # --- Build data arrays -------------------------------------------------
    labels = [_format_timestamp(_parse_run_id(r.run_id)) for r in sorted_runs]
    total_counts = [r.passed + r.failed + r.skipped + r.errors for r in sorted_runs]

    pass_rates: list[float] = []
    pass_details: list[str] = []
    for r in sorted_runs:
        total = r.passed + r.failed + r.errors
        if total > 0:
            rate = round(r.passed / total * 100, 1)
        else:
            rate = 0.0
        pass_rates.append(rate)
        pass_details.append(
            f"✅ Passed: {r.passed}  ❌ Failed: {r.failed}  ⏭️ Skipped: {r.skipped}  ⚠️ Errors: {r.errors}"
        )

    # Marker colours per run
    marker_colors = [_health_color(pr) for pr in pass_rates]
    health_labels = [_health_label(pr) for pr in pass_rates]

    # --- Build figure ------------------------------------------------------
    fig = go.Figure()

    # -- Total Test Count bars (right axis) --
    fig.add_trace(
        go.Bar(
            name="Total Tests",
            x=labels,
            y=total_counts,
            marker_color=COLOR_BAR_FILL,
            marker_line_color=COLOR_BAR_LINE,
            marker_line_width=1,
            opacity=0.40,
            yaxis="y",
            hovertemplate=("<b>%{x}</b><br>Total Tests: %{y}<br><extra></extra>"),
        )
    )

    # -- Pass Rate % line (left axis) --
    fig.add_trace(
        go.Scatter(
            name="Pass Rate %",
            x=labels,
            y=pass_rates,
            mode="lines+markers",
            line={"color": COLOR_LINE, "width": 3},
            marker={
                "color": marker_colors,
                "size": 14,
                "line": {"color": "#ffffff", "width": 2},
                "symbol": "circle",
            },
            fill="tozeroy",
            fillcolor=COLOR_RANGE_100,
            yaxis="y2",
            hovertemplate=(
                "<b>%{x}</b><br>Pass Rate: <b>%{y}%</b> (%{customdata[0]})<br>%{customdata[1]}<br><extra></extra>"
            ),
            customdata=list(zip(health_labels, pass_details, strict=False)),
        )
    )

    # -- 100% reference line --
    fig.add_hline(
        y=100,
        line={"color": COLOR_PASS_GREEN, "width": 1, "dash": "dot"},
        yref="y2",
        opacity=0.5,
    )

    # -- Health threshold zone fills (behind bars) --
    # Add a light red zone for unhealthy (0-70) and amber zone (70-90)
    # Done via shapes rather than traces to keep legend clean
    for y0, y1, color, label in [
        (0, THRESHOLD_AMBER, "rgba(231,76,60,0.05)", "Unhealthy zone"),
        (THRESHOLD_AMBER, THRESHOLD_GREEN, "rgba(243,156,18,0.04)", "At-risk zone"),
    ]:
        fig.add_hrect(
            y0=y0,
            y1=y1,
            line_width=0,
            fillcolor=color,
            yref="y2",
            layer="below",
            name=label,
            showlegend=False,
        )

    # -- Flaky-test markers (subtle) --
    if include_flaky_markers and flaky_test_names:
        for i, run in enumerate(sorted_runs):
            run_flaky = any(t.name in flaky_test_names for t in run.results)
            if run_flaky:
                fig.add_annotation(
                    text="❗",
                    x=labels[i],
                    y=pass_rates[i],
                    yshift=14,
                    showarrow=False,
                    font={"size": 11, "color": "#e67e22"},
                    yref="y2",
                )

    # --- Layout ---
    fig.update_layout(
        title={
            "text": "Test Suite Health Trend",
            "font": {"size": 18, "color": COLOR_TEXT},
        },
        xaxis={
            "title": "Run Timestamp",
            "title_font": {"size": 12},
            "tickfont": {"size": 10},
            "gridcolor": COLOR_GRID,
            "showgrid": True,
        },
        yaxis={
            "title": "Total Test Count",
            "title_font": {"size": 12},
            "tickfont": {"size": 10},
            "gridcolor": COLOR_GRID,
            "showgrid": True,
            "side": "left",
        },
        yaxis2={
            "title": "Pass Rate (%)",
            "title_font": {"size": 12, "color": COLOR_LINE},
            "tickfont": {"size": 10, "color": COLOR_LINE},
            "overlaying": "y",
            "side": "right",
            "range": [0, 105],
            "gridcolor": COLOR_GRID,
            "showgrid": False,
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 11},
        },
        hovermode="x unified",
        hoverlabel={"font": {"size": 12}},
        height=max(400, 250 + len(sorted_runs) * 20),
        margin={"t": 60, "b": 40, "l": 60, "r": 60},
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        barmode="overlay",  # bars sit behind the line
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
        fig.update_layout(title="Test Suite Health Trend", height=300)
        return fig

    # Build data arrays from SQL results
    labels: list[str] = []
    total_counts: list[int] = []
    pass_rates: list[float] = []
    pass_details: list[str] = []

    for row in stats_rows:
        labels.append(_format_timestamp(_parse_run_id(row["run_id"])))
        total_counts.append(row["passed"] + row["failed"] + row["skipped"] + row["errors"])
        pass_rates.append(row["pass_rate"])
        pass_details.append(
            f"✅ Passed: {row['passed']}  ❌ Failed: {row['failed']}  "
            f"⏭️ Skipped: {row['skipped']}  ⚠️ Errors: {row['errors']}"
        )

    marker_colors = [_health_color(pr) for pr in pass_rates]
    health_labels = [_health_label(pr) for pr in pass_rates]

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
            run_has_flaky = [stats_rows[i]["run_id"] in flaky_run_ids for i in range(len(stats_rows))]

    # --- Build figure ------------------------------------------------------
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Total Tests",
            x=labels,
            y=total_counts,
            marker_color=COLOR_BAR_FILL,
            marker_line_color=COLOR_BAR_LINE,
            marker_line_width=1,
            opacity=0.40,
            yaxis="y",
            hovertemplate=("<b>%{x}</b><br>Total Tests: %{y}<br><extra></extra>"),
        )
    )

    fig.add_trace(
        go.Scatter(
            name="Pass Rate %",
            x=labels,
            y=pass_rates,
            mode="lines+markers",
            line={"color": COLOR_LINE, "width": 3},
            marker={
                "color": marker_colors,
                "size": 14,
                "line": {"color": "#ffffff", "width": 2},
                "symbol": "circle",
            },
            fill="tozeroy",
            fillcolor=COLOR_RANGE_100,
            yaxis="y2",
            hovertemplate=(
                "<b>%{x}</b><br>Pass Rate: <b>%{y}%</b> (%{customdata[0]})<br>%{customdata[1]}<br><extra></extra>"
            ),
            customdata=list(zip(health_labels, pass_details, strict=False)),
        )
    )

    # -- 100% reference line --
    fig.add_hline(
        y=100,
        line={"color": COLOR_PASS_GREEN, "width": 1, "dash": "dot"},
        yref="y2",
        opacity=0.5,
    )

    # -- Health threshold zones --
    for y0, y1, color in [
        (0, THRESHOLD_AMBER, "rgba(231,76,60,0.05)"),
        (THRESHOLD_AMBER, THRESHOLD_GREEN, "rgba(243,156,18,0.04)"),
    ]:
        fig.add_hrect(
            y0=y0,
            y1=y1,
            line_width=0,
            fillcolor=color,
            yref="y2",
            layer="below",
            showlegend=False,
        )

    # Flaky-test markers
    if include_flaky_markers:
        for i, has_flaky in enumerate(run_has_flaky):
            if has_flaky:
                fig.add_annotation(
                    text="❗",
                    x=labels[i],
                    y=pass_rates[i],
                    yshift=14,
                    showarrow=False,
                    font={"size": 11, "color": "#e67e22"},
                    yref="y2",
                )

    fig.update_layout(
        title={
            "text": "Test Suite Health Trend",
            "font": {"size": 18, "color": COLOR_TEXT},
        },
        xaxis={
            "title": "Run Timestamp",
            "title_font": {"size": 12},
            "tickfont": {"size": 10},
            "gridcolor": COLOR_GRID,
            "showgrid": True,
        },
        yaxis={
            "title": "Total Test Count",
            "title_font": {"size": 12},
            "tickfont": {"size": 10},
            "gridcolor": COLOR_GRID,
            "showgrid": True,
            "side": "left",
        },
        yaxis2={
            "title": "Pass Rate (%)",
            "title_font": {"size": 12, "color": COLOR_LINE},
            "tickfont": {"size": 10, "color": COLOR_LINE},
            "overlaying": "y",
            "side": "right",
            "range": [0, 105],
            "gridcolor": COLOR_GRID,
            "showgrid": False,
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 11},
        },
        hovermode="x unified",
        hoverlabel={"font": {"size": 12}},
        height=max(400, 250 + len(stats_rows) * 20),
        margin={"t": 60, "b": 40, "l": 60, "r": 60},
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        barmode="overlay",
    )

    return fig
