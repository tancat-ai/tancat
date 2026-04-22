"""Utilities for building Gantt-style timelines from EvidenceTracker sidecars."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


@dataclass(frozen=True)
class GanttEntry:
    test_name: str
    condition_ref: str
    story_ref: str
    status: str
    duration_s: float


GroupingMode = Literal["condition_type", "sprint", "source"]


def safe_read_sidecar(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_gantt_entries(evidence_dir: Path) -> list[GanttEntry]:
    """Load all `.evidence.json` sidecars from a directory into typed entries."""
    if not evidence_dir.exists():
        return []

    entries: list[GanttEntry] = []
    for path in sorted(evidence_dir.glob("*.evidence.json")):
        sidecar = safe_read_sidecar(path)
        if not sidecar:
            continue
        test_block = sidecar.get("test", {})
        if not isinstance(test_block, dict):
            continue

        test_name = str(test_block.get("name", path.stem))
        condition_ref = str(test_block.get("condition_ref", "unknown"))
        story_ref = str(test_block.get("story_ref", "unknown"))
        status = str(test_block.get("status", "unknown"))
        duration_raw = test_block.get("duration_s", 0.0)
        try:
            duration_s = float(duration_raw)
        except Exception:
            duration_s = 0.0

        entries.append(
            GanttEntry(
                test_name=test_name,
                condition_ref=condition_ref,
                story_ref=story_ref,
                status=status,
                duration_s=duration_s,
            )
        )
    return entries


def build_gantt_summary_sentences(
    entries: list[GanttEntry], *, total_expected: int | None = None
) -> tuple[str, str, str]:
    """Return (fastest, slowest, coverage) summary sentences."""
    if not entries:
        return (
            "Fastest test: n/a (no evidence sidecars found).",
            "Slowest test: n/a (no evidence sidecars found).",
            "Automation coverage: n/a (no evidence sidecars found).",
        )

    fastest = min(entries, key=lambda e: e.duration_s)
    slowest = max(entries, key=lambda e: e.duration_s)

    fastest_sentence = f"Fastest test: {fastest.condition_ref} ({fastest.duration_s:.2f}s)."
    slowest_sentence = f"Slowest test: {slowest.condition_ref} ({slowest.duration_s:.2f}s)."

    if total_expected is None or total_expected <= 0:
        coverage_sentence = f"Automation coverage: {len(entries)} executed test(s) (total expected unknown)."
    else:
        pct = (len(entries) / total_expected) * 100
        coverage_sentence = f"Automation coverage: {len(entries)}/{total_expected} ({pct:.0f}%)."

    return fastest_sentence, slowest_sentence, coverage_sentence


def group_gantt_entries(
    entries: list[GanttEntry],
    mode: GroupingMode,
    *,
    condition_meta: dict[str, dict[str, str]] | None = None,
) -> dict[str, list[GanttEntry]]:
    """Group entries by a selected mode, using optional metadata where available.

    `condition_meta` is keyed by condition_ref, values may include:
    - type
    - sprint
    - source
    """
    grouped: dict[str, list[GanttEntry]] = {}
    for entry in entries:
        meta = (condition_meta or {}).get(entry.condition_ref, {})
        if mode == "condition_type":
            key = str(meta.get("type", "unknown"))
        elif mode == "sprint":
            key = str(meta.get("sprint", "unknown"))
        else:
            key = str(meta.get("source", "unknown"))
        grouped.setdefault(key, []).append(entry)

    # stable sorting within each group for consistent UI
    for key in list(grouped.keys()):
        grouped[key] = sorted(grouped[key], key=lambda e: (e.status, -e.duration_s, e.condition_ref))
    return grouped


def build_gantt_chart(
    entries: list[GanttEntry],
    grouping_mode: GroupingMode = "condition_type",
    condition_meta: dict[str, dict[str, str]] | None = None,
) -> go.Figure:
    """Build a Plotly Gantt chart from entries."""
    if not entries:
        fig = go.Figure()
        fig.update_layout(title="No Gantt data available")
        return fig

    # Group data
    grouped = group_gantt_entries(entries, grouping_mode, condition_meta=condition_meta)

    # Flatten grouped data for Plotly
    plot_data = []
    current_start = 0.0
    for group_name, group_entries in grouped.items():
        for entry in group_entries:
            plot_data.append(
                {
                    "Task": entry.condition_ref,
                    "Start": current_start,
                    "Finish": current_start + entry.duration_s,
                    "Duration_Numeric": entry.duration_s,
                    "Status": entry.status,
                    "Group": group_name,
                    "Duration": f"{entry.duration_s:.2f}s",
                    "Story": entry.story_ref,
                }
            )
            current_start += entry.duration_s

    df = pd.DataFrame(plot_data)

    # Color mapping
    colors = {
        "passed": "#28a745",
        "failed": "#dc3545",
        "skipped": "#ffc107",
        "pending": "#6c757d",
        "unknown": "#17a2b8",
    }

    # Use a horizontal bar chart instead of px.timeline to avoid date-casting issues
    # with relative numeric durations.
    fig = px.bar(
        df,
        x="Duration_Numeric",
        y="Task",
        base="Start",
        color="Status",
        orientation="h",
        hover_data=["Duration", "Group", "Story"],
        color_discrete_map=colors,
        category_orders={"Task": df["Task"].tolist()},
        title=f"Test Execution Timeline (Grouped by {grouping_mode.replace('_', ' ').title()})",
    )

    fig.update_layout(
        xaxis_title="Relative Execution Time (s)",
        yaxis_title="Test Condition",
        showlegend=True,
        height=min(800, 300 + (len(entries) * 25)),
    )

    return fig
