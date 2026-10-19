"""Standard report format renderers.

Each function takes a list[dict] (produced by ``build_report_dicts``) and returns
a string in the corresponding format (local markdown, Jira markdown, or HTML).
"""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Any

from src.report_builder import _status_icon, _status_summary, escape_html


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
        if status == "failed" and (failure_note or suggested_locators or page_url):
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
        if status == "failed" and (failure_note or suggested_locators or page_url):
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

    Args:
        coverage: List of test coverage dictionaries with test_name, status, screenshots, duration
        screenshots_dir: Directory containing screenshot files (optional, used for embedding)
        title: Optional package/story name shown under the heading so a report
            saved on its own says which run it belongs to.

    Returns:
        HTML formatted report string as a complete standalone document
    """
    passed_count, failed_count, pending_count, unknown_count = _status_summary(coverage)

    def embed_screenshot(screenshot_path: str) -> tuple[str, str]:
        """Embed screenshot as base64 data URI or return placeholder.

        Evidence screenshots are full-page captures (~8,000-9,000 px tall).
        Inlined at full width they made the report page ~17,000 px tall and
        impossible to scan, so each image sits in a fixed-height scroll box:
        full reading width, scroll inside, report layout stays compact.

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
                    '<div style="max-height:640px;overflow:auto;border:1px solid #ddd;border-radius:4px;padding:4px;background:#fafafa;">'
                    f'<img src="data:{mime_type};base64,{base64_data}" style="display:block;width:100%;height:auto;" alt="screenshot">'
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
    ]

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

        if status == "failed" and (failure_note or suggested_locators or page_url):
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
