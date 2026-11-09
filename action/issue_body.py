#!/usr/bin/env python3
"""CI issue body - built from the run's own report, not typed into the workflow.

The nightly self-test files one issue when it goes red (forced visibility). It
used to be hand-written prose inside the workflow: a title, a run link, a date
and "re-run it" - no test count, no failing test, no step. Every other surface
reports those facts; the one CI artefact a person actually reads did not, and the
prose could only drift from the report.

This renders the SAME facts from the report the run already wrote
(``report.json``, see ``action/report.py``): total/passed/failed/errors/skipped,
the failing test names, and the run link. One source, two readers - the PR
comment keeps using ``report.md`` from that same dict.

``report.json`` is read, never re-derived: a second calculation would be a second
truth. When no report reached this job (the run died before writing one), the
body says so plainly instead of pretending the numbers are zero.

Usage::

    python action/issue_body.py --results <dir> --run-url <url> --output issue.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ISSUE_TITLE = "\U0001f319 Nightly self-test failing"


def load_reports(results_dir: Path) -> list[dict[str, Any]]:
    """Every ``report.json`` under *results_dir*, newest first, titled by folder."""
    reports: list[dict[str, Any]] = []
    for path in sorted(results_dir.rglob("report.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        if not isinstance(data, dict):
            continue
        data["_report_path"] = str(path)
        reports.append(data)
    reports.sort(key=lambda r: str(r.get("generated_at") or ""), reverse=True)
    return reports


def render_issue_body(
    reports: list[dict[str, Any]],
    *,
    run_url: str,
    date: str | None = None,
    mode: str = "full self-test (six modes)",
) -> str:
    """The issue body for a red run, from the reports the run produced."""
    today = date or datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        f"The forced {mode} failed.",
        "",
        f"- Run: {run_url}",
        f"- Date: {today}",
        "",
    ]
    if not reports:
        lines += [
            "**No report reached this job.** The run failed before writing one (or its artifact "
            "did not upload), so there are no counts and no failing test names to show here. The "
            "run link above is the only evidence; open it for the step that failed.",
            "",
            "Re-run: Actions → CI/CD Action Self-Test → Run workflow.",
            "Close this issue only after a green full run.",
            "",
        ]
        return "\n".join(lines)

    totals = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    failed_rows: list[tuple[str, str, str]] = []
    for report in reports:
        tests = report.get("tests") or {}
        for key in totals:
            totals[key] += int(tests.get(key) or 0)
        # j-0296: label by the report's MODE (what ran), not by the folder it
        # was downloaded into - every row said "(ci-results)".
        leg = str(report.get("mode") or "run")
        for failure in report.get("failed_tests") or []:
            failed_rows.append(
                (
                    str(failure.get("test") or "unknown"),
                    str(failure.get("message") or "")[:200],
                    leg,
                )
            )

    lines += [
        "| Metric | Value |",
        "|---|---|",
        f"| Tests | {totals['total']} ({totals['passed']} passed · {totals['failed']} failed · "
        f"{totals['errors']} errors · {totals['skipped']} skipped) |",
        f"| Legs read | {len(reports)}" + (" (one leg - a partial run)" if len(reports) == 1 else "") + " |",
        "",
    ]
    if failed_rows:
        lines.append("**Failing tests:**")
        for name, message, where in failed_rows[:25]:
            suffix = f" — {message}" if message else ""
            lines.append(f"- `{name}` ({where}){suffix}")
        if len(failed_rows) > 25:
            lines.append(f"- ... and {len(failed_rows) - 25} more in the run artifact")
        lines.append("")
    else:
        lines.append(
            "**Failing tests:** none named in the reports. The red step is not a test failure "
            "(a build, an install or a stub assertion) - the run link names it."
        )
        lines.append("")

    lines += [
        "The counts above were read from the run's own `report.json`, the same file the PR comment "
        "and the HTML artifact are built from.",
        "",
        "Re-run: Actions → CI/CD Action Self-Test → Run workflow.",
        "Close this issue only after a green full run.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the CI issue body from report.json")
    parser.add_argument("--results", required=True, help="Directory holding the run's report.json files")
    parser.add_argument("--run-url", required=True, help="Link to the failed workflow run")
    parser.add_argument("--date", default="", help="Date to print (default: today, UTC)")
    parser.add_argument("--output", required=True, help="Where to write the markdown body")
    args = parser.parse_args(argv)

    results = Path(args.results)
    reports = load_reports(results) if results.exists() else []
    body = render_issue_body(reports, run_url=args.run_url, date=args.date or None)
    Path(args.output).write_text(body, encoding="utf-8")
    print(f"issue body written to {args.output} ({len(reports)} report(s) read)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
