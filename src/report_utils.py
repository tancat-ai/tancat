from __future__ import annotations

import base64
import html as _html
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from src.pytest_output_parser import RunResult, TestResult

_EVIDENCE_STEP_COLORS: dict[str, str] = {
    "navigate": "#993556",
    "fill": "#0F6E56",
    "click": "#185FA5",
    "assertion": "#854F0B",
}


def escape_html(text: str) -> str:
    """Escape HTML special characters for safe embedding in HTML documents.

    Args:
        text: Raw text to escape

    Returns:
        HTML-escaped text with &, <, >, ", and ' characters escaped
    """
    return _html.escape(text, quote=True)


def _normalise_test_name(name: str) -> str:
    """Return test name without pytest parameterization suffix."""
    return name.split("[", 1)[0]


def _find_matching_run_result(run_map: dict[str, TestResult], test_name: str) -> TestResult | None:
    """Find run result by exact, prefix, or de-parameterized test name."""
    direct = run_map.get(test_name)
    if direct is not None:
        return direct

    test_name_base = _normalise_test_name(test_name)
    for result_name, result in run_map.items():
        if result_name == test_name:
            return result
        if result_name.startswith(f"{test_name}["):
            return result
        if _normalise_test_name(result_name) == test_name_base:
            return result
    return None


def build_report_dicts(
    coverage_analysis: dict | None,
    run_result: RunResult | None,
) -> list[dict]:
    """Convert RequirementCoverage + RunResult to the dict format used by report_utils.

    Args:
        coverage_analysis: dict with "requirements" key containing RequirementCoverage list
        run_result: RunResult from pytest parser, or None

    Returns:
        list of dicts with keys: test_name, status, duration, screenshots, error_message
    """
    rows: list[dict] = []

    requirements = (coverage_analysis or {}).get("requirements", [])
    run_map: dict[str, TestResult] = {}
    if run_result:
        for tr in run_result.results:
            run_map[tr.name] = tr

    for req in requirements:
        linked: list[str] = getattr(req, "linked_tests", []) or []
        status = "unknown"
        duration = 0.0
        error_message = ""

        if linked and run_result:
            for test_name in linked:
                found = _find_matching_run_result(run_map, test_name)
                if found is not None:
                    status = found.status
                    duration = float(found.duration)
                    error_message = found.error_message or ""
                    break
            else:
                status = "pending"
        elif linked and run_result is None:
            status = "pending"
        elif getattr(req, "status", "") == "not_covered":
            status = "unknown"
        else:
            status = "pending"

        rows.append(
            {
                "test_name": f"{req.id}: {req.description[:80]}",
                "status": status,
                "duration": duration,
                "screenshots": [],
                "error_message": error_message,
            }
        )

    return rows


def _status_summary(coverage: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    """Return passed, failed, pending, unknown counts."""
    passed_count = sum(1 for t in coverage if t.get("status") == "passed")
    failed_count = sum(1 for t in coverage if t.get("status") == "failed")
    pending_count = sum(1 for t in coverage if t.get("status") == "pending")
    unknown_count = sum(1 for t in coverage if t.get("status") not in {"passed", "failed", "pending"})
    return passed_count, failed_count, pending_count, unknown_count


def _status_icon(status: str) -> str:
    """Return icon for a row status."""
    if status == "passed":
        return "✅"
    if status == "failed":
        return "❌"
    if status == "pending":
        return "⏳"
    return "⚪"


def generate_local_report(coverage: list[dict[str, Any]]) -> str:
    """Generate markdown report with relative screenshot paths.

    Args:
        coverage: List of test coverage dictionaries with test_name, status, screenshots, duration

    Returns:
        Markdown formatted report string
    """
    lines = [
        "# Test Coverage Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
    ]

    passed_count, failed_count, pending_count, unknown_count = _status_summary(coverage)

    lines.append(f"- **Total Tests:** {len(coverage)}")
    lines.append(f"- **Passed:** {passed_count}")
    lines.append(f"- **Failed:** {failed_count}")
    lines.append(f"- **Pending:** {pending_count}")
    lines.append(f"- **Unknown:** {unknown_count}")
    lines.append("")

    if coverage:
        total_duration = sum(float(t.get("duration", 0)) for t in coverage)
        lines.append(f"- **Total Duration:** {total_duration:.2f}s")
        lines.append("")

    lines.extend(["## Details", ""])

    for idx, test in enumerate(coverage, 1):
        test_name = test.get("test_name", "Unknown Test")
        status = test.get("status", "unknown")
        duration = float(test.get("duration", 0))
        screenshots = test.get("screenshots", [])
        error_message = test.get("error_message", "")

        status_icon = _status_icon(status)
        lines.append(f"### {idx}. {test_name} {status_icon}")
        lines.append("")
        lines.append(f"- **Status:** {status}")
        lines.append(f"- **Duration:** {duration:.2f}s")

        if error_message:
            lines.append(f"- **Error:** {error_message[:200]}")

        if screenshots:
            lines.append("")
            lines.append("**Screenshots:**")
            for screenshot in screenshots:
                path = screenshot.get("path", "")
                description = screenshot.get("description", "No description")
                # Use relative path from generated_tests directory
                rel_path = Path(path).name if Path(path).is_absolute() else path
                lines.append(f"- `{rel_path}` - {description}")

        lines.append("")

    return "\n".join(lines)


def generate_jira_report(coverage: list[dict[str, Any]], test_execution_date: str = "") -> str:
    """Generate markdown report in Jira attachment format.

    Args:
        coverage: List of test coverage dictionaries with test_name, status, screenshots, duration
        test_execution_date: Optional ISO date string (e.g., "2026-03-12")

    Returns:
        Markdown formatted report string compatible with Jira attachments
    """
    # Use provided date or current time
    if test_execution_date:
        exec_line = f"Test Execution Date: {test_execution_date}"
    else:
        exec_line = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    lines = [
        "# Test Coverage Report",
        "",
        exec_line,
        "",
        "## Summary",
        "",
    ]

    passed_count, failed_count, pending_count, unknown_count = _status_summary(coverage)

    lines.append(
        " | ".join(
            [
                f"Total Tests: {len(coverage)}",
                f"Passed: {passed_count}",
                f"Failed: {failed_count}",
                f"Pending: {pending_count}",
                f"Unknown: {unknown_count}",
            ]
        )
    )
    lines.append("")

    if coverage:
        total_duration = sum(float(t.get("duration", 0)) for t in coverage)
        lines.append(f"Total Duration: {total_duration:.2f}s")
        lines.append("")

    lines.extend(["## Test Details", ""])

    for idx, test in enumerate(coverage, 1):
        test_name = test.get("test_name", "Unknown Test")
        status = test.get("status", "unknown")
        duration = float(test.get("duration", 0))
        screenshots = test.get("screenshots", [])
        error_message = test.get("error_message", "")

        status_emoji = _status_icon(status)
        lines.append(f"=== {idx}. {test_name} {status_emoji} ===")
        lines.append("")
        lines.append(f"*Status:* {status}")
        lines.append(f"*Duration:* {duration:.2f}s")

        if error_message:
            lines.append(f"*Error:* {error_message[:200]}")

        if screenshots:
            lines.append("")
            lines.append("*Screenshots:*")
            for screenshot in screenshots:
                path = screenshot.get("path", "")
                description = screenshot.get("description", "No description")
                filename = Path(path).name if Path(path).is_absolute() else path
                # Jira thumbnail syntax
                lines.append(f"!{filename}|thumbnail! - {description}")

        lines.append("")

    return "\n".join(lines)


def generate_html_report(coverage: list[dict[str, Any]], screenshots_dir: Path | None = None) -> str:
    """Generate self-contained HTML report with base64 embedded screenshots.

    Args:
        coverage: List of test coverage dictionaries with test_name, status, screenshots, duration
        screenshots_dir: Directory containing screenshot files (optional, used for embedding)

    Returns:
        HTML formatted report string as a complete standalone document
    """
    passed_count, failed_count, pending_count, unknown_count = _status_summary(coverage)

    def embed_screenshot(screenshot_path: str) -> tuple[str, str]:
        """Embed screenshot as base64 data URI or return placeholder.

        Returns:
            Tuple of (image_html, alt_text)
        """
        if not screenshots_dir or not Path(screenshots_dir).exists():
            # No directory provided, use placeholder
            return (
                '<div style="background:#f0f0f0;padding:20px;text-align:center;color:#666;">⚠️ Screenshot unavailable</div>',
                "Screenshot unavailable",
            )

        full_path = Path(screenshots_dir) / screenshot_path
        if not full_path.exists():
            return (
                '<div style="background:#f0f0f0;padding:20px;text-align:center;color:#666;">⚠️ File not found</div>',
                "File not found",
            )

        try:
            with open(full_path, "rb") as f:
                content = f.read()
                base64_data = base64.b64encode(content).decode("utf-8")
                ext = full_path.suffix.lower()
                mime_type = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }.get(ext, "application/octet-stream")

                return (
                    f'<img src="data:{mime_type};base64,{base64_data}" style="max-width:100%;border:1px solid #ddd;border-radius:4px;padding:4px;" alt="screenshot">',
                    screenshot_path,
                )
        except Exception:
            return (
                '<div style="background:#f0f0f0;padding:20px;text-align:center;color:#666;">⚠️ Error loading image</div>',
                "Error loading image",
            )

    lines = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "    <meta charset='UTF-8'>",
        "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "    <title>Test Coverage Report</title>",
        "    <style>",
        "        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }",
        "        .container { max-width: 1200px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
        "        h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }",
        "        h2 { color: #555; margin-top: 30px; }",
        "        .summary { display: grid; grid-template-columns: repeat(5, 1fr); gap: 20px; margin: 20px 0; }",
        "        .stat { text-align: center; padding: 20px; border-radius: 8px; }",
        "        .stat.total { background: #e3f2fd; }",
        "        .stat.passed { background: #e8f5e9; }",
        "        .stat.failed { background: #ffebee; }",
        "        .stat.pending { background: #fff8e1; }",
        "        .stat.unknown { background: #eceff1; }",
        "        .stat-value { font-size: 36px; font-weight: bold; }",
        "        .stat-label { color: #666; margin-top: 5px; }",
        "        .test-item { border: 1px solid #ddd; border-radius: 8px; margin: 15px 0; overflow: hidden; }",
        "        .test-header { padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; background: #f9f9f9; }",
        "        .test-name { font-weight: bold; font-size: 18px; }",
        "        .status-badge { padding: 5px 12px; border-radius: 4px; font-size: 14px; font-weight: 500; }",
        "        .status-passed { background: #4caf50; color: white; }",
        "        .status-failed { background: #f44336; color: white; }",
        "        .status-pending { background: #f9a825; color: white; }",
        "        .status-unknown { background: #9e9e9e; color: white; }",
        "        .test-body { padding: 20px; }",
        "        .detail-row { display: flex; margin: 10px 0; }",
        "        .detail-label { font-weight: bold; width: 120px; color: #555; }",
        "        .screenshot-container { margin-top: 15px; padding: 10px; background: #fafafa; border-radius: 4px; }",
        "        .timestamp { color: #888; font-size: 12px; margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; }",
        "        @media (max-width: 600px) { .summary { grid-template-columns: 1fr; } }",
        "    </style>",
        "</head>",
        "<body>",
        "    <div class='container'>",
        "        <h1>🧪 Test Coverage Report</h1>",
        f"        <p class='timestamp'>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
        "",
        "        <div class='summary'>",
        f"            <div class='stat total'><div class='stat-value'>{len(coverage)}</div><div class='stat-label'>Total Tests</div></div>",
        f"            <div class='stat passed'><div class='stat-value'>{passed_count}</div><div class='stat-label'>Passed</div></div>",
        f"            <div class='stat failed'><div class='stat-value'>{failed_count}</div><div class='stat-label'>Failed</div></div>",
        f"            <div class='stat pending'><div class='stat-value'>{pending_count}</div><div class='stat-label'>Pending</div></div>",
        f"            <div class='stat unknown'><div class='stat-value'>{unknown_count}</div><div class='stat-label'>Unknown</div></div>",
        "        </div>",
        "",
        "        <h2>Test Details</h2>",
    ]

    for idx, test in enumerate(coverage, 1):
        test_name = test.get("test_name", "Unknown Test")
        status = test.get("status", "unknown")
        duration = float(test.get("duration", 0))
        screenshots = test.get("screenshots", [])
        error_message = test.get("error_message", "")

        status_class = f"status-{status}" if status in ["passed", "failed", "pending"] else "status-unknown"
        status_icon = _status_icon(status)

        lines.extend(
            [
                "        <div class='test-item'>",
                "            <div class='test-header'>",
                f"                <span class='test-name'>{idx}. {test_name} {status_icon}</span>",
                f"                <span class='status-badge {status_class}'>{status.upper()}</span>",
                "            </div>",
                "            <div class='test-body'>",
                f"                <div class='detail-row'><span class='detail-label'>Duration:</span><span>{duration:.2f}s</span></div>",
            ]
        )

        if error_message:
            lines.extend(
                [
                    f"                <div class='detail-row'><span class='detail-label'>Error:</span><span style='color:#d32f2f;'>{error_message[:200]}</span></div>",
                ]
            )

        if screenshots:
            screenshot_html_parts = []
            for screenshot in screenshots:
                path = screenshot.get("path", "")
                description = screenshot.get("description", "No description")
                img_html, _ = embed_screenshot(str(path))
                screenshot_html_parts.append(
                    f'<div style="margin-bottom:10px;">{img_html}<p style="margin:5px 0 0;padding:5px 0;color:#666;font-size:12px;">{description}</p></div>'
                )

            if screenshot_html_parts:
                lines.extend(
                    [
                        "                <div class='detail-row'><span class='detail-label'>Screenshots:</span></div>",
                        "                <div class='screenshot-container'>",
                    ]
                    + screenshot_html_parts
                    + ["                </div>"]
                )

        lines.extend(
            [
                "            </div>",
                "        </div>",
            ]
        )

    lines.extend(
        [
            "    </div>",
            "    <p class='timestamp'>Report generated by AI Playwright Test Generator</p>",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(lines)


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        import json

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
    segment_screenshots: list[str] = []
    segment_assertion_screenshots: list[str] = []

    def flush_segment(url_norm: str) -> None:
        if not url_norm:
            return
        if segment_assertion_screenshots:
            bg_by_url[url_norm] = segment_assertion_screenshots[-1]
        elif segment_screenshots:
            bg_by_url[url_norm] = segment_screenshots[-1]

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type", "")).lower()
        if "navigate" in step_type:
            flush_segment(current_url_norm)
            current_url = str(step.get("value", "") or "")  # EvidenceTracker stores url in value for navigate
            current_url_norm = _normalise_url(current_url)
            segment_screenshots = []
            segment_assertion_screenshots = []
            # navigate screenshots are useful as a fallback but often capture consent;
            # keep them, but we prefer later assertion screenshots.
            shot = step.get("screenshot")
            if shot:
                segment_screenshots.append(str(shot))
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
            # If we don't know the URL yet, skip grouping (should be rare).
            continue

        shot = step.get("screenshot")
        if shot:
            segment_screenshots.append(str(shot))
            if "assert" in step_type:
                segment_assertion_screenshots.append(str(shot))

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
    best_background: tuple[int, str] | None = None  # (priority, rel_path)

    for sidecar_path in evidence_dir.glob("*.evidence.json"):
        sidecar = _safe_read_json(sidecar_path)
        if not sidecar:
            continue
        points_by_url, bg_by_url = _extract_step_points_by_url(sidecar)
        all_points.extend(points_by_url.get(target_norm, []))
        if target_norm in bg_by_url:
            rel = bg_by_url[target_norm]
            # Prefer assertion screenshots if they exist in the segment path name, otherwise keep first.
            priority = 2 if "assert" in rel else 1
            if best_background is None or priority > best_background[0]:
                best_background = (priority, rel)

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

    import json

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
  <div style="margin-top:10px;color:#555;font-size:12px;">
    <strong>Points</strong>: {len(all_points)} total interactions across all tests.
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
    return 10 + Math.min(rc * 0.9, 28);
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
    points.forEach((p) => {{
      const t = stepType(p.type);
      const color = COLORS[t] || "#999";
      const r = baseRadius(p.run_count);
      const cx = (Number(p.x) / 100) * w;
      const cy = (Number(p.y) / 100) * h;
      const opacity = Math.min(0.18 + (Number(p.run_count || 1) * 0.04), 0.7);
      out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="7" opacity="${{opacity}}" />`);
      out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{Math.max(6, r - 12)}}" fill="none" stroke="${{color}}" stroke-width="2" opacity="${{opacity}}" />`);
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
    import json

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
      out.push(`<circle cx="${{cx}}" cy="${{cy}}" r="${{r}}" fill="${{color}}" opacity="0.85" stroke="${{stroke}}" stroke-width="${{sw}}" />`);
      out.push(`<text x="${{cx}}" y="${{cy + 5}}" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">${{idx + 1}}</text>`);
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

    import json

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
