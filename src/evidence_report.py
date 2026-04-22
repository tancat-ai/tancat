"""Evidence/annotated report generators.

These read ``.evidence.json`` sidecar files from disk and produce HTML strings.
Entirely independent of the standard report renderers.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from src.report_builder import escape_html

_EVIDENCE_STEP_COLORS: dict[str, str] = {
    "navigate": "#993556",
    "fill": "#0F6E56",
    "click": "#185FA5",
    "assertion": "#854F0B",
}


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


def _normalise_url(url: str) -> str:
    """Normalise URLs for matching across redirects and trailing slashes."""
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


def _clean_evidence_label(label: str) -> str:
    """Convert raw placeholder-token labels into cleaner user-facing text."""
    raw = str(label or "").strip()
    match = re.fullmatch(r"\{\{([A-Z_]+):(.+)\}\}", raw)
    if not match:
        return raw

    action = match.group(1).strip().lower().replace("_", " ")
    description = match.group(2).strip()
    if not description:
        return raw
    return f"{action.title()}: {description}"


def _prepare_steps_for_display(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return steps with labels normalized for UI rendering."""
    prepared: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        cloned = dict(step)
        cloned["label"] = _clean_evidence_label(str(step.get("label", "")))
        prepared.append(cloned)
    return prepared


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
        # Choose the highest priority screenshot (assertions are priority 2, others 1)
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

        points_by_url.setdefault(current_url_norm, []).append(
            {
                "type": step_type,
                "x": float(x),
                "y": float(y),
                "run_count": run_count,
            }
        )

    flush_segment(current_url_norm)
    return points_by_url, bg_by_url


def generate_suite_heatmap(
    *,
    evidence_dir: Path,
    page_url: str,
) -> str:
    """Render a suite-level heatmap for one page URL across all sidecars."""
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
            # We also prefer the screenshot that has the most points associated with it in this sidecar
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

    points_json = json.dumps(all_points)
    colors_json = json.dumps(_EVIDENCE_STEP_COLORS)
    safe_url = escape_html(page_url)
    bg_html = (
        f'<img id="suite-img" src="{image_data_uri}" alt="suite screenshot" style="display:block;width:100%;height:auto;border-radius:8px;border:1px solid #eee;" />'
        if image_data_uri
        else '<div id="suite-img" style="width:100%;aspect-ratio:16/9;border-radius:8px;border:1px dashed #ddd;display:flex;align-items:center;justify-content:center;color:#666;">No screenshot available for this page. Rendering points only.</div>'
    )

    return f"""
<div style="border:1px solid #e6e6e6;border-radius:10px;padding:14px;background:#fff;">
  <div style="font-weight:600;margin-bottom:10px;">Suite Heatmap</div>
  <div style="color:#6b7280;font-size:12px;margin:-6px 0 10px 0;">{safe_url}</div>
  <div id="suite-wrap" style="position:relative;width:100%;max-width:1100px;">
    {bg_html}
    <svg id="suite-svg" style="position:absolute;left:0;top:0;pointer-events:none;z-index:5;"></svg>
  </div>
  <div style="margin-top:12px;padding-top:10px;border-top:1px solid #eee;display:flex;gap:15px;font-size:12px;color:#666;">
    <strong>Legend</strong>:
    <span style="color:{_EVIDENCE_STEP_COLORS["navigate"]};font-weight:700;">navigate</span>,
    <span style="color:{_EVIDENCE_STEP_COLORS["fill"]};font-weight:700;">fill</span>,
    <span style="color:{_EVIDENCE_STEP_COLORS["click"]};font-weight:700;">click</span>,
    <span style="color:{_EVIDENCE_STEP_COLORS["assertion"]};font-weight:700;">assertion</span>
    <span style="margin-left:auto;"><strong>Points</strong>: {len(all_points)} total interactions across all tests.</span>
  </div>
</div>

<script>
(() => {{
  const COLORS = {colors_json};
  const points = {points_json};
  const wrap = document.getElementById("suite-wrap");
  const svg = document.getElementById("suite-svg");
  const img = document.getElementById("suite-img");

  function baseRadius(runCount) {{
    const rc = Number(runCount || 1);
    // Large, solid circles for maximum visibility
    return 22 + Math.min(rc * 2, 50);
  }}

  function stepType(typeStr) {{
    const t = String(typeStr || "").toLowerCase();
    if (t.includes("navigate")) return "navigate";
    if (t.includes("fill")) return "fill";
    if (t.includes("click")) return "click";
    if (t.includes("assert")) return "assertion";
    return "click";
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

    const out = [];
    points.forEach((p, idx) => {{
      const t = stepType(p.type);
      const color = COLORS[t] || "#999";
      const r = baseRadius(p.run_count);
      const cx = (Number(p.x) / 100) * w;
      const cy = (Number(p.y) / 100) * h;
      const opacity = Math.min(0.25 + (Number(p.run_count || 1) * 0.08), 0.85);

      // Grouping logic for tooltip
      const label = p.label || p.type;

      out.push(`
        <g class="point-group" style="cursor:help;">
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="white" stroke-width="4" opacity="${{opacity}}" />
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="3" opacity="${{opacity}}" />
          <circle cx="${{cx}}" cy="${{cy}}" r="${{Math.max(8, r - 15)}}" fill="none" stroke="${{color}}" stroke-width="2" opacity="${{opacity}}" />
          <text x="${{cx}}" y="${{cy + 4}}" font-size="12" font-weight="bold" fill="${{color}}" text-anchor="middle" style="pointer-events:none;">${{idx + 1}}</text>
          <title>${{label}} (x: ${{p.x.toFixed(1)}}%, y: ${{p.y.toFixed(1)}}%)</title>
        </g>
      `);
    }});
    svg.innerHTML = out.join("");
  }}

  const ro = new ResizeObserver(() => render());
  ro.observe(wrap);
  if (img && img.addEventListener) {{
    img.addEventListener("load", () => render());
  }}
  render();
}})();
</script>
"""


def generate_annotated_screenshot(
    *,
    sidecar_path: Path,
    view_mode: Literal["annotated", "heatmap", "clean"] = "annotated",
    title: str = "",
) -> str:
    """Return interactive HTML for an annotated evidence screenshot.

    This reads a single `.evidence.json` sidecar written by `EvidenceTracker` and renders
    an SVG overlay on top of the recorded screenshot image.
    """

    sidecar = _safe_read_json(sidecar_path)
    if sidecar is None:
        escaped = escape_html(str(sidecar_path))
        return f"<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>Missing sidecar: <code>{escaped}</code></div>"

    steps = sidecar.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return "<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>No steps recorded in sidecar.</div>"

    screenshot_rel: str | None = None
    # Prefer an assertion screenshot for context; otherwise take the last available screenshot.
    screenshots: list[str] = []
    assertion_screenshots: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        shot = step.get("screenshot")
        if not shot:
            continue
        shot_str = str(shot)
        screenshots.append(shot_str)
        step_type = str(step.get("type", "")).lower()
        if "assert" in step_type:
            assertion_screenshots.append(shot_str)

    if assertion_screenshots:
        screenshot_rel = assertion_screenshots[-1]
    elif screenshots:
        screenshot_rel = screenshots[-1]
    if not screenshot_rel:
        return "<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>No screenshot recorded in sidecar steps.</div>"

    image_path = (
        (sidecar_path.parent.parent / screenshot_rel).resolve()
        if screenshot_rel.startswith("evidence/")
        else (sidecar_path.parent / screenshot_rel).resolve()
    )
    image_data_uri = _safe_embed_image_data_uri(image_path)
    if not image_data_uri:
        escaped = escape_html(str(image_path))
        return f"<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>Screenshot not found or unsupported: <code>{escaped}</code></div>"

    test_block = sidecar.get("test", {}) if isinstance(sidecar.get("test", {}), dict) else {}
    page_block = sidecar.get("page", {}) if isinstance(sidecar.get("page", {}), dict) else {}
    safe_title = escape_html(title or test_block.get("name", "") or "Evidence")
    safe_url = escape_html(str(page_block.get("url", "")))
    mode = view_mode

    mode_json = json.dumps(mode)
    colors_json = json.dumps(_EVIDENCE_STEP_COLORS)
    steps_json = json.dumps(_prepare_steps_for_display(steps))

    # Minimal, self-contained interactive HTML with ResizeObserver driven overlay sizing.
    # NOTE: Streamlit's st.components.v1.html can render this safely.
    return f"""
<div style="border:1px solid #e6e6e6;border-radius:10px;padding:14px;background:#fff;">
  <div style="font-weight:600;margin-bottom:10px;">{safe_title}</div>
  <div style="color:#6b7280;font-size:12px;margin:-6px 0 10px 0;">{safe_url}</div>
  <div id="ev-wrap" style="position:relative;width:100%;max-width:1100px;">
    <img id="ev-img" src="{image_data_uri}" alt="evidence screenshot" style="display:block;width:100%;height:auto;border-radius:8px;border:1px solid #eee;" />
    <svg id="ev-svg" style="position:absolute;left:0;top:0;pointer-events:none;"></svg>
  </div>

  <div style="display:flex;gap:10px;align-items:center;margin-top:10px;color:#555;font-size:12px;">
    <span><strong>Mode</strong>: {escape_html(mode)}</span>
    <span style="margin-left:auto;"><strong>Legend</strong>:
      <span style="color:{_EVIDENCE_STEP_COLORS["navigate"]};font-weight:700;">navigate</span>,
      <span style="color:{_EVIDENCE_STEP_COLORS["fill"]};font-weight:700;">fill</span>,
      <span style="color:{_EVIDENCE_STEP_COLORS["click"]};font-weight:700;">click</span>,
      <span style="color:{_EVIDENCE_STEP_COLORS["assertion"]};font-weight:700;">assertion</span>
    </span>
  </div>

  <div id="ev-timeline" style="margin-top:12px;border-top:1px solid #f0f0f0;padding-top:12px;">
  </div>
</div>

<script>
(() => {{
  const MODE = {mode_json};
  const COLORS = {colors_json};
  const steps = {steps_json};

  const wrap = document.getElementById("ev-wrap");
  const img = document.getElementById("ev-img");
  const svg = document.getElementById("ev-svg");
  const timeline = document.getElementById("ev-timeline");
  let hoveredId = null;

  function baseRadius(runCount) {{
    const rc = Number(runCount || 1);
    return 14 + Math.min(rc * 0.7, 20);
  }}

  function stepType(step) {{
    const t = String(step.type || "").toLowerCase();
    if (t.includes("navigate")) return "navigate";
    if (t.includes("fill")) return "fill";
    if (t.includes("click")) return "click";
    if (t.includes("assert")) return "assertion";
    return "click";
  }}

  function getPct(step) {{
    const el = step.element || {{}};
    const pct = el.viewport_pct || null;
    if (!pct) return null;
    const x = Number(pct.x);
    const y = Number(pct.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return {{ x, y }};
  }}

  function renderTimeline() {{
    timeline.innerHTML = "";
    steps.forEach((s, idx) => {{
      const id = idx;
      const t = stepType(s);
      const label = String(s.label || t);
      const status = String((s.result && s.result.status) || "");
      const runCount = s.result && s.result.run_count ? s.result.run_count : 1;
      const row = document.createElement("div");
      row.setAttribute("data-step-id", String(id));
      row.style.display = "flex";
      row.style.gap = "10px";
      row.style.alignItems = "center";
      row.style.padding = "8px 10px";
      row.style.border = "1px solid #f0f0f0";
      row.style.borderRadius = "8px";
      row.style.marginBottom = "8px";
      row.style.cursor = "default";
      row.innerHTML = `
        <div style="min-width:30px;height:30px;border-radius:999px;background:${{COLORS[t] || "#999"}};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;">${{idx + 1}}</div>
        <div style="flex:1;">
          <div style="font-weight:600;color:#222;">${{label}}</div>
          <div style="font-size:12px;color:#666;">type=${{t}} · status=${{status}} · run_count=${{runCount}}</div>
        </div>
      `;
      row.addEventListener("mouseenter", () => {{
        hoveredId = id;
        renderOverlay();
        highlightTimeline();
      }});
      row.addEventListener("mouseleave", () => {{
        hoveredId = null;
        renderOverlay();
        highlightTimeline();
      }});
      timeline.appendChild(row);
    }});
  }}

  function highlightTimeline() {{
    const rows = timeline.querySelectorAll("[data-step-id]");
    rows.forEach((row) => {{
      const id = Number(row.getAttribute("data-step-id"));
      if (hoveredId === id) {{
        row.style.borderColor = "#c7d2fe";
        row.style.background = "#eef2ff";
      }} else {{
        row.style.borderColor = "#f0f0f0";
        row.style.background = "#fff";
      }}
    }});
  }}

  function renderOverlay() {{
    const rect = img.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    svg.setAttribute("width", String(w));
    svg.setAttribute("height", String(h));
    svg.setAttribute("viewBox", `0 0 ${{w}} ${{h}}`);
    svg.style.pointerEvents = "none";

    const out = [];
    steps.forEach((s, idx) => {{
      const pct = getPct(s);
      if (!pct) return;
      const t = stepType(s);
      const color = COLORS[t] || "#999";
      const runCount = (s.result && s.result.run_count) ? s.result.run_count : 1;
      const r = baseRadius(runCount);
      const cx = (pct.x / 100) * w;
      const cy = (pct.y / 100) * h;
      const isHover = hoveredId === idx;

      if (MODE === "clean") {{
        return;
      }}

      if (MODE === "heatmap") {{
        const opacity = Math.min(0.15 + (Number(runCount || 1) * 0.05), 0.6);
        out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="6" opacity="${{opacity}}" />`);
        out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{Math.max(6, r - 10)}}" fill="none" stroke="${{color}}" stroke-width="2" opacity="${{opacity}}" />`);
        return;
      }}

      // annotated
      const stroke = isHover ? "#111827" : "rgba(0,0,0,0.35)";
      const sw = isHover ? 3 : 2;
      out.push(`
        <g class="point-group" style="cursor:help;">
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="${{color}}" opacity="0.4" />
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="white" stroke-width="3" opacity="0.9" />
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="1.5" opacity="0.9" />
          <text x="${{cx}}" y="${{cy + 6}}" font-size="16" font-weight="900" fill="white" text-anchor="middle" style="pointer-events:none; filter: drop-shadow(0px 0px 2px rgba(0,0,0,0.8));">${{idx + 1}}</text>
          <title>${{label}} (status: ${{status}})</title>
        </g>
      `);
    }});

    svg.innerHTML = out.join("");
  }}

  const ro = new ResizeObserver(() => renderOverlay());
  ro.observe(wrap);
  img.addEventListener("load", () => renderOverlay());

  renderTimeline();
  renderOverlay();
  highlightTimeline();
}})();
</script>
"""


def generate_annotated_journey(
    *,
    sidecar_path: Path,
    view_mode: Literal["annotated", "heatmap", "clean"] = "annotated",
    title: str = "",
) -> str:
    """Annotated evidence viewer that supports multi-page journeys.

    A single test may navigate across multiple URLs; this viewer lets you switch the
    background screenshot and overlay/timeline per URL segment.
    """
    sidecar = _safe_read_json(sidecar_path)
    if sidecar is None:
        escaped = escape_html(str(sidecar_path))
        return f"<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>Missing sidecar: <code>{escaped}</code></div>"

    steps = sidecar.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return "<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>No steps recorded in sidecar.</div>"
    prepared_steps = _prepare_steps_for_display(steps)

    # Build segments keyed by normalised URL.
    segments: list[dict[str, Any]] = []
    current_url = ""
    current_norm = ""
    current_steps: list[dict[str, Any]] = []
    seg_screens: list[str] = []
    seg_assert_screens: list[str] = []

    def flush() -> None:
        nonlocal current_url, current_norm, current_steps, seg_screens, seg_assert_screens
        if not current_norm:
            return
        screenshot_rel = seg_assert_screens[-1] if seg_assert_screens else (seg_screens[-1] if seg_screens else "")
        segments.append(
            {
                "url": current_url,
                "url_norm": current_norm,
                "screenshot": screenshot_rel,
                "steps": current_steps,
            }
        )

    for step in prepared_steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type", "")).lower()
        if "navigate" in step_type:
            flush()
            current_url = str(step.get("value", "") or "")
            current_norm = _normalise_url(current_url)
            current_steps = []
            seg_screens = []
            seg_assert_screens = []
            shot = step.get("screenshot")
            if shot:
                seg_screens.append(str(shot))
            continue

        if not current_norm:
            continue

        shot = step.get("screenshot")
        if shot:
            seg_screens.append(str(shot))
            if "assert" in step_type:
                seg_assert_screens.append(str(shot))
        current_steps.append(step)

    flush()
    if not segments:
        return "<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>No navigations recorded in sidecar steps.</div>"

    # Resolve screenshot data URIs per segment (best-effort).
    for seg in segments:
        rel = str(seg.get("screenshot") or "")
        if not rel:
            seg["image_data_uri"] = ""
            continue
        image_path = (
            (sidecar_path.parent.parent / rel).resolve()
            if rel.startswith("evidence/")
            else (sidecar_path.parent / rel).resolve()
        )
        seg["image_data_uri"] = _safe_embed_image_data_uri(image_path) or ""

    payload = {
        "title": title or str(sidecar.get("test", {}).get("name", "Evidence")),
        "segments": segments,
        "colors": _EVIDENCE_STEP_COLORS,
        "mode": view_mode,
    }
    payload_json = json.dumps(payload)

    safe_title = escape_html(str(payload["title"]))
    safe_mode = escape_html(str(view_mode))
    return f"""
<div style="border:1px solid #e6e6e6;border-radius:10px;padding:14px;background:#fff;">
  <div style="font-weight:600;margin-bottom:10px;">{safe_title}</div>
  <div style="display:flex;gap:10px;align-items:center;margin:-6px 0 12px 0;">
    <label style="font-size:12px;color:#6b7280;">Segment</label>
    <select id="seg-select" style="flex:1;padding:6px 10px;border:1px solid #e5e7eb;border-radius:8px;"></select>
    <span style="font-size:12px;color:#6b7280;">Mode: {safe_mode}</span>
  </div>
  <div id="seg-url" style="color:#6b7280;font-size:12px;margin:-6px 0 10px 0;"></div>
  <div id="seg-wrap" style="position:relative;width:100%;max-width:1100px;">
    <img id="seg-img" alt="evidence screenshot" style="display:block;width:100%;height:auto;border-radius:8px;border:1px solid #eee;" />
    <svg id="seg-svg" style="position:absolute;left:0;top:0;pointer-events:none;z-index:5;"></svg>
  </div>
  <div id="seg-timeline" style="margin-top:12px;border-top:1px solid #f0f0f0;padding-top:12px;"></div>
</div>

<script>
(() => {{
  const data = {payload_json};
  const select = document.getElementById("seg-select");
  const urlEl = document.getElementById("seg-url");
  const img = document.getElementById("seg-img");
  const svg = document.getElementById("seg-svg");
  const wrap = document.getElementById("seg-wrap");
  const timeline = document.getElementById("seg-timeline");

  const MODE = String(data.mode || "annotated");
  const COLORS = data.colors || {{}};
  const segments = data.segments || [];

  function baseRadius(runCount) {{
    const rc = Number(runCount || 1);
    return 14 + Math.min(rc * 0.7, 20);
  }}

  function stepType(step) {{
    const t = String(step.type || "").toLowerCase();
    if (t.includes("navigate")) return "navigate";
    if (t.includes("fill")) return "fill";
    if (t.includes("click")) return "click";
    if (t.includes("assert")) return "assertion";
    return "click";
  }}

  function getPct(step) {{
    const el = step.element || {{}};
    const pct = el.viewport_pct || null;
    if (!pct) return null;
    const x = Number(pct.x);
    const y = Number(pct.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return {{ x, y }};
  }}

  function render(seg) {{
    urlEl.textContent = seg.url || "";
    img.src = seg.image_data_uri || "";

    // Timeline
    timeline.innerHTML = "";
    (seg.steps || []).forEach((s, idx) => {{
      const t = stepType(s);
      const label = String(s.label || t);
      const status = String((s.result && s.result.status) || "");
      const runCount = s.result && s.result.run_count ? s.result.run_count : 1;
      const row = document.createElement("div");
      row.style.display = "flex";
      row.style.gap = "10px";
      row.style.alignItems = "center";
      row.style.padding = "8px 10px";
      row.style.border = "1px solid #f0f0f0";
      row.style.borderRadius = "8px";
      row.style.marginBottom = "8px";
      row.innerHTML = `
        <div style="min-width:30px;height:30px;border-radius:999px;background:${{COLORS[t] || "#999"}};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;">${{idx + 1}}</div>
        <div style="flex:1;">
          <div style="font-weight:600;color:#222;">${{label}}</div>
          <div style="font-size:12px;color:#666;">type=${{t}} · status=${{status}} · run_count=${{runCount}}</div>
        </div>
      `;
      timeline.appendChild(row);
    }});

    function overlay() {{
      const r = img.getBoundingClientRect();
      const w = r.width || wrap.getBoundingClientRect().width;
      const h = r.height || wrap.getBoundingClientRect().height;
      svg.setAttribute("width", String(w));
      svg.setAttribute("height", String(h));
      svg.setAttribute("viewBox", `0 0 ${{w}} ${{h}}`);

      const out = [];
      (seg.steps || []).forEach((s, idx) => {{
        const pct = getPct(s);
        if (!pct) return;
        const t = stepType(s);
        const color = COLORS[t] || "#999";
        const runCount = (s.result && s.result.run_count) ? s.result.run_count : 1;
        const rr = baseRadius(runCount);
        const cx = (pct.x / 100) * w;
        const cy = (pct.y / 100) * h;
        if (MODE === "clean") return;
        if (MODE === "heatmap") {{
          const opacity = Math.min(0.15 + (Number(runCount || 1) * 0.05), 0.6);
          out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{rr}}" fill="none" stroke="${{color}}" stroke-width="6" opacity="${{opacity}}" />`);
          out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{Math.max(6, rr - 10)}}" fill="none" stroke="${{color}}" stroke-width="2" opacity="${{opacity}}" />`);
          return;
        }}
        out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{rr}}" fill="${{color}}" opacity="0.85" stroke="rgba(0,0,0,0.35)" stroke-width="2" />`);
        out.push(`<text x="${{cx}}" y="${{cy + 5}}" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">${{idx + 1}}</text>`);
      }});
      svg.innerHTML = out.join("");
    }}

    const ro = new ResizeObserver(() => overlay());
    ro.observe(wrap);
    img.addEventListener("load", () => overlay());
    overlay();
  }}

  segments.forEach((seg, idx) => {{
    const opt = document.createElement("option");
    opt.value = String(idx);
    opt.textContent = seg.url || `segment ${{idx + 1}}`;
    select.appendChild(opt);
  }});

  select.addEventListener("change", () => {{
    const idx = Number(select.value);
    render(segments[idx] || segments[0]);
  }});

  render(segments[0]);
}})();
</script>
"""
