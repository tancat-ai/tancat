#!/usr/bin/env python3
"""CI report core (Phase 7a) — JUnit -> summary + repair-candidate marking.

Parses the raw pytest ``junit.xml`` (and optionally the AI-028 evidence
JUnit), computes pass/fail/skip counts, marks LocatorNotFound-class failures
as **repair candidates** (spec §8/7a: marking only, no adaptation execution —
that lands in 7b), and writes ``report.json`` + ``report.md``.

``report.md`` is shaped exactly like the Phase 7b PR comment (§6), so the
self-test workflow can assert the comment payload shape today via a stub
step instead of a real PR.

Platform seam (spec §5.5): reads argv + files, writes files. Zero GitHub
imports — the GitLab adapter (7c) reuses it unchanged.

Usage::

    python action/report.py --mode run-existing --junit junit.xml --output <dir>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

# Locator-class failure signatures — mechanical, often environment churn in
# shared environments; exactly the class the 7b verified-adaptation engine
# is allowed to patch (spec §9.6: assertion failures always surface).
_REPAIR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"strict mode violation", re.IGNORECASE),
    re.compile(r"locator.*\bnot found\b", re.IGNORECASE),
    re.compile(r"waiting for locator", re.IGNORECASE),
    re.compile(r"timeout\s+\d+\s*ms exceeded", re.IGNORECASE),
    re.compile(r"unable to (find|locate|resolve)", re.IGNORECASE),
)


class JunitStats(TypedDict):
    """Parsed pytest junit.xml — counts + per-testcase failure records."""

    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_s: float
    failed_tests: list[dict[str, str]]
    repair_candidates: list[dict[str, str]]


def _is_repair_candidate(message: str) -> bool:
    return any(p.search(message) for p in _REPAIR_PATTERNS)


def _parse_junit(path: Path) -> JunitStats:
    """Extract suite counts + per-testcase failures from a pytest junit.xml."""
    tree = ET.parse(path)
    root = tree.getroot()

    suites: list[ET.Element]
    if root.tag == "testsuites":
        suites = list(root)
    else:
        suites = [root]

    total = failures = errors = skipped = 0
    duration_s = 0.0
    failed_tests: list[dict[str, str]] = []
    repair_candidates: list[dict[str, str]] = []

    for suite in suites:
        total += int(suite.get("tests", 0) or 0)
        failures += int(suite.get("failures", 0) or 0)
        errors += int(suite.get("errors", 0) or 0)
        skipped += int(suite.get("skipped", 0) or 0)
        try:
            duration_s += float(suite.get("time", 0.0) or 0.0)
        except ValueError:
            pass
        for case in suite.iter("testcase"):
            failure = case.find("failure")
            if failure is None:
                continue
            message = failure.get("message", "") or (failure.text or "").strip()
            record = {
                "test": case.get("name", "unknown"),
                "classname": case.get("classname", ""),
                "message": message[:500],
            }
            failed_tests.append(record)
            if _is_repair_candidate(message):
                repair_candidates.append(record)

    passed = total - failures - errors - skipped
    return JunitStats(
        total=total,
        passed=max(passed, 0),
        failed=failures,
        errors=errors,
        skipped=skipped,
        duration_s=round(duration_s, 2),
        failed_tests=failed_tests,
        repair_candidates=repair_candidates,
    )


def _render_markdown(report: dict[str, object]) -> str:
    tests: dict[str, object] = report["tests"]  # type: ignore[assignment]
    failed = tests["failed"]
    errors = tests["errors"]
    skipped = tests["skipped"]
    candidates: list[dict[str, str]] = report["repair_candidates"]  # type: ignore[assignment]
    failed_tests: list[dict[str, str]] = report["failed_tests"]  # type: ignore[assignment]

    lines = [
        "## 🤖 AI Test Generator — results",
        "",
        f"**Mode:** {report['mode']} · **Package:** {report.get('package', '—')}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Tests | {tests['total']} ({tests['passed']} passed · {failed} failed · "
        f"{errors} errors · {skipped} skipped) |",
        f"| Duration | {tests['duration_s']}s |",
        "",
    ]
    if failed_tests:
        lines.append("**Failed tests:**")
        for ft in failed_tests[:10]:
            lines.append(f"- `{ft['test']}` — {ft['message'][:200]}")
        lines.append("")
    if candidates:
        lines.append(
            "**Repair candidates** (offered, never auto-applied): "
            f"{len(candidates)} failure(s) are locator-class — mechanical, often environment "
            "churn in shared environments. Interactive repair is available in the tool."
        )
        for ft in candidates[:10]:
            lines.append(f"- `{ft['test']}` — {ft['message'][:200]}")
        lines.append("")
    else:
        lines.append("**Repair candidates:** none.")
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="report",
        description="JUnit -> summary + repair-candidate marking (Phase 7a report core).",
    )
    parser.add_argument("--mode", required=True, help="Action mode (generate-only | run-existing)")
    parser.add_argument("--junit", required=True, help="Raw pytest junit.xml path")
    parser.add_argument("--evidence-junit", default="", help="AI-028 evidence junit.xml path (optional)")
    parser.add_argument("--package", default="", help="Package path as given by the caller")
    parser.add_argument("--workspace", default="", help="AI-029 workspace name")
    parser.add_argument("--url", default="", help="Target site URL (context only)")
    parser.add_argument("--story", default="", help="Story ref (context only)")
    parser.add_argument("--output", required=True, help="Output directory (report.json + report.md)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    junit_path = Path(args.junit)
    if not junit_path.exists():
        print(f"ERROR: junit file not found: {junit_path}", file=sys.stderr)
        return 2

    stats = _parse_junit(junit_path)
    report: dict[str, object] = {
        "mode": args.mode,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "package": args.package,
        "workspace": args.workspace,
        "url": args.url,
        "story": args.story,
        "junit": str(junit_path.resolve()),
        "evidence_junit": str(Path(args.evidence_junit).resolve()) if args.evidence_junit else "",
        "tests": {
            "total": stats["total"],
            "passed": stats["passed"],
            "failed": stats["failed"],
            "errors": stats["errors"],
            "skipped": stats["skipped"],
            "duration_s": stats["duration_s"],
        },
        "failed_tests": stats["failed_tests"],
        "repair_candidates": stats["repair_candidates"],
    }

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(_render_markdown(report), encoding="utf-8")
    print(
        f"report: {stats['total']} tests, {stats['failed']} failed, "
        f"{len(stats['repair_candidates'])} repair candidate(s) -> {out_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
