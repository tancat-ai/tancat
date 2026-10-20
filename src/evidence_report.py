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

    # AI-067: a step can pass while running on a page other than the one its
    # locator was resolved against. That is a silent sequence difference, so it
    # gets a visible marker instead of a plain green row.
    mismatch_html = ""
    mismatch = result.get("page_mismatch")
    if isinstance(mismatch, dict) and mismatch:
        expected_url = escape_html(str(mismatch.get("expected", "")))
        actual_url = escape_html(str(mismatch.get("actual", "")))
        mismatch_html = (
            f" · <span title='resolved for {expected_url}, ran on {actual_url}' "
            "style='color:#b45309;background:#fef3c7;border:1px solid #fcd34d;"
            "padding:1px 6px;border-radius:10px;font-weight:600;font-size:10px;'>"
            "wrong page</span>"
        )

    meta_html = f"""
    <div style='margin-top:3px;font-size:11px;color:#6b7280;display:flex;flex-wrap:wrap;align-items:center;gap:2px;'>
      <code style='background:#f3f4f6;padding:1px 4px;border-radius:3px;'>{escape_html(type_key)}</code> ·
      {status_html}{locator_html}{matched_html}{elapsed_html}{mismatch_html}
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


# ---------------------------------------------------------------------------
# Frame matching (B-105)
#
# A marker's percentage is only meaningful against the document it was
# measured in. The page height changes between steps (a newsletter bar
# appears, a cart modal opens), so a percentage drawn on a frame of a
# different height lands on a different element — in the flagship demo that
# put a "View Product" marker on another card's "Add to cart" button.
# ---------------------------------------------------------------------------


def _as_int(value: Any) -> int | None:
    """Return *value* as an int, or None when it is not a usable number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


@dataclass(frozen=True)
class EvidenceFrame:
    """One captured page state: the screenshot plus the document it shows."""

    rel_path: str
    url: str
    doc_width: int | None
    doc_height: int | None
    step_index: int


@dataclass(frozen=True)
class FrameMatch:
    """Where a marker may be drawn, and whether that placement is confirmed."""

    frame: EvidenceFrame | None
    verified: bool
    reason: str


def build_evidence_frames(steps: list[dict[str, Any]]) -> list[EvidenceFrame]:
    """Return one frame per distinct screenshot recorded in *steps*.

    Two steps that share a screenshot share a frame. The frame carries the
    URL it shows and the size of the document it captured, so a marker can be
    matched to the frame it was measured in.
    """
    frames: list[EvidenceFrame] = []
    seen: set[str] = set()
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        shot = str(step.get("screenshot") or "")
        if not shot or shot in seen:
            continue
        seen.add(shot)
        frames.append(
            EvidenceFrame(
                rel_path=shot,
                url=_normalise_url(str(step.get("frame_url") or step.get("url") or "")),
                doc_width=_as_int(step.get("frame_doc_width")),
                doc_height=_as_int(step.get("frame_doc_height")),
                step_index=idx,
            )
        )
    return frames


def match_frame(
    frames: list[EvidenceFrame],
    *,
    doc_width: int | None,
    doc_height: int | None,
    own_rel_path: str = "",
    step_index: int = 0,
) -> FrameMatch:
    """Return the frame a marker measured in that document may be drawn on.

    When the sidecar records the document size, only a frame of exactly that
    size is a legal target: the marker's percentage is relative to the
    document it was measured in, and nothing else. When the sidecar does not
    record it (written before the frame sizes were captured) the step's own
    frame is used and the match is reported as unverified, so the caller can
    say so. A wrong marker is worse than no marker.
    """
    if doc_width is None or doc_height is None:
        own = next((f for f in frames if f.rel_path == own_rel_path), None)
        if own is None:
            return FrameMatch(None, False, "this step has no captured frame")
        return FrameMatch(
            own,
            False,
            "the sidecar does not record the size of the frame, so the frame could not be confirmed",
        )

    candidates = [f for f in frames if f.doc_width == doc_width and f.doc_height == doc_height]
    if not candidates:
        return FrameMatch(
            None,
            False,
            "no captured frame shows the page this step was measured on, so no marker could be placed",
        )
    own = next((f for f in candidates if f.rel_path == own_rel_path), None)
    if own is not None:
        return FrameMatch(own, True, "")
    earlier = [f for f in candidates if f.step_index <= step_index]
    return FrameMatch(earlier[-1] if earlier else candidates[0], True, "")


def _resolve_evidence_image(sidecar_path: Path, rel_path: str) -> Path:
    """Resolve a screenshot path recorded in a sidecar to a file on disk."""
    if rel_path.startswith("evidence/"):
        return (sidecar_path.parent.parent / rel_path).resolve()
    return (sidecar_path.parent / rel_path).resolve()


def _build_overlay_model(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Work out which captured frame every step's marker belongs on.

    Returns the frames, the markers that may be drawn, the failure ribbons
    and the per-step note. A failed step that never located its element has
    no position to mark, so it gets a ribbon on its own frame instead of a
    marker: the picture must still say the step failed.
    """
    frames = build_evidence_frames(steps)
    frame_ids = {f.rel_path: f"f{i}" for i, f in enumerate(frames)}
    frame_meta: list[dict[str, Any]] = []
    for i, frame in enumerate(frames):
        step_type = ""
        if 0 <= frame.step_index < len(steps):
            candidate = steps[frame.step_index]
            if isinstance(candidate, dict):
                step_type = _step_type_key(candidate)
        frame_meta.append(
            {
                "id": f"f{i}",
                "rel_path": frame.rel_path,
                "step_index": frame.step_index,
                "label": f"Frame {i + 1} - captured at step {frame.step_index + 1} ({step_type})",
                "has_failure": False,
            }
        )
    meta_by_id = {f["id"]: f for f in frame_meta}

    markers: list[dict[str, Any]] = []
    ribbons: dict[str, list[dict[str, Any]]] = {}
    notes: dict[int, str] = {}

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        raw_element = step.get("element")
        element: dict[str, Any] = raw_element if isinstance(raw_element, dict) else {}
        pct = element.get("viewport_pct")
        failed = _is_failed_step(step)
        own_rel = str(step.get("screenshot") or "")
        own_frame = frame_ids.get(own_rel, "")

        if not isinstance(pct, dict) or pct.get("x") is None or pct.get("y") is None:
            if failed:
                notes[idx] = "this step failed before the element was located, so there is no position to mark"
                if own_frame:
                    ribbons.setdefault(own_frame, []).append(
                        {"step": idx + 1, "label": str(step.get("label") or step.get("type") or "step")}
                    )
                    meta_by_id[own_frame]["has_failure"] = True
            else:
                notes[idx] = "no element position was recorded for this step"
            continue

        match = match_frame(
            frames,
            doc_width=_as_int(element.get("doc_width")),
            doc_height=_as_int(element.get("doc_height")),
            own_rel_path=own_rel,
            step_index=idx,
        )
        if match.frame is None:
            notes[idx] = match.reason
            continue

        frame_id = frame_ids[match.frame.rel_path]
        raw_result = step.get("result")
        result: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
        markers.append(
            {
                "step": idx,
                "frame": frame_id,
                "x": float(pct.get("x") or 0.0),
                "y": float(pct.get("y") or 0.0),
                "type": _step_type_key(step),
                "status": str(result.get("status") or "passed"),
                "failed": failed,
                "verified": match.verified,
                "run_count": int(result.get("run_count") or 1),
                "label": _clean_evidence_label(str(step.get("label") or "")),
                "locator": str(step.get("locator") or ""),
            }
        )
        if failed:
            meta_by_id[frame_id]["has_failure"] = True
        if not match.verified:
            notes[idx] = match.reason

    return {"frames": frame_meta, "markers": markers, "ribbons": ribbons, "notes": notes}


def generate_annotated_screenshot(
    *,
    sidecar_path: Path,
    view_mode: Literal["annotated", "heatmap", "clean"] = "annotated",
    title: str = "",
) -> str:
    """Return interactive HTML for an annotated evidence screenshot.

    Every marker is drawn on the frame it was measured in. A marker's
    percentage is only meaningful against the document it was measured in —
    the page height changes between steps (a newsletter bar appears, a cart
    modal opens), so drawing every step's marker on one background frame puts
    markers on the wrong element (B-105). When the frame cannot be confirmed
    the marker is not drawn and the timeline says why: a wrong marker is
    worse than no marker.
    """

    sidecar = _safe_read_json(sidecar_path)
    if sidecar is None:
        escaped = escape_html(str(sidecar_path))
        return f"<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>Missing sidecar: <code>{escaped}</code></div>"

    steps = sidecar.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return "<div style='padding:12px;border:1px solid #eee;border-radius:8px;'>No steps recorded in sidecar.</div>"

    model = _build_overlay_model(steps)

    used_frames = {m["frame"] for m in model["markers"]}
    used_frames |= set(model["ribbons"])
    if not used_frames:
        # Nothing could be marked, but the reader still gets the frames and
        # the reason in the step list.
        used_frames = {f["id"] for f in model["frames"]}

    frame_blocks: list[str] = []
    for frame in model["frames"]:
        if frame["id"] not in used_frames:
            continue
        image_data_uri = _safe_embed_image_data_uri(_resolve_evidence_image(sidecar_path, frame["rel_path"]))
        if not image_data_uri:
            continue
        border = "#fca5a5" if frame["has_failure"] else "#eee"
        ribbon_html = ""
        for ribbon in model["ribbons"].get(frame["id"], []):
            ribbon_html += (
                "<div style='display:inline-block;margin:0 6px 6px 0;padding:4px 10px;background:#fef2f2;"
                "border:1px solid #fca5a5;border-radius:6px;color:#991b1b;font-size:11px;font-weight:700;'>"
                f"Step {ribbon['step']} failed - no element position was recorded, so no marker could be placed"
                "</div>"
            )
        frame_blocks.append(
            f"""
  <div class="ev-frame" data-frame-id="{frame["id"]}" style="margin-bottom:16px;">
    <div style="font-size:11px;color:#6b7280;font-weight:600;margin-bottom:4px;">{escape_html(frame["label"])}</div>
    <div class="ev-wrap" style="position:relative;width:100%;max-width:1100px;">
      <img class="ev-img" data-frame-id="{frame["id"]}" src="{image_data_uri}" alt="evidence screenshot" style="display:block;width:100%;height:auto;border-radius:8px;border:1px solid {border};" />
      <svg class="ev-svg" data-frame-id="{frame["id"]}" style="position:absolute;left:0;top:0;pointer-events:none;"></svg>
      {ribbon_html}
    </div>
  </div>"""
        )

    test_block = sidecar.get("test", {}) if isinstance(sidecar.get("test", {}), dict) else {}
    page_block = sidecar.get("page", {}) if isinstance(sidecar.get("page", {}), dict) else {}
    safe_title = escape_html(title or test_block.get("name", "") or "Evidence")
    safe_url = escape_html(str(page_block.get("url", "")))
    mode = view_mode

    mode_json = json.dumps(mode)
    colors_json = json.dumps(_EVIDENCE_STEP_COLORS)
    status_colors_json = json.dumps(_STATUS_COLORS)
    steps_json = json.dumps(_prepare_steps_for_display(steps, model["notes"]))
    markers_json = json.dumps(model["markers"])
    frames_json = json.dumps(model["frames"])

    return f"""
<div style="border:1px solid #e6e6e6;border-radius:10px;padding:14px;background:#fff;">
  <div style="font-weight:600;margin-bottom:10px;">{safe_title}</div>
  <div style="color:#6b7280;font-size:12px;margin:-6px 0 10px 0;">{safe_url}</div>
  <div id="ev-frames">
{"".join(frame_blocks)}
  </div>

  <div style="display:flex;gap:10px;align-items:center;margin-top:10px;color:#555;font-size:12px;flex-wrap:wrap;">
    <span><strong>Mode</strong>: {escape_html(mode)}</span>
    <span style="margin-left:auto;"><strong>Legend</strong>:
      <span style="color:{_EVIDENCE_STEP_COLORS["navigate"]};font-weight:700;">navigate</span>,
      <span style="color:{_EVIDENCE_STEP_COLORS["fill"]};font-weight:700;">fill</span>,
      <span style="color:{_EVIDENCE_STEP_COLORS["click"]};font-weight:700;">click</span>,
      <span style="color:{_EVIDENCE_STEP_COLORS["assertion"]};font-weight:700;">assertion</span>,
      <span style="color:{_STATUS_COLORS["failed"]};font-weight:700;">failed</span>,
      <span style="color:{_STATUS_COLORS["partial_pass"]};font-weight:700;">partial</span>
    </span>
  </div>
  <div style="font-size:11px;color:#6b7280;margin-top:4px;">
    Each marker sits on the frame its step was measured on. A dashed ring means the sidecar
    does not record the frame size, so the frame could not be confirmed. A step with no marker
    says why in the list below.
  </div>

  <div id="ev-timeline" style="margin-top:12px;border-top:1px solid #f0f0f0;padding-top:12px;">
  </div>
</div>

<script>
(() => {{
  const MODE = {mode_json};
  const COLORS = {colors_json};
  const STATUS_COLORS = {status_colors_json};
  const steps = {steps_json};
  const markers = {markers_json};
  const frames = {frames_json};

  const timeline = document.getElementById("ev-timeline");
  let hoveredId = null;

  // Step labels and failure notes are free text (site copy, error logs).
  // They go through innerHTML below, so escape them — an unescaped "<" in a
  // label broke the timeline row markup (and could inject HTML into the report).
  function esc(v) {{
    return String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }}

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

  function markerColor(marker) {{
    if (marker.failed) return STATUS_COLORS.failed;
    if (marker.status === "partial_pass") return STATUS_COLORS.partial_pass;
    if (marker.status === "skipped") return STATUS_COLORS.skipped;
    return COLORS[marker.type] || "#999";
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
      const markerNote = String(s.marker_note || "");

      let rowContent = `
        <div style="min-width:30px;height:30px;border-radius:999px;background:${{hasError ? "#dc2626" : COLORS[t] || "#999"}};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;">${{idx + 1}}</div>
        <div style="flex:1;">
          <div style="font-weight:600;color:#222;">${{esc(label)}}</div>
          <div style="font-size:12px;color:#666;">type=${{esc(t)}} · status=${{esc(status)}} · run_count=${{esc(runCount)}}</div>
      `;

      if (markerNote) {{
        rowContent += `
          <div style="margin-top:4px;font-size:11px;color:#b45309;">${{esc(markerNote)}}</div>
        `;
      }}

      if (failureNote) {{
        rowContent += `
          <div style="margin-top:6px;padding:8px;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;font-size:11px;color:#991b1b;max-height:120px;overflow-y:auto;white-space:pre-wrap;">
            <strong>Failure Diagnosis:</strong><br/>
            <pre style="white-space:pre-wrap;margin:0;">${{esc(failureNote)}}</pre>
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
    document.querySelectorAll("svg.ev-svg").forEach((svg) => {{
      const frameId = svg.getAttribute("data-frame-id");
      const img = document.querySelector(`img.ev-img[data-frame-id="${{frameId}}"]`);
      if (!img) return;
      const rect = img.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      if (!w || !h) return;
      svg.setAttribute("width", String(w));
      svg.setAttribute("height", String(h));
      svg.setAttribute("viewBox", `0 0 ${{w}} ${{h}}`);
      svg.style.pointerEvents = "none";

      const out = [];
      markers.forEach((m) => {{
        if (m.frame !== frameId) return;
        if (MODE === "clean") return;
        const color = markerColor(m);
        const r = baseRadius(m.run_count);
        const cx = (Number(m.x) / 100) * w;
        const cy = (Number(m.y) / 100) * h;
        const isHover = hoveredId === m.step;

        if (MODE === "heatmap") {{
          const opacity = Math.min(0.15 + (Number(m.run_count || 1) * 0.05), 0.6);
          out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="6" opacity="${{opacity}}" />`);
          out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{Math.max(6, r - 10)}}" fill="none" stroke="${{color}}" stroke-width="2" opacity="${{opacity}}" />`);
          return;
        }}

        const dash = m.verified ? "" : ` stroke-dasharray="7 5"`;
        let glyph = "";
        if (m.failed) {{
          glyph = `<path d="M ${{cx - 7}} ${{cy - 7}} L ${{cx + 7}} ${{cy + 7}} M ${{cx + 7}} ${{cy - 7}} L ${{cx - 7}} ${{cy + 7}}" stroke="#7F1D1D" stroke-width="3" fill="none" />`;
        }} else {{
          glyph = `<text x="${{cx}}" y="${{cy + 6}}" font-size="16" font-weight="900" fill="white" text-anchor="middle" style="pointer-events:none; filter: drop-shadow(0px 0px 2px rgba(0,0,0,0.8));">${{m.step + 1}}</text>`;
        }}

        out.push(`
        <g class="point-group" style="cursor:help;">
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="${{color}}" opacity="0.4" />
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="white" stroke-width="3" opacity="0.9" />
          <circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="1.5" opacity="0.9"${{dash}} />
          ${{glyph}}
          <title>${{esc(m.label)}}${{m.failed ? " (FAILED)" : ""}} (status: ${{esc(m.status)}})</title>
        </g>
      `);
      }});

      svg.innerHTML = out.join("");
    }});
  }}

  const ro = new ResizeObserver(() => renderOverlay());
  ro.observe(document.getElementById("ev-frames"));
  document.querySelectorAll("img.ev-img").forEach((img) => {{
    img.addEventListener("load", () => renderOverlay());
  }});

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


def _prepare_steps_for_display(
    steps: list[dict[str, Any]],
    notes: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Return steps with labels normalized for UI rendering.

    Also extracts failure_note and diagnosis from the result dict when present,
    and the per-step marker note (why a marker is missing or unconfirmed).
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
        cloned["marker_note"] = (notes or {}).get(len(prepared), "")
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
        # Mismatch failures carry error=None; str(None) would print "None".
        error = str(result.get("error") or "")

        lines.append(f"  Step {i}: [{step_type}] {label}")
        if locator:
            lines.append(f"    Locator:     {locator}")
        lines.append(f"    Status:      {step_status}")
        if _is_failed_step(step):
            if error:
                lines.append(f"    Error:       {error}")
            failure_note = str(result.get("failure_note") or "")
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
