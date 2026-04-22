"""Coverage confidence heat map aggregation from EvidenceTracker sidecars."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

ConfidenceLevel = Literal[
    "tester_confirmed",
    "ai_covered_unreviewed",
    "partial_pending",
    "gap_open_question",
    "not_in_scope",
]


CONFIDENCE_COLORS: dict[ConfidenceLevel, str] = {
    "tester_confirmed": "#1D9E75",
    "ai_covered_unreviewed": "#9FE1CB",
    "partial_pending": "#FAC775",
    "gap_open_question": "#F09595",
    "not_in_scope": "var(--color-background-secondary)",
}


@dataclass(frozen=True)
class StoryConfidence:
    story_ref: str
    level: ConfidenceLevel
    color: str
    total_conditions_with_evidence: int
    passed_conditions: int
    failed_conditions: int
    skipped_conditions: int


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _extract_confirmed_ids(test_plan_state: dict[str, Any] | None, story_ref: str) -> set[str]:
    if not test_plan_state:
        return set()

    # Accept either a global `confirmed_ids` set/list, or mapping by story_ref.
    confirmed_any = test_plan_state.get("confirmed_ids")
    if isinstance(confirmed_any, (list, set, tuple)):
        return {str(x) for x in confirmed_any}

    confirmed_by_story = test_plan_state.get("confirmed_ids_by_story")
    if isinstance(confirmed_by_story, dict):
        raw = confirmed_by_story.get(story_ref, [])
        if isinstance(raw, (list, set, tuple)):
            return {str(x) for x in raw}

    return set()


def build_story_confidence(
    evidence_dir: Path,
    *,
    test_plan_state: dict[str, Any] | None = None,
) -> list[StoryConfidence]:
    """Aggregate evidence sidecars into a per-story confidence signal.

    This is intentionally conservative until AI-017 (Living Test Plan UI) is wired:
    - If any condition failed -> gap_open_question
    - Else if no sidecars for story -> partial_pending
    - Else if all recorded conditions confirmed in test_plan -> tester_confirmed
    - Else -> ai_covered_unreviewed
    """
    if not evidence_dir.exists():
        return []

    by_story: dict[str, list[dict[str, Any]]] = {}
    for path in evidence_dir.glob("*.evidence.json"):
        sidecar = _safe_read_json(path)
        if not sidecar:
            continue
        test_block = sidecar.get("test", {})
        if not isinstance(test_block, dict):
            continue
        story_ref = str(test_block.get("story_ref", "unknown"))
        by_story.setdefault(story_ref, []).append(sidecar)

    stories: list[StoryConfidence] = []
    for story_ref, sidecars in sorted(by_story.items(), key=lambda kv: kv[0]):
        passed = 0
        failed = 0
        skipped = 0
        condition_refs: set[str] = set()
        for sc in sidecars:
            test_block = sc.get("test", {})
            if not isinstance(test_block, dict):
                continue
            condition_refs.add(str(test_block.get("condition_ref", "unknown")))
            status = str(test_block.get("status", "unknown"))
            if status == "passed":
                passed += 1
            elif status == "skipped":
                skipped += 1
            elif status == "failed":
                failed += 1

        confirmed_ids = _extract_confirmed_ids(test_plan_state, story_ref)
        has_any = len(sidecars) > 0

        if failed > 0:
            level: ConfidenceLevel = "gap_open_question"
        elif not has_any:
            level = "partial_pending"
        else:
            # If we have a non-empty confirmed set and it covers all seen condition refs, treat as confirmed.
            if confirmed_ids and condition_refs.issubset(confirmed_ids):
                level = "tester_confirmed"
            else:
                level = "ai_covered_unreviewed"

        stories.append(
            StoryConfidence(
                story_ref=story_ref,
                level=level,
                color=CONFIDENCE_COLORS[level],
                total_conditions_with_evidence=len(sidecars),
                passed_conditions=passed,
                failed_conditions=failed,
                skipped_conditions=skipped,
            )
        )

    return stories


def build_confidence_heatmap(stories: list[StoryConfidence]) -> go.Figure:
    """Build a Plotly heatmap (treemap style) for story confidence."""
    if not stories:
        fig = go.Figure()
        fig.update_layout(title="No coverage data available")
        return fig

    plot_data = []
    for s in stories:
        plot_data.append(
            {
                "Story": s.story_ref,
                "Confidence": s.level.replace("_", " ").title(),
                "Color": s.color,
                "Value": 1,  # Equal sizing for now
                "Passed": s.passed_conditions,
                "Failed": s.failed_conditions,
                "Skipped": s.skipped_conditions,
                "Total": s.total_conditions_with_evidence,
            }
        )

    df = pd.DataFrame(plot_data)

    fig = px.treemap(
        df,
        path=["Confidence", "Story"],
        values="Value",
        color="Confidence",
        color_discrete_map={level.replace("_", " ").title(): color for level, color in CONFIDENCE_COLORS.items()},
        hover_data=["Passed", "Failed", "Skipped", "Total"],
        title="Coverage Confidence Heat Map",
    )

    fig.update_layout(
        margin={"t": 50, "l": 25, "r": 25, "b": 25},
        hoverlabel={"bgcolor": "white", "font_size": 14, "font_family": "Rockwell"},
    )

    # Add annotation explaining the map
    fig.add_annotation(
        text="<b>How to read:</b> Confidence is grouped by level. Larger blocks = more tests. Click to drill down.",
        xref="paper",
        yref="paper",
        x=0,
        y=1.05,
        showarrow=False,
        font={"size": 12, "color": "#666"},
        align="left",
    )
    return fig
