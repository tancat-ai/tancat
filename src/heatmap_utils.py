"""Coverage confidence heat map aggregation from EvidenceTracker sidecars.

This module also houses the Tier 3 per-URL suite heatmap rendering logic
(moved from ``src/evidence_report.py``).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.evidence_image import embed_preview_data_uri
from src.report_builder import escape_html


def _normalise_url(url: str) -> str:
    """Normalise URLs for matching across redirects and trailing slashes."""
    from urllib.parse import urlsplit, urlunsplit

    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, netloc, path, "", ""))


# ---------------------------------------------------------------------------
# Constants (copied from evidence_report.py so heatmap_utils is self-contained)
# ---------------------------------------------------------------------------

_CONFIDENCE_COLORS: dict[ConfidenceLevel, str] = {  # noqa: SIM909 (exported alias below)
    "tester_confirmed": "#1D9E75",
    "ai_covered_unreviewed": "#9FE1CB",
    "partial_pending": "#FAC775",
    "gap_open_question": "#F09595",
    "not_in_scope": "var(--color-background-secondary)",
}

CONFIDENCE_COLORS: dict[ConfidenceLevel, str] = _CONFIDENCE_COLORS

# Tier 3 status colors
_STATUS_COLORS: dict[str, str] = {
    "passed": "#1D9E75",  # Green
    "partial_pass": "#FAC775",  # Yellow
    "failed": "#F09595",  # Red
    "skipped": "#6B7280",  # Gray
}

# Step type colors for heatmap overlay
_EVIDENCE_STEP_COLORS: dict[str, str] = {
    "navigate": "#993556",
    "fill": "#0F6E56",
    "click": "#185FA5",
    "assertion": "#854F0B",
}

ConfidenceLevel = Literal[
    "tester_confirmed",
    "ai_covered_unreviewed",
    "partial_pending",
    "gap_open_question",
    "not_in_scope",
]


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


def _safe_embed_image_data_uri(image_path: Path) -> str | None:
    if not image_path.exists():
        return None
    try:
        content = image_path.read_bytes()
        ext = image_path.suffix.lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext)
        if not mime_type:
            return None
        return f"data:{mime_type};base64,{base64.b64encode(content).decode('utf-8')}"
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Story confidence aggregation (existing)
# ---------------------------------------------------------------------------


def _extract_confirmed_ids(test_plan_state: dict[str, Any] | None, story_ref: str) -> set[str]:
    if not test_plan_state:
        return set()

    # Accept either a global `confirmed_ids` set/list, or mapping by story_ref.
    confirmed_any = test_plan_state.get("confirmed_ids")
    if isinstance(confirmed_any, list | set | tuple):
        return {str(x) for x in confirmed_any}

    confirmed_by_story = test_plan_state.get("confirmed_ids_by_story")
    if isinstance(confirmed_by_story, dict):
        raw = confirmed_by_story.get(story_ref, [])
        if isinstance(raw, list | set | tuple):
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

    # Map internal level names to plain-English labels for display
    LEVEL_LABELS: dict[str, str] = {
        "tester_confirmed": "✅ All Tests Passing",
        "ai_covered_unreviewed": "🟡 Covered (Not Yet Reviewed)",
        "partial_pending": "⏳ Partially Covered",
        "gap_open_question": "❌ Has Failures / Gaps",
        "not_in_scope": "Out of Scope",
    }

    plot_data: list[dict[str, Any]] = []
    for s in stories:
        label = LEVEL_LABELS.get(s.level, s.level)
        story_label = s.story_ref if s.story_ref != "unknown" else "(No story ref — tests run outside pipeline)"
        plot_data.append(
            {
                "Story": story_label,
                "Status": label,
                "Color": s.color,
                "Value": 1,
                "Passed": s.passed_conditions,
                "Failed": s.failed_conditions,
                "Skipped": s.skipped_conditions,
                "Total Tests": s.total_conditions_with_evidence,
            }
        )

    df = pd.DataFrame(plot_data)

    fig = px.treemap(
        df,
        path=["Status", "Story"],
        values="Value",
        color="Status",
        color_discrete_map={LEVEL_LABELS.get(level, level): color for level, color in CONFIDENCE_COLORS.items()},
        hover_data=["Passed", "Failed", "Skipped", "Total Tests"],
        title="Story Coverage Overview",
    )

    fig.update_layout(
        margin={"t": 50, "l": 25, "r": 25, "b": 25},
        hoverlabel={"bgcolor": "white", "font_size": 14, "font_family": "Rockwell"},
    )

    fig.add_annotation(
        text=(
            "<b>How to read:</b> Each coloured block = one user story. "
            "Green = all tests passing. Red = one or more failures. "
            "Click a block to drill into the story's tests."
        ),
        xref="paper",
        yref="paper",
        x=0,
        y=1.06,
        showarrow=False,
        font={"size": 12, "color": "#666"},
        align="left",
    )
    return fig


# ---------------------------------------------------------------------------
# Tier 3: Per-URL Suite Heatmap (moved from evidence_report.py)
# ---------------------------------------------------------------------------


def _extract_step_points_by_url(
    sidecar: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Return (points_by_url, frames_by_url) from one sidecar.

    Every step is attributed to the page it RAN on, not to the page it ended
    on: a click is measured before it runs, so a link that navigates would
    otherwise move its own marker to the destination page (B-105). The page a
    step ran on is the page the previous step left us on; a step that records
    its own measurement URL (``element.measured_url``) states it outright.

    ``frames_by_url`` lists the screenshots captured on each page, with the
    size of the document each captured, so a marker can be matched to the
    frame it was measured in.
    """
    steps = sidecar.get("steps", [])
    if not isinstance(steps, list):
        return {}, {}

    points_by_url: dict[str, list[dict[str, Any]]] = {}
    frames_by_url: dict[str, list[dict[str, Any]]] = {}

    page_block = sidecar.get("page", {})
    fallback_url = _normalise_url(str(page_block.get("url", ""))) if isinstance(page_block, dict) else ""

    current_segment_url = ""  # the last navigate's destination (legacy sidecars)
    prev_url = ""  # the page the previous step left us on

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type", "")).lower()
        raw_element = step.get("element")
        element: dict[str, Any] = raw_element if isinstance(raw_element, dict) else {}
        step_url = str(step.get("url") or "")
        shot = str(step.get("screenshot") or "")

        # The page this step RAN on.
        if "navigate" in step_type:
            page_url = _normalise_url(str(step.get("value") or step_url or current_segment_url))
            if page_url:
                current_segment_url = page_url
        else:
            measured_url = str(element.get("measured_url") or "")
            if measured_url:
                page_url = _normalise_url(measured_url)
            elif step_url:
                page_url = prev_url or _normalise_url(step_url)
            else:
                page_url = current_segment_url or fallback_url

        # The frame the step captured shows the page the step ENDED on.
        frame_url = _normalise_url(str(step.get("frame_url") or step_url or current_segment_url))
        if shot and frame_url:
            frames_by_url.setdefault(frame_url, []).append(
                {
                    "rel": shot,
                    "doc_width": step.get("frame_doc_width"),
                    "doc_height": step.get("frame_doc_height"),
                }
            )

        raw_result = step.get("result")
        result: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
        raw_run_count = result.get("run_count")
        run_count = int(raw_run_count) if isinstance(raw_run_count, (int, float)) else 1
        status = str(result.get("status") or "passed")
        if status not in ("passed", "partial_pass", "failed", "skipped"):
            status = "passed"

        if "navigate" in step_type:
            if page_url:
                points_by_url.setdefault(page_url, []).append(
                    {
                        "type": "navigate",
                        "x": 50.0,
                        "y": 50.0,
                        "run_count": run_count,
                        "status": status,
                        "locator": "",
                        "label": str(step.get("label") or ""),
                        "element_id": "",
                        "tag": "",
                        "arrival": True,
                        "doc_width": None,
                        "doc_height": None,
                    }
                )
            prev_url = frame_url or prev_url
            continue

        viewport_pct = element.get("viewport_pct")
        if isinstance(viewport_pct, dict) and page_url:
            x = viewport_pct.get("x")
            y = viewport_pct.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                points_by_url.setdefault(page_url, []).append(
                    {
                        "type": step_type,
                        "x": float(x),
                        "y": float(y),
                        "run_count": run_count,
                        "status": status,
                        "locator": str(step.get("locator") or ""),
                        "label": str(step.get("label") or ""),
                        "element_id": str(element.get("element_id") or ""),
                        "tag": str(element.get("tag") or ""),
                        "arrival": False,
                        "doc_width": element.get("doc_width"),
                        "doc_height": element.get("doc_height"),
                    }
                )

        prev_url = frame_url or prev_url

    return points_by_url, frames_by_url


def _point_matches_frame(point: dict[str, Any], frame: dict[str, Any]) -> bool:
    """Return True when *point* may be drawn on *frame*.

    A marker's percentage is only meaningful against the document it was
    measured in, so the document sizes must match. A sidecar or a frame that
    does not record its size cannot be checked — the match is accepted and
    reported as unverified, which is the legacy behaviour.
    """
    point_w = point.get("doc_width")
    point_h = point.get("doc_height")
    if not isinstance(point_w, (int, float)) or not isinstance(point_h, (int, float)):
        return True
    frame_w = frame.get("doc_width")
    frame_h = frame.get("doc_height")
    if not isinstance(frame_w, (int, float)) or not isinstance(frame_h, (int, float)):
        return True
    return int(point_w) == int(frame_w) and int(point_h) == int(frame_h)


def _dominant_status(status_counts: dict[str, int]) -> str:
    """Return the status that best describes an element.

    The most common status wins. On a tie the worse status wins: an element
    that failed once out of two attempts did fail.
    """
    if not status_counts:
        return "passed"
    severity = {"failed": 3, "partial_pass": 2, "skipped": 1, "passed": 0}
    return max(status_counts.items(), key=lambda kv: (kv[1], severity.get(kv[0], 0)))[0]


def list_evidence_urls(evidence_dir: Path) -> list[str]:
    """Return the page URLs that have evidence points, most-covered first.

    Each URL is one page of the product under test; the suite heatmap is
    rendered per URL, so this is the list of pages a report can show.
    """
    if not evidence_dir.exists():
        return []
    counts: dict[str, int] = {}
    for sidecar_path in evidence_dir.glob("*.evidence.json"):
        sidecar = _safe_read_json(sidecar_path)
        if not sidecar:
            continue
        points_by_url, _frames = _extract_step_points_by_url(sidecar)
        for url, points in points_by_url.items():
            counts[url] = counts.get(url, 0) + len(points)
    return [url for url, _count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def generate_suite_heatmap(
    *,
    evidence_dir: Path,
    page_url: str,
    max_width: int = 0,
    instance: str = "",
) -> str:
    """Render a suite-level heatmap for one page URL across all sidecars.

    Tier 3 redesign: Per-URL aggregation with status overlay and locator info.
    - Color-coded by test status: green (passed), yellow (partial_pass), red (failed)
    - Circle size proportional to test count
    - Tooltips show locator, element info, and test results
    - Filterable by test status

    Args:
        evidence_dir: The package's ``evidence/`` directory.
        page_url: The page to render.
        max_width: Cap on the embedded background width in pixels. Above 0 the
            background is embedded as a downscaled preview; 0 embeds the
            full-resolution capture.
        instance: Unique id for this heatmap inside the page. A report can
            carry one heatmap per page, and each heatmap's script must scope
            itself to its own block. Defaults to a hash of the page URL.
    """
    if not evidence_dir.exists():
        return "<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>Evidence directory not found.</div>"

    target_norm = _normalise_url(page_url)
    all_points: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []

    for sidecar_path in evidence_dir.glob("*.evidence.json"):
        sidecar = _safe_read_json(sidecar_path)
        if not sidecar:
            continue
        points_by_url, frames_by_url = _extract_step_points_by_url(sidecar)
        current_points = points_by_url.get(target_norm, [])
        if not current_points:
            continue

        all_points.extend(current_points)
        frames.extend(frames_by_url.get(target_norm, []))

    if not all_points:
        escaped = escape_html(page_url)
        return f"<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>No evidence points found for <code>{escaped}</code>.</div>"

    # A page arrival is evidence that the page was reached, not an element
    # hit: it carries no locator and must not merge into an element.
    element_points = [p for p in all_points if not p.get("arrival")]
    arrival_count = len(all_points) - len(element_points)

    # Draw the points on the frame of this page that most of them were
    # measured in. A percentage is only meaningful against the document it
    # came from, so a point measured on a different page layout is reported
    # rather than drawn on the wrong frame (B-105).
    chosen_frame: dict[str, Any] | None = None
    best_score = -1
    for frame in frames:
        score = sum(1 for point in element_points if _point_matches_frame(point, frame))
        if score > best_score:
            best_score = score
            chosen_frame = frame

    if chosen_frame is None:
        plotted = list(element_points)
    else:
        plotted = [point for point in element_points if _point_matches_frame(point, chosen_frame)]
    not_plotted = len(element_points) - len(plotted)

    # Pick the background image: the frame the points are drawn on.
    image_data_uri = None
    if chosen_frame is not None:
        background_rel = str(chosen_frame.get("rel") or "")
        image_path = (
            (evidence_dir.parent / background_rel).resolve()
            if background_rel.startswith("evidence/")
            else (evidence_dir / background_rel).resolve()
        )
        image_data_uri = _safe_embed_image_data_uri(image_path)
        if max_width > 0:
            preview_uri = embed_preview_data_uri(image_path, max_width=max_width)
            if preview_uri:
                image_data_uri = preview_uri

    # Aggregate per-element: group by (x, y) position and collect statuses
    # Elements within 2% of each other are considered the same element.
    # B-105: a point inside the tolerance MERGES into the element it matched.
    # The old code overwrote the matched element instead, so an element hit
    # by eight tests showed one hit and the status of the last hit only.
    ELEMENT_TOLERANCE = 2.0
    aggregated: dict[str, dict[str, Any]] = {}
    for point in plotted:
        key = f"{point['x']:.1f}_{point['y']:.1f}"
        # Check if this point is close to an existing element
        merged = False
        for agg_key, agg in aggregated.items():
            ax, ay = agg["x"], agg["y"]
            px, py = point["x"], point["y"]
            if abs(ax - px) < ELEMENT_TOLERANCE and abs(ay - py) < ELEMENT_TOLERANCE:
                # Merge into existing element
                key = agg_key
                merged = True
                break
        if not merged:
            aggregated[key] = {
                "x": point["x"],
                "y": point["y"],
                "statuses": [],
                "locators": set(),
                "labels": set(),
                "element_ids": set(),
                "tags": set(),
                "run_count": 0,
                "runs": 0,
            }
        aggregated[key]["statuses"].append(point.get("status", "passed"))
        if point.get("locator"):
            aggregated[key]["locators"].add(point["locator"])
        if point.get("label"):
            aggregated[key]["labels"].add(point["label"])
        if point.get("element_id"):
            aggregated[key]["element_ids"].add(point["element_id"])
        if point.get("tag"):
            aggregated[key]["tags"].add(point["tag"])
        aggregated[key]["run_count"] += 1
        aggregated[key]["runs"] += int(point.get("run_count") or 1)

    # Compute summary stats per element
    for _key, elem in aggregated.items():
        status_counts: dict[str, int] = {}
        for s in elem["statuses"]:
            status_counts[s] = status_counts.get(s, 0) + 1
        elem["total"] = len(elem["statuses"])
        elem["passed"] = status_counts.get("passed", 0)
        elem["failed"] = status_counts.get("failed", 0)
        elem["partial_pass"] = status_counts.get("partial_pass", 0)
        elem["skipped"] = status_counts.get("skipped", 0)
        # Dominant status (most common; the worse one wins a tie)
        elem["dominant_status"] = _dominant_status(status_counts)
        # Convert sets to lists for JSON serialization
        elem["locators"] = list(elem["locators"])[:3]  # Limit to 3
        elem["labels"] = list(elem["labels"])[:3]
        elem["element_ids"] = list(elem["element_ids"])
        elem["tags"] = list(elem["tags"])

    # Build aggregated data for JS
    aggregated_json = json.dumps(list(aggregated.values()))
    status_counts_overall: dict[str, int] = {}
    for point in plotted:
        s = point.get("status", "passed")
        status_counts_overall[s] = status_counts_overall.get(s, 0) + 1

    points_json = json.dumps(all_points)
    plotted_json = json.dumps(plotted)
    colors_json = json.dumps(_EVIDENCE_STEP_COLORS)
    status_colors_json = json.dumps(_STATUS_COLORS)
    safe_url = escape_html(page_url)
    instance = instance or hashlib.sha1(page_url.encode("utf-8")).hexdigest()[:10]
    bg_html = (
        f'<img class="suite-img" id="suite-img-{instance}" src="{image_data_uri}" alt="suite screenshot" style="display:block;width:100%;max-width:{max_width or 1100}px;height:auto;" />'
        if image_data_uri
        else '<div class="suite-img" id="suite-img-{instance}" style="width:100%;aspect-ratio:16/9;border-radius:8px;border:1px dashed #ddd;display:flex;align-items:center;justify-content:center;color:#666;">No screenshot available for this page. Rendering points only.</div>'
    )
    unplotted_html = (
        f"<span style='color:#b45309;font-weight:700;'>Not drawn: {not_plotted}</span>"
        f"<span style='color:#6b7280;'>(measured on a different page layout)</span>"
        if not_plotted
        else ""
    )
    arrival_html = f"<span style='color:#6b7280;'>Page arrivals: {arrival_count}</span>" if arrival_count else ""

    return f"""
<div class="suite-heatmap" id="suite-heat-{instance}" style="border:1px solid #e6e6e6;border-radius:10px;padding:14px;background:#fff;">
  <div style="font-weight:600;margin-bottom:10px;">Suite Heatmap — Per-URL Element Coverage</div>
  <div style="color:#6b7280;font-size:12px;margin:-6px 0 10px 0;">{safe_url}</div>

  <!-- Summary stats -->
  <div style="display:flex;gap:15px;margin-bottom:12px;font-size:13px;flex-wrap:wrap;align-items:center;">
    <span><strong>Total:</strong> {len(all_points)} evidence points ({len(plotted)} drawn on this frame)</span>
    <span style="color:{_STATUS_COLORS["passed"]};font-weight:700;">Passed: {status_counts_overall.get("passed", 0)}</span>
    <span style="color:{_STATUS_COLORS["partial_pass"]};font-weight:700;">Partial: {status_counts_overall.get("partial_pass", 0)}</span>
    <span style="color:{_STATUS_COLORS["failed"]};font-weight:700;">Failed: {status_counts_overall.get("failed", 0)}</span>
    <span style="color:{_STATUS_COLORS["skipped"]};font-weight:700;">Skipped: {status_counts_overall.get("skipped", 0)}</span>
    {arrival_html}
    {unplotted_html}
  </div>

  <!-- Filter buttons -->
  <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
    <button class="heatmap-filter-btn" data-filter="all" style="padding:4px 12px;border:1px solid #ddd;border-radius:16px;background:#fff;cursor:pointer;font-size:12px;">All</button>
    <button class="heatmap-filter-btn" data-filter="passed" style="padding:4px 12px;border:1px solid #1D9E75;border-radius:16px;background:#1D9E75;color:#fff;cursor:pointer;font-size:12px;">Passed</button>
    <button class="heatmap-filter-btn" data-filter="partial_pass" style="padding:4px 12px;border:1px solid #FAC775;border-radius:16px;background:#FAC775;color:#333;cursor:pointer;font-size:12px;">Partial</button>
    <button class="heatmap-filter-btn" data-filter="failed" style="padding:4px 12px;border:1px solid #F09595;border-radius:16px;background:#F09595;color:#333;cursor:pointer;font-size:12px;">Failed</button>
  </div>

  <div class="suite-wrap" id="suite-wrap-{instance}" style="position:relative;width:100%;max-width:{max_width or 1100}px;max-height:640px;overflow:auto;border:1px solid #eee;border-radius:8px;background:#fafafa;">
    {bg_html}
    <svg class="suite-svg" id="suite-svg-{instance}" style="position:absolute;left:0;top:0;pointer-events:none;z-index:5;"></svg>
  </div>

  <!-- Element details table -->
  <div id="element-details" style="margin-top:12px;border-top:1px solid #eee;padding-top:10px;">
    <div style="font-weight:600;margin-bottom:8px;">Element Details (click a circle to highlight)</div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead>
        <tr style="border-bottom:2px solid #eee;text-align:left;">
          <th style="padding:6px;">Position</th>
          <th style="padding:6px;">Element</th>
          <th style="padding:6px;">Locator</th>
          <th style="padding:6px;">Total Hits</th>
          <th style="padding:6px;">Passed</th>
          <th style="padding:6px;">Partial</th>
          <th style="padding:6px;">Failed</th>
        </tr>
      </thead>
      <tbody class="element-table-body" id="element-table-body-{instance}">
      </tbody>
    </table>
  </div>

  <div style="margin-top:12px;padding-top:10px;border-top:1px solid #eee;display:flex;gap:15px;font-size:12px;color:#666;">
    <strong>Legend</strong>:
    <span style="color:{_STATUS_COLORS["passed"]};font-weight:700;">● Passed</span>
    <span style="color:{_STATUS_COLORS["partial_pass"]};font-weight:700;">● Partial (fallback)</span>
    <span style="color:{_STATUS_COLORS["failed"]};font-weight:700;">● Failed</span>
    <span style="color:{_EVIDENCE_STEP_COLORS["navigate"]};font-weight:700;">● Navigate</span>
    <span style="color:{_EVIDENCE_STEP_COLORS["fill"]};font-weight:700;">● Fill</span>
    <span style="color:{_EVIDENCE_STEP_COLORS["click"]};font-weight:700;">● Click</span>
    <span style="color:{_EVIDENCE_STEP_COLORS["assertion"]};font-weight:700;">● Assertion</span>
    <span style="margin-left:auto;"><strong>Circle size</strong> = number of hits on that element</span>
  </div>
</div>

<script>
(() => {{
  const COLORS = {colors_json};
  const STATUS_COLORS = {status_colors_json};
  const allPoints = {points_json};
  const plottedPoints = {plotted_json};
  const aggregated = {aggregated_json};
  // Every heatmap scopes itself: a report can carry one heatmap per page,
  // and the first heatmap's script must not drive the others.
  const ROOT = document.getElementById("suite-heat-{instance}");
  const wrap = ROOT.querySelector(".suite-wrap");
  const svg = ROOT.querySelector("svg.suite-svg");
  const img = ROOT.querySelector(".suite-img");
  const tableBody = ROOT.querySelector(".element-table-body");

  let currentFilter = "all";

  // Locators and labels are free text (site copy). They go into innerHTML
  // below, so they must be escaped — without this the element table threw
  // and never rendered at all.
  function escapeHtml(v) {{
    return String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }}

  function baseRadius(runCount) {{
    const rc = Number(runCount || 1);
    return 18 + Math.min(rc * 3, 40);
  }}

  function stepType(typeStr) {{
    const t = String(typeStr || "").toLowerCase();
    if (t.includes("navigate")) return "navigate";
    if (t.includes("fill")) return "fill";
    if (t.includes("click")) return "click";
    if (t.includes("assert")) return "assertion";
    return "click";
  }}

  function getDominantColor(status) {{
    return STATUS_COLORS[status] || "#999";
  }}

  function renderTable() {{
    const filtered = currentFilter === "all"
      ? aggregated
      : aggregated.filter(e => e.dominant_status === currentFilter);

    tableBody.innerHTML = filtered.map((elem, idx) => {{
      const dominantColor = getDominantColor(elem.dominant_status);
      const locator = elem.locators[0] || "—";
      const element = `${{elem.tags[0] || 'element'}}${{elem.element_ids[0] ? '#' + elem.element_ids[0] : ''}}`;
      return `
        <tr style="border-bottom:1px solid #f0f0f0;cursor:pointer;" data-element-idx="${{idx}}">
          <td style="padding:6px;">${{elem.x.toFixed(1)}}%, ${{elem.y.toFixed(1)}}%</td>
          <td style="padding:6px;color:${{dominantColor}};font-weight:600;">${{element}}</td>
          <td style="padding:6px;font-family:monospace;font-size:11px;">${{escapeHtml(locator)}}</td>
          <td style="padding:6px;text-align:center;">${{elem.total}}</td>
          <td style="padding:6px;text-align:center;color:${{STATUS_COLORS.passed}};">${{elem.passed}}</td>
          <td style="padding:6px;text-align:center;color:${{STATUS_COLORS.partial_pass}};">${{elem.partial_pass}}</td>
          <td style="padding:6px;text-align:center;color:${{STATUS_COLORS.failed}};">${{elem.failed}}</td>
        </tr>
      `;
    }}).join("");
  }}

  function render() {{
    let w = 0;
    let h = 0;
    if (img && img.getBoundingClientRect) {{
      const r = img.getBoundingClientRect();
      w = r.width;
      h = r.height;
    }}
    if (!w || !h) {{
      const r = wrap.getBoundingClientRect();
      w = r.width;
      h = r.height;
    }}
    svg.setAttribute("width", String(w));
    svg.setAttribute("height", String(h));
    svg.setAttribute("viewBox", `0 0 ${{w}} ${{h}}`);

    const filtered = currentFilter === "all"
      ? aggregated
      : aggregated.filter(e => e.dominant_status === currentFilter);

    const out = [];
    filtered.forEach((elem, idx) => {{
      const color = getDominantColor(elem.dominant_status);
      const r = baseRadius(elem.run_count);
      const cx = (Number(elem.x) / 100) * w;
      const cy = (Number(elem.y) / 100) * h;
      const opacity = Math.min(0.3 + (Number(elem.run_count || 1) * 0.1), 0.9);

      const locator = elem.locators[0] || "N/A";
      const labels = elem.labels.join(", ") || "N/A";
      const tooltip = `Locator: ${{escapeHtml(locator)}}\\nLabels: ${{escapeHtml(labels)}}\\nHits: ${{elem.total}}\\nRuns: ${{elem.runs}}\\nPassed: ${{elem.passed}}\\nFailed: ${{elem.failed}}\\nPartial: ${{elem.partial_pass}}`;

      out.push(`
        <g class="point-group" style="cursor:help;" data-element-idx="${{idx}}">
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="white" stroke-width="4" opacity="${{opacity}}" />
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="3" opacity="${{opacity}}" />
          <circle cx="${{cx}}" cy="${{cy}}" r="${{Math.max(10, r - 12)}}" fill="none" stroke="${{color}}" stroke-width="2" opacity="${{opacity}}" />
          <text x="${{cx}}" y="${{cy + 5}}" font-size="14" font-weight="bold" fill="${{color}}" text-anchor="middle" style="pointer-events:none;">${{elem.run_count}}</text>
          <title>${{tooltip}}</title>
        </g>
      `);
    }});
    svg.innerHTML = out.join("");

    // Add click handlers to table rows
    const rows = tableBody.querySelectorAll("tr");
    rows.forEach((row, idx) => {{
      row.addEventListener("mouseenter", () => {{
        // Highlight corresponding circle
        const circles = svg.querySelectorAll(`[data-element-idx="${{idx}}"] circle`);
        circles.forEach(c => {{
          c.setAttribute("stroke-width", "5");
          c.setAttribute("opacity", "1");
        }});
      }});
      row.addEventListener("mouseleave", () => {{
        // Reset highlighting
        render();
      }});
    }});
  }}

  // Filter button handlers
  ROOT.querySelectorAll(".heatmap-filter-btn").forEach(btn => {{
    btn.addEventListener("click", () => {{
      currentFilter = btn.dataset.filter;
      render();
      renderTable();
    }});
  }});

  const ro = new ResizeObserver(() => render());
  ro.observe(wrap);
  if (img && img.addEventListener) {{
    img.addEventListener("load", () => render());
  }}
  render();
  renderTable();
}})();
</script>
"""
