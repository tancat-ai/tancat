#!/usr/bin/env python3
"""Per-branch run-history store for the Phase 7 CI action (AI-011 flaky markers).

The Action keeps its own run history so the PR comment can mark flaky tests
("last 3 runs" style). The history file lives in the workspace
(``<workspace>/run-history.json``) and is persisted across job runs by the
workflow's ``actions/cache`` (branch-scoped key, default-branch fallback via
``restore-keys``) — the action itself only reads/writes the file, exactly the
platform seam pattern (spec §5.5).

Flaky semantics mirror the product's AI-011 detection: a test is *flaky* when
it has BOTH passes and failures (or errors) across at least ``min_runs``
observations. Observations come from the raw pytest junit.xml, one per job
run. Same-suite name matching — junit test names include the ``[chromium]``
parameter, so names match exactly across runs of the same package.

Platform-neutral core: reads argv + files, writes files. Zero GitHub imports.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_RUNS_KEPT = 10


def _load_history(path: str | Path) -> dict[str, Any]:
    """Load the run-history JSON; missing/corrupt file yields an empty store."""
    p = Path(path)
    if not p.exists():
        return {"runs": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {"runs": []}
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        return {"runs": []}
    return data


def _parse_junit_results(junit_path: str | Path) -> list[dict[str, str]]:
    """Extract (name, status) pairs from a pytest junit.xml (passed/failed/skipped)."""
    root = ET.parse(str(junit_path)).getroot()
    suites: list[ET.Element] = list(root) if root.tag == "testsuites" else [root]
    results: list[dict[str, str]] = []
    for suite in suites:
        for case in suite.iter("testcase"):
            name = case.get("name", "unknown")
            if case.find("failure") is not None:
                status = "failed"
            elif case.find("error") is not None:
                status = "error"
            elif case.find("skipped") is not None:
                status = "skipped"
            else:
                status = "passed"
            results.append({"name": name, "status": status})
    return results


def merge_run(
    history: dict[str, Any],
    junit_path: str | Path,
    package: str = "",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Append one run's results to the store and trim to ``MAX_RUNS_KEPT``.

    Returns the updated store (caller persists it with :func:`save_history`).
    """
    results = _parse_junit_results(junit_path)
    if not results:
        return history
    run: dict[str, Any] = {
        "run_id": run_id or datetime.now(UTC).isoformat(timespec="seconds"),
        "package": package,
        "results": results,
    }
    runs = history.setdefault("runs", [])
    runs.append(run)
    history["runs"] = runs[-MAX_RUNS_KEPT:]
    return history


def save_history(history: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(history, indent=2), encoding="utf-8")


def get_flaky(
    history: dict[str, Any],
    min_runs: int = 2,
) -> list[tuple[str, dict[str, int]]]:
    """Return tests with inconsistent results across runs (AI-011 semantics).

    Returns ``[(test_name, {"passed": n, "failed": n, "error": n, "skipped": n})]``
    sorted by flakiness ratio (minority outcome / total, descending).
    """
    counts: dict[str, dict[str, int]] = {}
    for run in history.get("runs", []):
        for result in run.get("results", []):
            name = result.get("name", "unknown")
            status = result.get("status", "passed")
            bucket = counts.setdefault(name, {"passed": 0, "failed": 0, "error": 0, "skipped": 0})
            bucket[status] = bucket.get(status, 0) + 1

    flaky: list[tuple[str, dict[str, int]]] = []
    for name, c in counts.items():
        total = c["passed"] + c["failed"] + c["error"]
        if total < min_runs:
            continue
        has_pass = c["passed"] > 0
        has_fail = c["failed"] > 0 or c["error"] > 0
        if not (has_pass and has_fail):
            continue
        flaky.append((name, c))

    def _score(item: tuple[str, dict[str, int]]) -> float:
        _, c = item
        total = c["passed"] + c["failed"] + c["error"]
        minority = min(c["passed"], c["failed"] + c["error"])
        return minority / total if total else 0.0

    flaky.sort(key=_score, reverse=True)
    return flaky


def render_flaky_section(flaky: list[tuple[str, dict[str, int]]], limit: int = 3) -> str:
    """Render the PR-comment flaky block (§6); empty string when none flaky."""
    if not flaky:
        return ""
    lines = ["**Flaky (last few runs):**"]
    for name, c in flaky[:limit]:
        failures = c["failed"] + c["error"]
        lines.append(f"- `{name}` — {failures} failure(s) across {c['passed'] + failures} run(s)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flaky_history",
        description="Merge a run into the action's cached history and emit the flaky marker block.",
    )
    parser.add_argument("--junit", required=True, help="Raw pytest junit.xml path")
    parser.add_argument("--history", required=True, help="run-history.json path (read + write)")
    parser.add_argument("--package", default="", help="Package path (context)")
    parser.add_argument("--run-id", default="", help="Optional run id (default: now)")
    parser.add_argument("--output-flaky", default="", help="Write the rendered flaky block here (optional)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    junit = Path(args.junit)
    if not junit.exists():
        print(f"ERROR: junit file not found: {junit}", file=sys.stderr)
        return 2

    history = _load_history(args.history)
    history = merge_run(history, junit, package=args.package, run_id=args.run_id or None)
    save_history(history, args.history)

    flaky = get_flaky(history)
    block = render_flaky_section(flaky)
    if args.output_flaky:
        Path(args.output_flaky).write_text(block, encoding="utf-8")
    print(f"flaky: {len(flaky)} test(s) in history at {args.history}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
