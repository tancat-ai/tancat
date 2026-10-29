"""Standard report format renderers.

Each function takes a list[dict] (produced by ``build_report_dicts``) and returns
a string in the corresponding format (local markdown, Jira markdown, or HTML).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from src.evidence_image import EMBED_PREVIEW_MAX_WIDTH, embed_preview_data_uri
from src.evidence_report import generate_annotated_screenshot, overlay_counts
from src.heatmap_utils import generate_suite_heatmap, list_evidence_urls
from src.report_builder import _status_icon, _status_summary, escape_html


def _index_sidecars(evidence_dir: Path | None) -> dict[str, Path]:
    """Map every evidence sidecar of a package to its path, keyed by test name."""
    if evidence_dir is None or not evidence_dir.is_dir():
        return {}
    return {path.stem.replace(".evidence", ""): path for path in sorted(evidence_dir.glob("*.evidence.json"))}


def _match_sidecar(row: dict[str, Any], sidecar_index: dict[str, Path]) -> Path | None:
    """Return the evidence sidecar that belongs to one report row.

    A row names its tests in ``expected_locators``; the sidecars are keyed by
    the test name, with the pytest parameterisation suffix (``[chromium]``)
    on one side or the other.
    """
    names = row.get("expected_locators") or []
    if isinstance(names, str):
        names = [names]
    for raw in names:
        name = str(raw)
        base = name.split("[", 1)[0]
        if name in sidecar_index:
            return sidecar_index[name]
        if base in sidecar_index:
            return sidecar_index[base]
        for key, path in sidecar_index.items():
            if key.split("[", 1)[0] == base or key.startswith(base):
                return path
    return None


def _overlay_block(row: dict[str, Any], sidecar_index: dict[str, Path]) -> str:
    """Return the annotated evidence overlay for one report row.

    Empty when the row has no evidence sidecar. The block is a disclosure:
    open for a failed test (that is where the reader needs the picture) and
    closed otherwise, so the report stays a document rather than a gallery.
    """
    sidecar_path = _match_sidecar(row, sidecar_index)
    if sidecar_path is None:
        return ""
    try:
        html = generate_annotated_screenshot(
            sidecar_path=sidecar_path,
            title=str(row.get("test_name", "")),
            max_width=EMBED_PREVIEW_MAX_WIDTH,
        )
        frames, markers = overlay_counts(sidecar_path)
    except Exception:
        return ""
    if markers:
        summary = f"Annotated overlay - {markers} step(s) marked on {frames} frame(s)"
    else:
        summary = "Annotated overlay - no element positions were recorded for this test"
    open_attr = " open" if str(row.get("status", "")) == "failed" else ""
    return (
        f"                <details{open_attr} style='margin:15px 0;border:1px solid #e0e0e0;border-radius:8px;padding:8px 12px;background:#fff;'>"
        f"                    <summary style='cursor:pointer;font-weight:600;color:#333;'>{escape_html(summary)}</summary>"
        f"                    <div style='margin-top:10px;'>{html}</div>"
        "                </details>"
    )


def _suite_heatmap_lines(evidence_dir: Path | None, urls: list[str]) -> list[str]:
    """Return the HTML lines for the per-URL suite heatmap section."""
    if evidence_dir is None or not evidence_dir.is_dir() or not urls:
        return []
    lines = [
        "        <h2>Suite Heatmap - Per-URL Element Coverage</h2>",
        "        <p class='timestamp'>Which elements each page of the product was exercised on, across the whole suite. "
        "A circle's number is how many times that element was hit; its colour is the outcome. "
        "Every marker sits on the frame the step was measured on.</p>",
    ]
    for idx, url in enumerate(urls):
        try:
            html = generate_suite_heatmap(
                evidence_dir=evidence_dir,
                page_url=url,
                max_width=EMBED_PREVIEW_MAX_WIDTH,
            )
        except Exception:
            continue
        open_attr = " open" if idx == 0 else ""
        lines.extend(
            [
                f"        <details{open_attr} style='margin:10px 0;border:1px solid #e0e0e0;border-radius:8px;padding:8px 12px;background:#fff;'>",
                f"            <summary style='cursor:pointer;font-weight:600;'>{escape_html(url)}</summary>",
                "            <div style='margin-top:10px;'>",
                html,
                "            </div>",
                "        </details>",
            ]
        )
    return lines


def journey_lines(test: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return the t-1063 journey summary as (step, expected, reached) rows.

    One row per failed step, plus the off-course note as a final row whose
    ``step`` is "Later steps". Empty for a clean test and for an older package
    that carries no journey block, so nothing is invented.
    """
    journey = test.get("journey") or {}
    if not isinstance(journey, dict) or not journey:
        return []
    rows: list[tuple[str, str, str]] = []
    for failure in journey.get("failed_steps") or []:
        if not isinstance(failure, dict):
            continue
        page = failure.get("page") or {}
        expected = str(page.get("expected") or "") if isinstance(page, dict) else ""
        reached = str(page.get("actual") or "") if isinstance(page, dict) else ""
        detail = str(failure.get("error") or "")
        if not expected and detail:
            expected = detail
        rows.append((f"Step {failure.get('step')}", expected, reached))
    stop_text = str(journey.get("stop_text") or "")
    if stop_text:
        detail = str((journey.get("stop") or {}).get("detail") or "") if isinstance(journey.get("stop"), dict) else ""
        rows.append(("Stopped", stop_text, detail))
    later = int(journey.get("later_steps") or 0)
    passed = int(journey.get("later_passed_off_course") or 0)
    off_course = journey.get("off_course") or {}
    if later:
        reached = str(off_course.get("actual") or "") if isinstance(off_course, dict) else ""
        note = f"{later} ran, {passed} passed"
        if reached:
            note += f" on '{reached}'; none of those passes is clean"
        else:
            note += " after the failure; none of those passes is clean"
        rows.append(("Later steps", "", note))
    return rows


def verification_line(test: dict[str, Any]) -> str:
    """Return the B-100 one-line verification summary for a report row.

    Uses the emitted verdict's own label, so the wording stays in one place:
    ``verified by element (<selector>)``, ``verified by page arrival (<url
    assertion>)``, or ``unverified - <reason>``. Empty when the row has no
    verdict (an older package).
    """
    verification = test.get("verification") or {}
    if not isinstance(verification, dict) or not verification:
        return ""
    label = str(verification.get("label") or verification.get("status") or "unverified")
    reason = str(verification.get("reason") or "")
    checked = str(verification.get("checked") or "")
    if label == "unverified":
        return f"unverified - {reason}" if reason else "unverified"
    if checked:
        return f"{label} ({checked})"
    return label


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

        # Failure diagnostics (new)
        failure_note = test.get("failure_note")
        suggested_locators = test.get("suggested_locators", [])
        available_elements = test.get("available_elements", [])
        screenshot_paths = test.get("screenshot_paths", [])
        page_url = test.get("page_url", "")
        page_title = test.get("page_title", "")

        status_icon = _status_icon(status)
        lines.append(f"### {idx}. {test_name} {status_icon}")
        lines.append("")
        lines.append(f"- **Status:** {status}")
        lines.append(f"- **Duration:** {duration:.2f}s")

        verification = verification_line(test)
        if verification:
            lines.append(f"- **Verification:** {verification}")

        if error_message:
            lines.append(f"- **Error:** {error_message[:200]}")

        # Failure diagnostics section (only for failed tests with diagnostic data)
        if status == "failed" and (failure_note or suggested_locators or page_url or test.get("journey")):
            lines.append("")
            lines.append("#### Failure Diagnostics")
            if page_url:
                lines.append(f"- **Page URL:** {page_url}")
            if page_title:
                lines.append(f"- **Page Title:** {page_title}")
            if failure_note:
                # Truncate very long failure notes for readability
                fn = failure_note if len(failure_note) < 600 else failure_note[:597] + "..."
                lines.append(f"- **Failure Note:** {fn}")
            if suggested_locators:
                lines.append("- **Suggested Alternatives:** " + ", ".join(f"`{s}`" for s in suggested_locators[:5]))
            journey_rows = journey_lines(test)
            if journey_rows:
                lines.append("")
                lines.append("#### Journey")
                for step, expected, reached in journey_rows:
                    parts = [f"**{step}**"]
                    if expected:
                        parts.append(f"expected {expected}")
                    if reached:
                        parts.append(f"reached {reached}")
                    lines.append("- " + " - ".join(parts))
            if available_elements:
                # Summarize by role/tag
                roles: dict[str, int] = {}
                for elem in available_elements[:20]:
                    role = elem.get("role", elem.get("tag", "unknown"))
                    roles[role] = roles.get(role, 0) + 1
                summary = ", ".join(f"[{r}]×{c}" for r, c in sorted(roles.items()))
                lines.append(f"- **Available Elements:** {summary}")
            if screenshot_paths:
                lines.append("")
                lines.append("**Failure Screenshots:**")
                for sp in screenshot_paths:
                    rel = Path(sp).name if Path(sp).is_absolute() else sp
                    lines.append(f"- `{rel}`")

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


def generate_jira_report(
    coverage: list[dict[str, Any]],
    test_execution_date: str = "",
    project_key: str = "",
) -> str:
    """Generate markdown report in Jira attachment format.

    Args:
        coverage: List of test coverage dictionaries with test_name, status, screenshots, duration
        test_execution_date: Optional ISO date string (e.g., "2026-03-12")
        project_key: Optional Jira project key (B-036 Phase 4 — export-time
            field). When non-empty, a ``Project:`` line is included in the
            header so the exported report shows which Jira project it
            belongs to.

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
    ]
    if project_key.strip():
        lines.extend([f"Project: {project_key.strip().upper()}", ""])
    lines.extend(["## Summary", ""])

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

        # Failure diagnostics (new)
        failure_note = test.get("failure_note")
        suggested_locators = test.get("suggested_locators", [])
        available_elements = test.get("available_elements", [])
        screenshot_paths = test.get("screenshot_paths", [])
        page_url = test.get("page_url", "")
        page_title = test.get("page_title", "")

        status_emoji = _status_icon(status)
        lines.append(f"=== {idx}. {test_name} {status_emoji} ===")
        lines.append("")
        lines.append(f"*Status:* {status}")
        lines.append(f"*Duration:* {duration:.2f}s")

        verification = verification_line(test)
        if verification:
            lines.append(f"*Verification:* {verification}")

        if error_message:
            lines.append(f"*Error:* {error_message[:200]}")

        # Failure diagnostics section
        if status == "failed" and (failure_note or suggested_locators or page_url or test.get("journey")):
            lines.append("")
            lines.append("*-- Failure Diagnostics --*")
            if page_url:
                lines.append(f"*Page URL:* {page_url}")
            if page_title:
                lines.append(f"*Page Title:* {page_title}")
            if failure_note:
                fn = failure_note if len(failure_note) < 600 else failure_note[:597] + "..."
                lines.append(f"*Failure Note:* {fn}")
            if suggested_locators:
                lines.append("*Suggested Alternatives:* " + ", ".join(f"`{s}`" for s in suggested_locators[:5]))
            if available_elements:
                roles: dict[str, int] = {}
                for elem in available_elements[:20]:
                    role = elem.get("role", elem.get("tag", "unknown"))
                    roles[role] = roles.get(role, 0) + 1
                summary = ", ".join(f"[{r}]x{c}" for r, c in sorted(roles.items()))
                lines.append(f"*Available Elements:* {summary}")
            if screenshot_paths:
                lines.append("")
                lines.append("*Failure Screenshots:*")
                for sp in screenshot_paths:
                    fn = Path(sp).name if Path(sp).is_absolute() else sp
                    lines.append(f"!{fn}|thumbnail!")

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


def generate_html_report(
    coverage: list[dict[str, Any]],
    screenshots_dir: Path | None = None,
    title: str = "",
) -> str:
    """Generate self-contained HTML report with base64 embedded screenshots.

    The report carries the evidence overlay (B-105): the annotated per-test
    viewer, whose markers sit on the frame each step was measured in, and the
    per-URL suite heatmap. Both are the artifacts this product sells, so they
    belong in the file the customer keeps.

    Every embedded image is a **preview** scaled to
    ``EMBED_PREVIEW_MAX_WIDTH`` pixels wide. Evidence frames are full-page
    captures (~8,000-9,000 px tall, ~2.5 MB each); embedding them whole made
    the report unsendable. The full-resolution lossless captures stay in the
    package's ``evidence/`` folder and every preview names its source file.

    Args:
        coverage: List of test coverage dictionaries with test_name, status, screenshots, duration
        screenshots_dir: Directory containing screenshot files (optional, used for embedding)
        title: Optional package/story name shown under the heading so a report
            saved on its own says which run it belongs to.

    Returns:
        HTML formatted report string as a complete standalone document
    """
    passed_count, failed_count, pending_count, unknown_count = _status_summary(coverage)

    evidence_dir = (Path(screenshots_dir) / "evidence") if screenshots_dir else None
    sidecar_index = _index_sidecars(evidence_dir)
    evidence_urls = list_evidence_urls(evidence_dir) if evidence_dir is not None else []

    def embed_screenshot(screenshot_path: str) -> tuple[str, str]:
        """Embed screenshot as base64 data URI or return placeholder.

        Evidence screenshots are full-page captures (~8,000-9,000 px tall).
        Inlined at full width they made the report page ~17,000 px tall and
        impossible to scan, so each image sits in a fixed-height scroll box:
        full reading width, scroll inside, report layout stays compact.

        The embed is a downscaled preview (the embed-size policy): the
        lossless capture stays in ``evidence/``.

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
            data_uri = embed_preview_data_uri(full_path)
            if not data_uri:
                raise OSError("preview failed")

            return (
                '<div style="max-height:640px;overflow:auto;border:1px solid #ddd;border-radius:4px;padding:4px;background:#fafafa;">'
                f'<img src="{data_uri}" style="display:block;width:100%;max-width:{EMBED_PREVIEW_MAX_WIDTH}px;height:auto;" alt="screenshot">'
                "</div>",
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
        "        .status-partial_pass { background: #fb8c00; color: white; }",
        "        .status-unknown { background: #9e9e9e; color: white; }",
        "        .test-nav { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 20px; }",
        "        .test-nav a { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border: 1px solid #ddd; border-radius: 16px; font-size: 12px; color: #333; text-decoration: none; background: #f9f9f9; }",
        "        .test-nav a:hover { background: #e3f2fd; border-color: #90caf9; }",
        "        .test-nav a.nav-failed { border-color: #f44336; color: #c62828; }",
        "        .test-nav a.nav-partial_pass { border-color: #fb8c00; color: #e65100; }",
        "        .test-body { padding: 20px; }",
        "        .detail-row { display: flex; margin: 10px 0; }",
        "        .detail-label { font-weight: bold; width: 120px; color: #555; }",
        "        .screenshot-container { margin-top: 15px; padding: 10px; background: #fafafa; border-radius: 4px; }",
        "        .timestamp { color: #888; font-size: 12px; margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; }",
        "        @media (max-width: 900px) { .summary { grid-template-columns: repeat(2, 1fr); } }",
        "        @media (max-width: 600px) { .summary { grid-template-columns: 1fr; } }",
        "    </style>",
        "</head>",
        "<body>",
        "    <div class='container'>",
        "        <h1>🧪 Test Coverage Report</h1>",
        f"        <p class='timestamp'>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        + (f" &middot; Package: <code>{escape_html(title)}</code>" if title else "")
        + "</p>",
        "",  # test-nav inserted below (needs the rows first)
        "        <div class='summary'>",
        f"            <div class='stat total'><div class='stat-value'>{len(coverage)}</div><div class='stat-label'>Total Tests</div></div>",
        f"            <div class='stat passed'><div class='stat-value'>{passed_count}</div><div class='stat-label'>Passed</div></div>",
        f"            <div class='stat failed'><div class='stat-value'>{failed_count}</div><div class='stat-label'>Failed</div></div>",
        f"            <div class='stat pending'><div class='stat-value'>{pending_count}</div><div class='stat-label'>Pending</div></div>",
        f"            <div class='stat unknown'><div class='stat-value'>{unknown_count}</div><div class='stat-label'>Unknown</div></div>",
        "        </div>",
        "",
        "        <p class='timestamp'>Every image in this report is a preview scaled to "
        f"{EMBED_PREVIEW_MAX_WIDTH}px wide, so the file stays small enough to send. The full-resolution "
        "lossless captures are the files in the package's <code>evidence/</code> folder, named under each image. "
        "Each test below carries an annotated overlay: every step's marker sits on the frame that step was "
        "measured in.</p>",
        "",
    ]

    lines.extend(_suite_heatmap_lines(evidence_dir, evidence_urls))
    if evidence_urls:
        lines.append("")

    if coverage:
        nav_links = []
        for idx, test in enumerate(coverage, 1):
            status = test.get("status", "unknown")
            short = escape_html(str(test.get("test_name", ""))[:40])
            cls = (
                " class='nav-failed'"
                if status == "failed"
                else (" class='nav-partial_pass'" if status == "partial_pass" else "")
            )
            nav_links.append(f"<a href='#test-{idx}'{cls} title='{short}'>{_status_icon(status)} {idx}</a>")
        lines.append("        <div class='test-nav'>" + "".join(nav_links) + "</div>")

    lines.append("        <h2>Test Details</h2>")

    for idx, test in enumerate(coverage, 1):
        test_name = test.get("test_name", "Unknown Test")
        status = test.get("status", "unknown")
        duration = float(test.get("duration", 0))
        screenshots = test.get("screenshots", [])
        error_message = test.get("error_message", "")

        status_class = (
            f"status-{status}" if status in ["passed", "failed", "pending", "partial_pass"] else "status-unknown"
        )
        status_icon = _status_icon(status)

        lines.extend(
            [
                f"        <div class='test-item' id='test-{idx}'>",
                "            <div class='test-header'>",
                f"                <span class='test-name'>{idx}. {escape_html(test_name)} {status_icon}</span>",
                f"                <span class='status-badge {status_class}'>{status.upper()}</span>",
                "            </div>",
                "            <div class='test-body'>",
                f"                <div class='detail-row'><span class='detail-label'>Duration:</span><span>{duration:.2f}s</span></div>",
            ]
        )

        verification = verification_line(test)
        if verification:
            # On a failed test the emit-time verdict reads like a pass
            # ("verified by element"). Frame it as what the test was meant to
            # check, so a red row cannot be skimmed as a green one.
            label = "Intended check:" if status == "failed" else "Verification:"
            lines.append(
                f"                <div class='detail-row'><span class='detail-label'>{label}</span>"
                f"<span>{escape_html(verification)}</span></div>"
            )

        if error_message:
            lines.extend(
                [
                    f"                <div class='detail-row'><span class='detail-label'>Error:</span><span style='color:#d32f2f;'>{escape_html(error_message[:200])}</span></div>",
                ]
            )

        # Failure diagnostics section for failed tests
        failure_note = test.get("failure_note")
        suggested_locators = test.get("suggested_locators", [])
        available_elements = test.get("available_elements", [])
        screenshot_paths = test.get("screenshot_paths", [])
        page_url = test.get("page_url", "")
        page_title = test.get("page_title", "")

        if status == "failed" and (failure_note or suggested_locators or page_url or test.get("journey")):
            diag_border = "border-left:4px solid #f44336;padding-left:15px;margin:15px 0;background:#fff5f5;padding:10px;border-radius:4px;"
            lines.append(f"                <div style='{diag_border}'>")
            lines.append("                    <strong style='color:#c62828;'>Failure Diagnostics</strong>")
            lines.append('                    <div style="margin-top:10px;">')
            if page_url:
                lines.append(
                    f"                    <div class='detail-row'><span class='detail-label'>Page URL:</span><span>{escape_html(page_url)}</span></div>"
                )
            if page_title:
                lines.append(
                    f"                    <div class='detail-row'><span class='detail-label'>Page Title:</span><span>{escape_html(page_title)}</span></div>"
                )
            if failure_note:
                fn = failure_note if len(failure_note) < 600 else failure_note[:597] + "..."
                lines.append(
                    f"                    <div class='detail-row'><span class='detail-label'>Failure Note:</span><span style='white-space:pre-wrap;'>{escape_html(fn)}</span></div>"
                )
            for step, expected, reached in journey_lines(test):
                detail = " - ".join(part for part in (expected, reached) if part)
                lines.append(
                    f"                    <div class='detail-row'><span class='detail-label'>{escape_html(step)}:</span><span>{escape_html(detail)}</span></div>"
                )
            if suggested_locators:
                loc_html = ", ".join(f"<code>{escape_html(s)}</code>" for s in suggested_locators[:5])
                lines.append(
                    f"                    <div class='detail-row'><span class='detail-label'>Suggested Alternatives:</span><span>{loc_html}</span></div>"
                )
            if available_elements:
                roles: dict[str, int] = {}
                for elem in available_elements[:20]:
                    role = elem.get("role", elem.get("tag", "unknown"))
                    roles[role] = roles.get(role, 0) + 1
                summary = ", ".join(f"[{r}]x{c}" for r, c in sorted(roles.items()))
                lines.append(
                    f"                    <div class='detail-row'><span class='detail-label'>Available Elements:</span><span>{escape_html(summary)}</span></div>"
                )
            if screenshot_paths:
                lines.append("                    <strong>Failure Screenshots:</strong>")
                for sp in screenshot_paths:
                    img_html, _ = embed_screenshot(sp)
                    lines.append(f"                    <div style='margin:5px 0;'>{img_html}</div>")
            lines.append("                    </div>")
            lines.append("                </div>")

        if screenshots:
            screenshot_html_parts = []
            for screenshot in screenshots:
                path = screenshot.get("path", "")
                description = screenshot.get("description", "No description")
                img_html, _ = embed_screenshot(str(path))
                screenshot_html_parts.append(
                    f'<div style="margin-bottom:10px;">{img_html}<p style="margin:5px 0 0;padding:5px 0;color:#666;font-size:12px;">{escape_html(description)}</p></div>'
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

        overlay_block = _overlay_block(test, sidecar_index)
        if overlay_block:
            lines.append(overlay_block)

        lines.extend(
            [
                "            </div>",
                "        </div>",
            ]
        )

    lines.extend(
        [
            "    </div>",
            "    <p class='timestamp'>Report generated by TanCat</p>",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(lines)
