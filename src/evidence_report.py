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


def _format_label(label: str, matched_text: str | None = None, truncate: int = 80) -> str:
    """Format a step label with optional matched text for user display."""
    cleaned = _clean_evidence_label(label)
    if matched_text:
        text = matched_text.strip()
        # Clean up excessive whitespace / HTML noise
        text = re.sub(r"\s+", " ", text)
        if len(text) > truncate:
            text = text[:truncate] + "..."
        if text:
            return f'{cleaned}: "{text}"'
    return cleaned


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


def generate_annotated_journey(
    *,
    sidecar_path: Path,
    view_mode: Literal["annotated", "heatmap", "clean"] = "annotated",
    title: str = "",
    bug_report_mode: bool = False,
) -> str:
    """Generate a focused evidence viewer for debugging.

    For passed tests → shows the screenshot cleanly (no overlays) + status summary.
    For failed tests → shows screenshot + failure panel with diagnosis + suggested locators.

    The ``bug_report_mode`` flag strips interactive elements for plain-text export.

    Args:
        sidecar_path: Path to the .evidence.json sidecar file.
        view_mode: Unused (kept for backwards compatibility).
        title: Optional display title.
        bug_report_mode: If True, returns a plain-text summary instead of HTML.

    Returns:
        HTML string (or plain-text when bug_report_mode=True).
    """
    sidecar = _safe_read_json(sidecar_path)
    if sidecar is None:
        return _empty_result(f"Missing sidecar: {sidecar_path}", bug_report_mode)

    steps = sidecar.get("steps", [])
    test_info = sidecar.get("test", {})
    if not isinstance(test_info, dict):
        test_info = {}
    status = str(test_info.get("status", "unknown"))

    if not isinstance(steps, list) or not steps:
        return _empty_result("No steps recorded in sidecar.", bug_report_mode)

    # Determine overall pass/fail status
    has_failure = False
    failed_step: dict[str, Any] | None = None
    for step in steps:
        if isinstance(step, dict) and _is_failed_step(step):
            has_failure = True
            failed_step = step
            break

    # Find screenshots
    screenshot_rel = _find_best_screenshot(steps)
    image_data_uri = ""
    if screenshot_rel:
        image_path = (
            (sidecar_path.parent.parent / screenshot_rel).resolve()
            if screenshot_rel.startswith("evidence/")
            else (sidecar_path.parent / screenshot_rel).resolve()
        )
        image_data_uri = _safe_embed_image_data_uri(image_path) or ""

    safe_title = escape_html(title or test_info.get("name", "") or "Evidence")
    safe_condition = escape_html(str(test_info.get("condition_ref", "")))
    safe_story = escape_html(str(test_info.get("story_ref", "")))

    # ── Plain-text bug report mode ─────────────────────────────────────
    if bug_report_mode:
        return _build_bug_report_text(sidecar_path, sidecar, image_data_uri)

    # ── HTML rendering ─────────────────────────────────────────────────
    steps_html = ""
    for step in steps:
        if not isinstance(step, dict):
            continue
        s = _build_step_html(step)
        steps_html += s

    if has_failure and failed_step:
        failure_html = _build_failure_panel_html(failed_step)
    else:
        failure_html = ""

    return f"""<div style="border:1px solid #e6e6e6;border-radius:10px;padding:14px;background:#fff;max-width:1100px;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
    <span style="font-size:24px;">{"❌" if has_failure else "✅"}</span>
    <div>
      <div style="font-weight:600;font-size:16px;color:#222;">{safe_title}</div>
      <div style="font-size:12px;color:#6b7280;">
        Condition: {safe_condition} · Story: {safe_story} · Status: <strong>{status}</strong>
      </div>
    </div>
  </div>

  {'<div style="margin-bottom:12px;padding:10px 14px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;color:#166534;font-size:13px;font-weight:500;">✅ All steps passed — the screenshot below is your evidence.</div>' if not has_failure else ""}

  <div style="position:relative;width:100%;">
    <img src="{image_data_uri}" alt="evidence screenshot" style="display:block;width:100%;height:auto;border-radius:8px;border:1px solid #eee;" {"onerror=\"this.style.display='none'\"" if not image_data_uri else ""} />
  </div>

  {failure_html}

  {steps_html if has_failure else ""}

  {_build_export_button_html(sidecar_path, title or safe_title, has_failure)}
</div>"""


# ── helpers ─────────────────────────────────────────────────────────────


def _empty_result(msg: str, bug_report_mode: bool) -> str:
    if bug_report_mode:
        return msg
    escaped = escape_html(msg)
    return f"<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>{escaped}</div>"


def _find_best_screenshot(steps: list[dict[str, Any]]) -> str:
    """Find the most informative screenshot from steps (prefer failure or last assertion)."""
    screenshots: list[str] = []
    failure_screenshots: list[str] = []
    assertion_screenshots: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        shot = step.get("screenshot")
        if not shot:
            continue
        shot_str = str(shot)
        screenshots.append(shot_str)
        if _is_failed_step(step):
            failure_screenshots.append(shot_str)
        step_type = str(step.get("type", "")).lower()
        if "assert" in step_type:
            assertion_screenshots.append(shot_str)
    if failure_screenshots:
        return failure_screenshots[0]
    if assertion_screenshots:
        return assertion_screenshots[-1]
    if screenshots:
        return screenshots[-1]
    return ""


def _is_failed_step(step: dict[str, Any]) -> bool:
    """Check if a step resulted in a failure."""
    result = step.get("result", {})
    if not isinstance(result, dict):
        return False
    return result.get("status") in ("failed", "error") or bool(result.get("error"))


def _build_step_html(step: dict[str, Any]) -> str:
    """Render a single step as an HTML row (only shown for failed tests)."""
    step_type = str(step.get("type", "unknown")).upper()
    label = _clean_evidence_label(str(step.get("label", "")))
    locator = str(step.get("locator", "")) if step.get("locator") else ""
    # value not used in this function
    result = step.get("result", {})
    if not isinstance(result, dict):
        result = {}
    status = str(result.get("status", ""))
    error = str(result.get("error", "")) if result.get("error") else ""
    matched = str(result.get("matched_text", "")) if result.get("matched_text") else ""
    failure_note = str(result.get("failure_note", "")) if result.get("failure_note") else ""

    is_failure = _is_failed_step(step)
    border_color = "#fecaca" if is_failure else "#e5e7eb"
    bg_color = "#fef2f2" if is_failure else "#ffffff"

    error_html = ""
    if error:
        error_html = f'<div style="margin-top:6px;padding:8px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;font-size:12px;color:#991b1b;white-space:pre-wrap;overflow-x:auto;"><strong>Error:</strong> {escape_html(error)}</div>'
    if failure_note and not error_html:
        error_html = f'<div style="margin-top:6px;padding:8px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;font-size:11px;color:#991b1b;max-height:150px;overflow-y:auto;white-space:pre-wrap;"><strong>Diagnosis:</strong> {escape_html(failure_note)}</div>'

    details = f"type={step_type.lower()}"
    if status:
        details += f" · status={status}"
    if locator:
        details += f" · locator=`{escape_html(locator)}`"
    if matched:
        text = re.sub(r"\s+", " ", matched).strip()
        if len(text) > 80:
            text = text[:80] + "..."
        details += f' · found="{escape_html(text)}"'

    return f"""
<div style="display:flex;gap:10px;align-items:flex-start;padding:10px;border:1px solid {border_color};border-radius:8px;margin-bottom:8px;background:{bg_color};">
  <div style="min-width:28px;height:28px;border-radius:999px;background:{"#dc2626" if is_failure else "#6b7280"};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;">!</div>
  <div style="flex:1;">
    <div style="font-weight:600;color:#222;font-size:13px;">{escape_html(label)}</div>
    <div style="font-size:11px;color:#6b7280;font-family:monospace;">{details}</div>
    {error_html}
  </div>
</div>"""


def _build_failure_panel_html(failed_step: dict[str, Any]) -> str:
    """Build the failure diagnosis panel shown below the screenshot for failed tests."""
    result = failed_step.get("result", {})
    if not isinstance(result, dict):
        return ""
    failure_note = str(result.get("failure_note", ""))
    diagnosis_raw = result.get("diagnosis", {})
    if isinstance(diagnosis_raw, dict):
        suggested_locators = diagnosis_raw.get("suggested_locators", [])
    else:
        suggested_locators = []

    step_type = str(failed_step.get("type", "unknown")).upper()
    label = _clean_evidence_label(str(failed_step.get("label", "")))
    locator = str(failed_step.get("locator", "")) if failed_step.get("locator") else "N/A"
    error = str(result.get("error", "")) if result.get("error") else "Unknown error"

    # Build suggested locators section
    suggestions_html = ""
    if suggested_locators:
        rows = ""
        for s in suggested_locators[:5]:
            loc = s.get("locator", "")
            score = s.get("score", "")
            confidence = s.get("confidence", "")
            rows += f"""<tr>
              <td style="padding:4px 8px;font-family:monospace;font-size:12px;border-bottom:1px solid #f0f0f0;"><code>{escape_html(loc)}</code></td>
              <td style="padding:4px 8px;font-size:12px;border-bottom:1px solid #f0f0f0;">{escape_html(str(score))}</td>
              <td style="padding:4px 8px;font-size:12px;border-bottom:1px solid #f0f0f0;">{escape_html(confidence)}</td>
            </tr>"""
        if rows:
            suggestions_html = f"""
<div style="margin:12px 0 0 0;padding:10px;background:#fafafa;border:1px solid #e5e7eb;border-radius:8px;">
  <div style="font-weight:600;font-size:13px;color:#222;margin-bottom:6px;">Suggested Alternative Locators</div>
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr>
      <th style="padding:4px 8px;font-size:11px;color:#6b7280;text-align:left;border-bottom:2px solid #e5e7eb;">Locator</th>
      <th style="padding:4px 8px;font-size:11px;color:#6b7280;text-align:left;border-bottom:2px solid #e5e7eb;">Score</th>
      <th style="padding:4px 8px;font-size:11px;color:#6b7280;text-align:left;border-bottom:2px solid #e5e7eb;">Confidence</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""

    # Build failure note / diagnosis text
    diagnosis_html = ""
    if failure_note:
        diagnosis_html = f"""<div style="margin:12px 0 0 0;padding:10px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;">
  <div style="font-weight:600;font-size:13px;color:#991b1b;margin-bottom:4px;">Failure Diagnosis</div>
  <pre style="margin:0;font-size:11px;color:#991b1b;white-space:pre-wrap;max-height:200px;overflow-y:auto;">{escape_html(failure_note)}</pre>
</div>"""

    return f"""
<div style="margin-top:14px;padding:14px;background:#fff;border:1px solid #e5e7eb;border-radius:10px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
    <span style="font-size:18px;">❌</span>
    <span style="font-weight:600;font-size:15px;color:#dc2626;">Step Failed: {escape_html(label)}</span>
  </div>

  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <tr><td style="padding:6px 8px;color:#6b7280;width:100px;">Step Type</td><td style="padding:6px 8px;font-weight:500;"><code>{escape_html(step_type)}</code></td></tr>
    <tr><td style="padding:6px 8px;color:#6b7280;">Locator</td><td style="padding:6px 8px;font-weight:500;font-family:monospace;font-size:12px;word-break:break-all;">{escape_html(locator)}</td></tr>
    <tr><td style="padding:6px 8px;color:#6b7280;">Error</td><td style="padding:6px 8px;color:#dc2626;font-size:12px;white-space:pre-wrap;">{escape_html(error)}</td></tr>
  </table>

  {diagnosis_html}
  {suggestions_html}
</div>"""


def _build_export_button_html(sidecar_path: Path, title: str, has_failure: bool) -> str:
    """Build an inline export section for the bug report."""
    report_label = "Bug Report" if has_failure else "Evidence Summary"
    return f"""
<div style="margin-top:14px;padding:12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;display:flex;align-items:center;justify-content:space-between;">
  <div style="font-size:13px;color:#374151;">
    <strong>{report_label}</strong> — Content is ready for copy-paste.
    Click below to select all and copy into your issue tracker.
  </div>
  <button onclick="(function(){{var t=document.getElementById('ev-bug-text');t.style.display=t.style.display==='none'?'block':'none';t.select();navigator.clipboard.writeText(t.value);}})()" style="padding:6px 14px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:500;">📋 Copy Bug Report</button>
</div>
<textarea id="ev-bug-text" style="display:none;width:100%;margin-top:8px;padding:10px;border:1px solid #e5e7eb;border-radius:6px;font-family:monospace;font-size:11px;height:200px;white-space:pre-wrap;" readonly>
{escape_html(_build_bug_report_text(sidecar_path, _safe_read_json(sidecar_path) or {}, "", title))}
</textarea>"""


def _build_bug_report_text(
    sidecar_path: Path,
    sidecar: dict[str, Any],
    image_data_uri: str = "",
    title: str = "",
) -> str:
    """Build a plain-text bug report from the evidence sidecar."""
    test_info = sidecar.get("test", {})
    if not isinstance(test_info, dict):
        test_info = {}
    steps = sidecar.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    status = str(test_info.get("status", "unknown"))
    name = title or str(test_info.get("name", "unknown"))
    condition_ref = str(test_info.get("condition_ref", "N/A"))
    story_ref = str(test_info.get("story_ref", "N/A"))

    lines = [
        "=" * 72,
        f"  {'BUG REPORT' if status in ('failed', 'error') else 'EVIDENCE SUMMARY'}",
        "=" * 72,
        "",
        f"  Test:          {name}",
        f"  Condition:     {condition_ref}",
        f"  Story:         {story_ref}",
        f"  Status:        {status}",
        f"  Sidecar:       {sidecar_path}",
        "",
    ]

    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type", "unknown")).upper()
        label = _clean_evidence_label(str(step.get("label", "")))
        locator = str(step.get("locator", "")) if step.get("locator") else ""
        result = step.get("result", {})
        if not isinstance(result, dict):
            result = {}
        step_status = str(result.get("status", ""))
        error = str(result.get("error", "")) if result.get("error") else ""

        lines.append(f"  Step {i}: [{step_type}] {label}")
        if locator:
            lines.append(f"    Locator:     {locator}")
        lines.append(f"    Status:      {step_status}")
        if _is_failed_step(step):
            lines.append(f"    Error:       {error}")
            failure_note = str(result.get("failure_note", ""))
            if failure_note:
                # Compact the diagnosis
                for note_line in failure_note.splitlines():
                    lines.append(f"    {note_line}")

    lines.append("")
    lines.append("=" * 72)
    lines.append("  END OF REPORT")
    lines.append("=" * 72)

    return "\n".join(lines)


# ── Evidence listing ────────────────────────────────────────────────────


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
