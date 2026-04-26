"""Coverage confidence heat map aggregation from EvidenceTracker sidecars.

This module also houses the Tier 3 per-URL suite heatmap rendering logic
(moved from ``src/evidence_report.py``).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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


# ---------------------------------------------------------------------------
# Tier 3: Per-URL Suite Heatmap (moved from evidence_report.py)
# ---------------------------------------------------------------------------


def _extract_step_points_by_url(sidecar: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Return (points_by_url, background_screenshot_by_url) from one sidecar.

    Points are derived by tracking the current URL as `navigate` steps occur.
    Background screenshot chooses the last assertion screenshot within a URL segment,
    otherwise the last screenshot for that segment.
    """
    steps = sidecar.get("steps", [])
    if not isinstance(steps, list):
        return {}, {}

    points_by_url: dict[str, list[dict[str, Any]]] = {}
    bg_by_url: dict[str, str] = {}

    current_url = ""
    current_url_norm = ""
    segment_screenshots: list[tuple[int, str]] = []  # (priority, rel_path)

    def is_meaningful_screenshot(step: dict[str, Any]) -> bool:
        """Check if a screenshot is likely to be meaningful (not a consent overlay)."""
        label = str(step.get("label", "")).lower()
        # Deprioritize screenshots of consent overlays or common pre-action states
        deprioritize = ["consent", "overlay", "cookie", "accept", "dismiss", "initial", "pre-action"]
        return not any(word in label for word in deprioritize)

    def flush_segment(url_norm: str) -> None:
        if not url_norm or not segment_screenshots:
            return
        # Choose the highest priority screenshot (assertions are priority 3/2, others 1)
        # If priorities are equal, prefer the one that is "meaningful"
        # Finally prefer the last one in the segment
        sorted_shots = sorted(segment_screenshots, key=lambda x: (x[0], x[1]))
        bg_by_url[url_norm] = sorted_shots[-1][1]

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type", "")).lower()
        if "navigate" in step_type:
            flush_segment(current_url_norm)
            current_url = str(step.get("value", "") or "")
            current_url_norm = _normalise_url(current_url)
            segment_screenshots = []
            shot = step.get("screenshot")
            if shot:
                # Navigate screenshots are priority 0 (fallback only)
                segment_screenshots.append((0, str(shot)))

            if current_url_norm:
                result = step.get("result", {})
                run_count = 1
                if isinstance(result, dict):
                    rc = result.get("run_count")
                    if isinstance(rc, int | float):
                        run_count = int(rc)
                points_by_url.setdefault(current_url_norm, []).append(
                    {
                        "type": "navigate",
                        "x": 50.0,
                        "y": 50.0,
                        "run_count": run_count,
                    }
                )
            continue

        if not current_url_norm:
            continue

        shot = step.get("screenshot")
        if shot:
            priority = 1
            if "assert" in step_type:
                priority = 3 if is_meaningful_screenshot(step) else 2
            elif is_meaningful_screenshot(step):
                priority = 1
            else:
                priority = 0
            segment_screenshots.append((priority, str(shot)))

        element = step.get("element", {})
        viewport_pct = element.get("viewport_pct") if isinstance(element, dict) else None
        if not isinstance(viewport_pct, dict):
            continue
        x = viewport_pct.get("x")
        y = viewport_pct.get("y")
        if not isinstance(x, int | float) or not isinstance(y, int | float):
            continue

        result = step.get("result", {})
        run_count = 1
        if isinstance(result, dict):
            rc = result.get("run_count")
            if isinstance(rc, int | float):
                run_count = int(rc)

        # Extract step status for Tier 3 heatmap
        step_status = "passed"
        if isinstance(result, dict):
            status = result.get("status", "passed")
            if status in ("failed", "partial_pass", "skipped"):
                step_status = status

        points_by_url.setdefault(current_url_norm, []).append(
            {
                "type": step_type,
                "x": float(x),
                "y": float(y),
                "run_count": run_count,
                "status": step_status,
                "locator": step.get("locator", ""),
                "label": step.get("label", ""),
                "element_id": element.get("element_id", "") if isinstance(element, dict) else "",
                "tag": element.get("tag", "") if isinstance(element, dict) else "",
            }
        )

    flush_segment(current_url_norm)
    return points_by_url, bg_by_url


def generate_suite_heatmap(
    *,
    evidence_dir: Path,
    page_url: str,
) -> str:
    """Render a suite-level heatmap for one page URL across all sidecars.

    Tier 3 redesign: Per-URL aggregation with status overlay and locator info.
    - Color-coded by test status: green (passed), yellow (partial_pass), red (failed)
    - Circle size proportional to test count
    - Tooltips show locator, element info, and test results
    - Filterable by test status
    """
    if not evidence_dir.exists():
        return "<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>Evidence directory not found.</div>"

    target_norm = _normalise_url(page_url)
    all_points: list[dict[str, Any]] = []
    best_background: tuple[tuple[int, int], str] | None = None  # ((priority, point_count), rel_path)

    for sidecar_path in evidence_dir.glob("*.evidence.json"):
        sidecar = _safe_read_json(sidecar_path)
        if not sidecar:
            continue
        points_by_url, bg_by_url = _extract_step_points_by_url(sidecar)
        current_points = points_by_url.get(target_norm, [])
        if not current_points:
            continue

        all_points.extend(current_points)
        if target_norm in bg_by_url:
            rel = bg_by_url[target_norm]
            # Priority: assertion (priority 3/2) > meaningful interaction (priority 1) > navigate (priority 0)
            priority = 0
            if "assert" in rel:
                priority = 3
            elif any(p["type"] != "navigate" for p in current_points):
                priority = 2
            else:
                priority = 1

            score = (priority, len(current_points))
            if best_background is None or score > best_background[0]:
                best_background = (score, rel)

    if not all_points:
        escaped = escape_html(page_url)
        return f"<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>No evidence points found for <code>{escaped}</code>.</div>"

    # Pick any background screenshot we found; if none, render points-only.
    image_data_uri = None
    if best_background:
        background_rel = best_background[1]
        image_path = (
            (evidence_dir.parent / background_rel).resolve()
            if background_rel.startswith("evidence/")
            else (evidence_dir / background_rel).resolve()
        )
        image_data_uri = _safe_embed_image_data_uri(image_path)

    # Aggregate per-element: group by (x, y) position and collect statuses
    # Elements within 2% of each other are considered the same element
    ELEMENT_TOLERANCE = 2.0
    aggregated: dict[str, dict[str, Any]] = {}
    for point in all_points:
        key = f"{point['x']:.1f}_{point['y']:.1f}"
        # Check if this point is close to an existing element
        merged = False
        for agg_key, agg in aggregated.items():
            ax, ay = agg["x"], agg["y"]
            px, py = point["x"], point["y"]
            if abs(ax - px) < ELEMENT_TOLERANCE and abs(ay - py) < ELEMENT_TOLERANCE:
                # Merge into existing element
                key = agg_key
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

    # Compute summary stats per element
    for _key, elem in aggregated.items():
        status_counts: dict[str, int] = {}
        for s in elem["statuses"]:
            status_counts[s] = status_counts.get(s, 0) + 1
        elem["total"] = len(elem["statuses"])
        elem["passed"] = status_counts.get("passed", 0)
        elem["failed"] = status_counts.get("failed", 0)
        elem["partial_pass"] = status_counts.get("partial_pass", 0)
        # Dominant status (most common)
        elem["dominant_status"] = max(status_counts, key=lambda s: status_counts[s]) if status_counts else "passed"
        # Convert sets to lists for JSON serialization
        elem["locators"] = list(elem["locators"])[:3]  # Limit to 3
        elem["labels"] = list(elem["labels"])[:3]
        elem["element_ids"] = list(elem["element_ids"])
        elem["tags"] = list(elem["tags"])

    # Build aggregated data for JS
    aggregated_json = json.dumps(list(aggregated.values()))
    status_counts_overall: dict[str, int] = {}
    for point in all_points:
        s = point.get("status", "passed")
        status_counts_overall[s] = status_counts_overall.get(s, 0) + 1

    points_json = json.dumps(all_points)
    colors_json = json.dumps(_EVIDENCE_STEP_COLORS)
    status_colors_json = json.dumps(_STATUS_COLORS)
    safe_url = escape_html(page_url)
    bg_html = (
        f'<img id="suite-img" src="{image_data_uri}" alt="suite screenshot" style="display:block;width:100%;height:auto;border-radius:8px;border:1px solid #eee;" />'
        if image_data_uri
        else '<div id="suite-img" style="width:100%;aspect-ratio:16/9;border-radius:8px;border:1px dashed #ddd;display:flex;align-items:center;justify-content:center;color:#666;">No screenshot available for this page. Rendering points only.</div>'
    )

    return f"""
<div style="border:1px solid #e6e6e6;border-radius:10px;padding:14px;background:#fff;">
  <div style="font-weight:600;margin-bottom:10px;">Suite Heatmap — Per-URL Element Coverage</div>
  <div style="color:#6b7280;font-size:12px;margin:-6px 0 10px 0;">{safe_url}</div>

  <!-- Summary stats -->
  <div style="display:flex;gap:15px;margin-bottom:12px;font-size:13px;">
    <span><strong>Total:</strong> {len(all_points)} evidence points</span>
    <span style="color:{_STATUS_COLORS["passed"]};font-weight:700;">Passed: {status_counts_overall.get("passed", 0)}</span>
    <span style="color:{_STATUS_COLORS["partial_pass"]};font-weight:700;">Partial: {status_counts_overall.get("partial_pass", 0)}</span>
    <span style="color:{_STATUS_COLORS["failed"]};font-weight:700;">Failed: {status_counts_overall.get("failed", 0)}</span>
    <span style="color:{_STATUS_COLORS["skipped"]};font-weight:700;">Skipped: {status_counts_overall.get("skipped", 0)}</span>
  </div>

  <!-- Filter buttons -->
  <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
    <button class="heatmap-filter-btn" data-filter="all" style="padding:4px 12px;border:1px solid #ddd;border-radius:16px;background:#fff;cursor:pointer;font-size:12px;">All</button>
    <button class="heatmap-filter-btn" data-filter="passed" style="padding:4px 12px;border:1px solid #1D9E75;border-radius:16px;background:#1D9E75;color:#fff;cursor:pointer;font-size:12px;">Passed</button>
    <button class="heatmap-filter-btn" data-filter="partial_pass" style="padding:4px 12px;border:1px solid #FAC775;border-radius:16px;background:#FAC775;color:#333;cursor:pointer;font-size:12px;">Partial</button>
    <button class="heatmap-filter-btn" data-filter="failed" style="padding:4px 12px;border:1px solid #F09595;border-radius:16px;background:#F09595;color:#333;cursor:pointer;font-size:12px;">Failed</button>
  </div>

  <div id="suite-wrap" style="position:relative;width:100%;max-width:1100px;">
    {bg_html}
    <svg id="suite-svg" style="position:absolute;left:0;top:0;pointer-events:none;z-index:5;"></svg>
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
      <tbody id="element-table-body">
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
    <span style="margin-left:auto;"><strong>Circle size</strong> = number of test hits</span>
  </div>
</div>

<script>
(() => {{
  const COLORS = {colors_json};
  const STATUS_COLORS = {status_colors_json};
  const allPoints = {points_json};
  const aggregated = {aggregated_json};
  const wrap = document.getElementById("suite-wrap");
  const svg = document.getElementById("suite-svg");
  const img = document.getElementById("suite-img");
  const tableBody = document.getElementById("element-table-body");

  let currentFilter = "all";

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
      const tooltip = `Locator: ${{locator}}\\nLabels: ${{labels}}\\nTotal: ${{elem.total}}\\nPassed: ${{elem.passed}}\\nFailed: ${{elem.failed}}\\nPartial: ${{elem.partial_pass}}`;

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
  document.querySelectorAll(".heatmap-filter-btn").forEach(btn => {{
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
