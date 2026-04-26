"""Evidence/annotated report generators.

These read ``.evidence.json`` sidecar files from disk and produce HTML strings.
Entirely independent of the standard report renderers.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
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

# Status colors for Tier 3 heatmap (also used by heatmap_utils.py)
_STATUS_COLORS: dict[str, str] = {
    "passed": "#1D9E75",  # Green
    "partial_pass": "#FAC775",  # Yellow
    "failed": "#F09595",  # Red
    "skipped": "#6B7280",  # Gray
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
    """Return steps with labels normalized for UI rendering.

    Also extracts failure_note and diagnosis from the result dict when present.
    """
    prepared: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        cloned = dict(step)
        cloned["label"] = _clean_evidence_label(str(step.get("label", "")))
        # Promote failure metadata from result -> top level for easy access
        result = step.get("result", {})
        if isinstance(result, dict):
            cloned["failure_note"] = result.get("failure_note")
            cloned["diagnosis"] = result.get("diagnosis")
            # Mark steps that had failures even if status says passed
            if result.get("error") and not result.get("status"):
                cloned["_had_error"] = True
        prepared.append(cloned)
    return prepared


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
      const failureNote = s.failure_note || null;
      const hasError = status === "failed" || s._had_error;

      // Build row content
      let rowContent = `
        <div style="min-width:30px;height:30px;border-radius:999px;background:${{hasError ? "#dc2626" : COLORS[t] || "#999"}};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;">${{idx + 1}}</div>
        <div style="flex:1;">
          <div style="font-weight:600;color:#222;">${{label}}</div>
          <div style="font-size:12px;color:#666;">type=${{t}} · status=${{status}} · run_count=${{runCount}}</div>
      `;

      // Add failure note if present
      if (failureNote) {{
        rowContent += `
          <div style="margin-top:6px;padding:8px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;font-size:11px;color:#991b1b;max-height:120px;overflow-y:auto;white-space:pre-wrap;">
            <strong>Failure Diagnosis:</strong><br/>
            <pre style="white-space:pre-wrap;margin:0;">${{failureNote}}</pre>
          </div>
        `;
      }}

      rowContent += `</div>`;

      const row = document.createElement("div");
      row.setAttribute("data-step-id", String(id));
      row.style.display = "flex";
      row.style.gap = "10px";
      row.style.alignItems = "center";
      row.style.padding = "8px 10px";
      row.style.border = hasError ? "1px solid #fecaca" : "1px solid #f0f0f0";
      row.style.borderRadius = "8px";
      row.style.marginBottom = "8px";
      row.style.cursor = "default";
      row.style.background = hasError ? "#fef2f2" : "#fff";
      row.innerHTML = rowContent;
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
      const hasError = row.style.background === "#fef2f2" || row.style.borderColor === "#fecaca";
      if (hoveredId === id) {{
        row.style.borderColor = hasError ? "#f87171" : "#c7d2fe";
        row.style.background = hasError ? "#fef2f2" : "#eef2ff";
      }} else {{
        row.style.borderColor = hasError ? "#fecaca" : "#f0f0f0";
        row.style.background = hasError ? "#fef2f2" : "#fff";
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


@dataclass
class EvidenceFile:
    """Represents a single evidence sidecar file."""

    test_name: str
    sidecar_path: Path
    condition_ref: str
    story_ref: str
    status: str
    duration_s: float
    step_count: int
    has_fallback: bool
    has_failure: bool
    screenshots: list[str]


@dataclass
class TestPackageEvidence:
    """Evidence for a single test package directory."""

    package_dir: Path
    package_name: str
    tests: list[EvidenceFile]
    total_steps: int
    total_screenshots: int
    passed: int
    failed: int
    partial_pass: int
    skipped: int


def list_evidence_from_package(package_dir: Path) -> TestPackageEvidence | None:
    """Scan a test package directory for evidence sidecars and return aggregated data.

    Looks for ``*.evidence.json`` files in ``package_dir/evidence/``.

    Returns None if no evidence is found.
    """
    evidence_dir = package_dir / "evidence"
    if not evidence_dir.exists():
        return None

    sidecars = sorted(evidence_dir.glob("*.evidence.json"))
    if not sidecars:
        return None

    tests: list[EvidenceFile] = []
    total_steps = 0
    total_screenshots = 0
    passed = 0
    failed = 0
    partial_pass = 0
    skipped = 0

    for sidecar in sidecars:
        data = _safe_read_json(sidecar)
        if data is None:
            continue

        test_info = data.get("test", {})
        if not isinstance(test_info, dict):
            test_info = {}

        status = str(test_info.get("status", "unknown"))
        steps = data.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        # Count screenshots
        screenshot_paths: list[str] = []
        for step in steps:
            if isinstance(step, dict):
                shot = step.get("screenshot")
                if shot:
                    screenshot_paths.append(str(shot))

        # Check for fallback usage
        has_fallback = False
        for step in steps:
            if isinstance(step, dict):
                result = step.get("result", {})
                if isinstance(result, dict) and result.get("fallback_used"):
                    has_fallback = True
                    break

        # Check for failures
        has_failure = False
        for step in steps:
            if isinstance(step, dict):
                result = step.get("result", {})
                if isinstance(result, dict) and result.get("status") == "failed":
                    has_failure = True
                    break

        tests.append(
            EvidenceFile(
                test_name=str(sidecar.stem),  # Remove .evidence.json
                sidecar_path=sidecar,
                condition_ref=str(test_info.get("condition_ref", "unknown")),
                story_ref=str(test_info.get("story_ref", "unknown")),
                status=status,
                duration_s=float(test_info.get("duration_s", 0)),
                step_count=len(steps),
                has_fallback=has_fallback,
                has_failure=has_failure,
                screenshots=screenshot_paths,
            )
        )

        total_steps += len(steps)
        total_screenshots += len(screenshot_paths)

        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        elif status == "partial_pass":
            partial_pass += 1
        elif status == "skipped":
            skipped += 1

    return TestPackageEvidence(
        package_dir=package_dir,
        package_name=package_dir.name,
        tests=tests,
        total_steps=total_steps,
        total_screenshots=total_screenshots,
        passed=passed,
        failed=failed,
        partial_pass=partial_pass,
        skipped=skipped,
    )


def list_evidence_from_packages(package_dirs: list[Path]) -> list[TestPackageEvidence]:
    """Scan multiple test package directories for evidence.

    Returns a list of ``TestPackageEvidence`` objects, one per directory that
    contains evidence sidecars.  Directories with no evidence are skipped.
    """
    return [result for package_dir in package_dirs if (result := list_evidence_from_package(package_dir)) is not None]


def list_evidence_from_test_dir(test_dir: Path) -> list[TestPackageEvidence]:
    """Scan *test_dir* for subdirectories that contain evidence.

    This is the common case where each generated test lives in its own
    subdirectory under ``generated_tests/``.
    """
    if not test_dir.exists():
        return []

    package_dirs = [d for d in test_dir.iterdir() if d.is_dir() and (d / "evidence").exists()]
    return list_evidence_from_packages(package_dirs)
