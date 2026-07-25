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

# Badge colours (text, background) keyed by step type
_BADGE_COLORS: dict[str, tuple[str, str]] = {
    "navigate": ("#6d28d9", "#ede9fe"),
    "fill": ("#065f46", "#d1fae5"),
    "click": ("#1e40af", "#dbeafe"),
    "assertion": ("#92400e", "#fef3c7"),
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
        text = re.sub(r"\s+", " ", text)
        if len(text) > truncate:
            text = text[:truncate] + "..."
        if text:
            return f'{cleaned}: "{text}"'
    return cleaned


def _is_failed_step(step: dict[str, Any]) -> bool:
    """Check if a step resulted in a failure."""
    result = step.get("result", {})
    if not isinstance(result, dict):
        return False
    return result.get("status") in ("failed", "error") or bool(result.get("error"))


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


def _step_type_key(step: dict[str, Any]) -> str:
    t = str(step.get("type", "")).lower()
    if "navigate" in t:
        return "navigate"
    if "fill" in t:
        return "fill"
    if "assert" in t:
        return "assertion"
    return "click"


def _build_step_row_html(step: dict[str, Any], idx: int) -> str:
    """Render a single step as a compact timeline row."""
    type_key = _step_type_key(step)
    label = _clean_evidence_label(str(step.get("label", "")))
    locator = str(step.get("locator", "")) if step.get("locator") else ""
    result = step.get("result", {}) if isinstance(step.get("result"), dict) else {}
    status = str(result.get("status", ""))
    error = str(result.get("error", "")) if result.get("error") else ""
    elapsed_ms = result.get("elapsed_ms")
    elapsed_str = f"{elapsed_ms / 1000:.1f}s" if elapsed_ms else ""
    matched_text = str(result.get("matched_text", "")) if result.get("matched_text") else ""

    diagnosis_raw = result.get("diagnosis", {})
    suggested_locators: list[dict[str, Any]] = (
        diagnosis_raw.get("suggested_locators", []) if isinstance(diagnosis_raw, dict) else []
    )

    is_failure = _is_failed_step(step)
    badge_fg, badge_bg = _BADGE_COLORS.get(type_key, ("#374151", "#f3f4f6"))
    row_bg = "#fef2f2" if is_failure else "#ffffff"
    row_border = "#fca5a5" if is_failure else "#f3f4f6"

    # ── meta pill row ─────────────────────────────────────────────────
    status_html = ""
    if status:
        status_color = "#dc2626" if status in ("failed", "error") else "#16a34a"
        status_html = (
            f"<span style='color:{status_color};font-weight:600;font-size:11px;'>{escape_html(status)}</span> · "
        )

    locator_html = ""
    if locator:
        locator_html = f"<code style='font-size:11px;background:#f3f4f6;padding:1px 4px;border-radius:3px;color:#374151;'>{escape_html(locator)}</code> · "

    matched_html = ""
    if matched_text and not is_failure:
        short = re.sub(r"\s+", " ", matched_text).strip()[:60]
        matched_html = f"found <em style='color:#374151;'>&ldquo;{escape_html(short)}&rdquo;</em> · "

    elapsed_html = f"<span style='color:#9ca3af;font-size:11px;'>{elapsed_str}</span>" if elapsed_str else ""

    meta_html = f"""
    <div style='margin-top:3px;font-size:11px;color:#6b7280;display:flex;flex-wrap:wrap;align-items:center;gap:2px;'>
      <code style='background:#f3f4f6;padding:1px 4px;border-radius:3px;'>{escape_html(type_key)}</code> ·
      {status_html}{locator_html}{matched_html}{elapsed_html}
    </div>"""

    # ── failure detail ────────────────────────────────────────────────
    failure_html = ""
    if is_failure:
        # Error box — truncate long messages (call logs etc.)
        lines = error.splitlines()
        if len(lines) > 8:
            shown = "\n".join(lines[:8]) + f"\n… ({len(lines) - 8} more lines)"
        else:
            shown = error

        failure_html += f"""
        <div style='margin-top:8px;padding:10px 12px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;'>
          <div style='font-weight:600;font-size:12px;color:#991b1b;margin-bottom:4px;'>Error</div>
          <pre style='margin:0;font-size:11px;color:#b91c1c;white-space:pre-wrap;overflow-x:auto;max-height:100px;overflow-y:auto;'>{escape_html(shown)}</pre>
        </div>"""

        # Suggested locators — copyable
        visible_locators = [s for s in suggested_locators[:5] if s.get("locator")]
        if visible_locators:
            loc_rows = ""
            for sl in visible_locators:
                loc = sl.get("locator", "")
                confidence = sl.get("confidence", "")
                loc_js = loc.replace("\\", "\\\\").replace("'", "\\'")
                loc_rows += f"""
                <div style='display:flex;align-items:center;gap:8px;padding:5px 8px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:5px;margin-bottom:4px;'>
                  <code style='flex:1;font-size:12px;color:#1e40af;word-break:break-all;'>{escape_html(loc)}</code>
                  <span style='font-size:11px;color:#6b7280;background:#e5e7eb;padding:1px 7px;border-radius:10px;white-space:nowrap;'>{escape_html(str(confidence))}</span>
                  <button onclick="navigator.clipboard.writeText('{loc_js}').then(()=>{{this.textContent='✓ Copied';setTimeout(()=>{{this.textContent='📋 Copy'}},1500)}})"
                          style='padding:3px 10px;background:#2563eb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;white-space:nowrap;'>
                    📋 Copy
                  </button>
                </div>"""

            failure_html += f"""
            <div style='margin-top:8px;'>
              <div style='font-weight:600;font-size:12px;color:#374151;margin-bottom:6px;'>
                💡 Suggested locators — copy one to fix your test:
              </div>
              {loc_rows}
            </div>"""

    return f"""
<div style='display:flex;gap:10px;align-items:flex-start;padding:10px;border:1px solid {row_border};border-radius:8px;margin-bottom:6px;background:{row_bg};'>
  <div style='min-width:28px;height:28px;border-radius:999px;background:{badge_bg};color:{badge_fg};display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;flex-shrink:0;'>
    {idx + 1}
  </div>
  <div style='flex:1;min-width:0;'>
    <div style='font-weight:600;color:#111;font-size:13px;word-break:break-word;'>{escape_html(label)}</div>
    {meta_html}
    {failure_html}
  </div>
</div>"""


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

      let rowContent = `
        <div style="min-width:30px;height:30px;border-radius:999px;background:${{hasError ? "#dc2626" : COLORS[t] || "#999"}};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;">${{idx + 1}}</div>
        <div style="flex:1;">
          <div style="font-weight:600;color:#222;">${{label}}</div>
          <div style="font-size:12px;color:#666;">type=${{t}} · status=${{status}} · run_count=${{runCount}}</div>
      `;

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
      const status = String((s.result && s.result.status) || "");
      const label = String(s.label || t);

      if (MODE === "clean") {{ return; }}

      if (MODE === "heatmap") {{
        const opacity = Math.min(0.15 + (Number(runCount || 1) * 0.05), 0.6);
        out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="6" opacity="${{opacity}}" />`);
        out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{Math.max(6, r - 10)}}" fill="none" stroke="${{color}}" stroke-width="2" opacity="${{opacity}}" />`);
        return;
      }}

      const stroke = isHover ? "#111827" : "rgba(0,0,0,0.35)";
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
    bug_report_mode: bool = False,
) -> str:
    """Generate a focused evidence viewer for debugging.

    Shows a step-by-step journey timeline, then the most informative
    screenshot at the bottom. For failed steps, inline error details and
    copyable suggested locators are shown directly in the timeline row.

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
    page_info = sidecar.get("page", {})
    if not isinstance(page_info, dict):
        page_info = {}
    if not isinstance(steps, list) or not steps:
        return _empty_result("No steps recorded in sidecar.", bug_report_mode)

    if bug_report_mode:
        return _build_bug_report_text(sidecar_path, sidecar, "", title)

    has_failure = any(_is_failed_step(s) for s in steps if isinstance(s, dict))

    # ── screenshot ────────────────────────────────────────────────────────
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
    safe_url = escape_html(str(page_info.get("url", "")))

    status_badge = (
        "<span style='background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px;'>FAILED</span>"
        if has_failure
        else "<span style='background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px;'>PASSED</span>"
    )
    icon = "❌" if has_failure else "✅"

    # ── step timeline ─────────────────────────────────────────────────────
    steps_html = ""
    for i, step in enumerate(steps):
        if isinstance(step, dict):
            steps_html += _build_step_row_html(step, i)

    # ── screenshot section ────────────────────────────────────────────────
    screenshot_html = ""
    if image_data_uri:
        screenshot_label = (
            "Screenshot captured at the point of failure" if has_failure else "Final page screenshot (all steps passed)"
        )
        screenshot_html = f"""
<div style="margin-top:16px;padding-top:14px;border-top:1px solid #f3f4f6;">
  <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">{escape_html(screenshot_label)}</div>
  <img src="{image_data_uri}" alt="evidence screenshot" style="display:block;width:100%;height:auto;border-radius:8px;border:1px solid #e5e7eb;" />
</div>"""

    success_banner = (
        ""
        if has_failure
        else "<div style='margin-bottom:12px;padding:10px 14px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;color:#166534;font-size:13px;font-weight:500;'>✅ All steps passed — the screenshot below is your evidence.</div>"
    )

    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;border:1px solid #e5e7eb;border-radius:12px;padding:16px;background:#fff;max-width:1100px;">

  <!-- Header -->
  <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #f3f4f6;">
    <span style="font-size:22px;line-height:1.2;">{icon}</span>
    <div style="min-width:0;flex:1;">
      <div style="font-weight:700;font-size:15px;color:#111;word-break:break-word;">{safe_title}</div>
      <div style="margin-top:4px;display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-size:12px;color:#6b7280;">
        {status_badge}
        <span>Condition: <strong>{safe_condition}</strong></span>
        <span>·</span>
        <span>Story: {safe_story}</span>
        {f"<span>·</span><span>{safe_url}</span>" if safe_url else ""}
      </div>
    </div>
  </div>

  {success_banner}

  <!-- Step Timeline -->
  <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">
    Step Journey ({len(steps)} steps)
  </div>
  <div>
    {steps_html}
  </div>

  <!-- Screenshot -->
  {screenshot_html}
</div>"""


# ── helpers ──────────────────────────────────────────────────────────────────


def _empty_result(msg: str, bug_report_mode: bool) -> str:
    if bug_report_mode:
        return msg
    escaped = escape_html(msg)
    return f"<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>{escaped}</div>"


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
        result = step.get("result", {})
        if isinstance(result, dict):
            cloned["failure_note"] = result.get("failure_note")
            cloned["diagnosis"] = result.get("diagnosis")
            if result.get("error") and not result.get("status"):
                cloned["_had_error"] = True
        prepared.append(cloned)
    return prepared


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
                for note_line in failure_note.splitlines():
                    lines.append(f"    {note_line}")

    lines.append("")
    lines.append("=" * 72)
    lines.append("  END OF REPORT")
    lines.append("=" * 72)

    return "\n".join(lines)


# ── Evidence listing ─────────────────────────────────────────────────────────


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

        screenshots = [str(s.get("screenshot", "")) for s in steps if isinstance(s, dict) and s.get("screenshot")]
        has_fallback = any(str(s.get("locator", "")).startswith("{{{{") for s in steps if isinstance(s, dict))
        has_failure = any(_is_failed_step(s) for s in steps if isinstance(s, dict))

        duration_s = 0.0
        for s in steps:
            if isinstance(s, dict):
                result = s.get("result", {})
                if isinstance(result, dict):
                    ms = result.get("elapsed_ms")
                    if ms:
                        duration_s += float(ms) / 1000

        total_steps += len(steps)
        total_screenshots += len(screenshots)

        if status == "passed":
            passed += 1
        elif status in ("failed", "error"):
            failed += 1
        elif status == "partial_pass":
            partial_pass += 1
        else:
            skipped += 1

        tests.append(
            EvidenceFile(
                test_name=str(test_info.get("name", sidecar.stem)),
                sidecar_path=sidecar,
                condition_ref=str(test_info.get("condition_ref", "")),
                story_ref=str(test_info.get("story_ref", "")),
                status=status,
                duration_s=duration_s,
                step_count=len(steps),
                has_fallback=has_fallback,
                has_failure=has_failure,
                screenshots=screenshots,
            )
        )

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
