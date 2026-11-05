#!/usr/bin/env python
"""ci_summary.py — Generate markdown summary for CI artifacts.

Usage:
    uv run python scripts/eval/ci_summary.py                       # static, offline
    uv run python scripts/eval/ci_summary.py --mode full           # refused (see below)
    uv run python scripts/eval/ci_summary.py --run-group ci-<sha>         --db ci_eval.sqlite                                        # from the store
    uv run python scripts/eval/ci_summary.py --min-accuracy 75

d-0138 follow-up: a summary must never RE-RUN a leg to report on it. A
model-bearing run is a measurement and may not be dispatched with
``persist=False`` (EvalRunner.run refuses it), so the CI path names the leg the
run step already stored and this script reads it back. Only the offline
``--mode static`` path still computes, because it spends nothing and writes
nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_SCRIPT_DIR))

from eval_metrics import HarnessReport  # noqa: E402
from eval_runner import EvalRunner, load_run_groups  # noqa: E402


def build_summary(report: HarnessReport, min_accuracy: float | None = None) -> list[str]:
    """Build the markdown summary lines for one report.

    Pure, so the test-count source line can be tested without running a harness
    pass. d-0050: the count never renders alone - the source that produced it
    (junit / log / none) is printed beside it, so a bare zero cannot read as
    data.
    """
    lines: list[str] = [
        "# Evaluation Harness Results",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Stories | {len(report.stories)} |",
        f"| Resolution accuracy | {report.resolution_accuracy():.1f}% |",
        f"| Skeleton completeness | {report.skeleton_completeness():.1f}% |",
        f"| Tests executed | {report.total_tests_executed} (source: {report.tests_count_source}) |",
        f"| Test pass rate | {report.test_pass_rate():.1f}% |",
        f"| False positive rate | {report.false_positive_rate():.1f}% |",
        "",
        "## Per-Story Breakdown",
        "",
        "| Story | Site | Accuracy | Skeletons |",
        "|-------|------|----------|-----------|",
    ]
    for s in report.stories:
        acc = sum(r.matched for r in s.resolutions) / len(s.resolutions) * 100 if s.resolutions else 0
        lines.append(f"| {s.story_id} | {s.site} | {acc:.0f}% | {s.criteria_with_skeletons}/{s.total_criteria} |")
    lines.append("")

    # Threshold check
    if min_accuracy is not None:
        acc = report.resolution_accuracy()
        if acc < min_accuracy:
            lines.append(f"⚠️ **Resolution accuracy {acc:.1f}% is below threshold {min_accuracy}%**")
            lines.append("")
        else:
            lines.append(f"✅ Evaluation passed: {acc:.1f}% >= {min_accuracy}%")
            lines.append("")
    return lines


def report_from_store(db_path: str | Path, run_group: str) -> tuple[HarnessReport | None, list[str]]:
    """Rebuild the report from the rows a leg already wrote - never by re-running.

    ``persist_results`` stores each story's own ``HarnessReport.to_dict()`` in
    ``raw_report``, so the numbers the summary prints are the ones the run
    computed. Returns the report (or ``None`` when the leg is absent) and a list
    of human lines saying what could not be read.
    """
    groups = load_run_groups(Path(db_path))
    if run_group not in groups:
        available = ", ".join(sorted(key for key in groups if key)) or "none"
        return None, [f"no stored leg named '{run_group}' in {db_path}. Legs in the store: {available}"]
    stories = []
    unreadable = 0
    for row in groups[run_group]:
        raw = row.get("raw_report")
        if not raw:
            unreadable += 1
            continue
        stored = HarnessReport.from_dict(json.loads(str(raw)))
        stories.extend(stored.stories)
    notes = [f"{unreadable} row(s) had no stored report and are not in this summary"] if unreadable else []
    return HarnessReport(stories=stories), notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate eval harness markdown summary")
    parser.add_argument("--mode", default="static", choices=["static", "full"])
    parser.add_argument("--run-group", default="", help="Read this stored leg instead of re-running the harness")
    parser.add_argument("--db", default="", help="Store holding --run-group (default: evidence/run_results.sqlite)")
    parser.add_argument("--min-accuracy", type=float, default=None)
    parser.add_argument("--output", default=".eval_summary.md")
    args = parser.parse_args(argv)

    notes: list[str] = []
    report: HarnessReport | None = None
    if args.run_group.strip():
        # d-0138 follow-up: the leg is already in the store; read it, do not
        # dispatch a second run just to summarise the first.
        db_path = Path(args.db) if args.db else _PROJECT_ROOT / "evidence" / "run_results.sqlite"
        report, notes = report_from_store(db_path, args.run_group.strip())
    else:
        dataset_dir = _PROJECT_ROOT / "scripts" / "eval" / "dataset"
        captures_dir = _PROJECT_ROOT / "scripts" / "eval" / "captures"
        runner = EvalRunner(
            dataset_dir=dataset_dir,
            code_dir=captures_dir,
            db_path=_PROJECT_ROOT / "evidence" / "run_results.sqlite",
        )
        try:
            report = runner.run(mode=args.mode, persist=False)
        except ValueError as exc:
            # d-0138: the persist rule now lives in the runner. A model-bearing
            # mode may not be re-run here at all - name the leg instead.
            print(f"ERROR: {exc}", file=sys.stderr)
            print(
                "This summary does not re-run a leg: pass --run-group <id> --db <store> "
                "to summarise a leg the run step already stored.",
                file=sys.stderr,
            )
            return 2

    lines = (
        build_summary(report, args.min_accuracy)
        if report is not None
        else [
            "# Evaluation Harness Results",
            "",
            "No summary: the leg was not stored, so there are no numbers to report.",
            "",
        ]
    )
    if notes:
        lines.extend(["", "## Notes", ""] + [f"- {note}" for note in notes])

    output_path = Path(args.output)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Summary written to {output_path}")
    for note in notes:
        print(f"NOTE: {note}", file=sys.stderr)

    if report is None:
        # The run step was supposed to store this leg. Say so instead of
        # printing a friendly summary over nothing.
        return 3

    # Also print to stdout for CI logs
    print(report.to_summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
