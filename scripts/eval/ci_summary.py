#!/usr/bin/env python
"""ci_summary.py — Generate markdown summary for CI artifacts.

Usage:
    uv run python scripts/eval/ci_summary.py
    uv run python scripts/eval/ci_summary.py --mode full
    uv run python scripts/eval/ci_summary.py --min-accuracy 75
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_SCRIPT_DIR))

from eval_metrics import HarnessReport  # noqa: E402
from eval_runner import EvalRunner  # noqa: E402


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate eval harness markdown summary")
    parser.add_argument("--mode", default="static", choices=["static", "full"])
    parser.add_argument("--min-accuracy", type=float, default=None)
    parser.add_argument("--output", default=".eval_summary.md")
    args = parser.parse_args()

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
        # d-0138: the persist rule now lives in the runner, so a model-bearing
        # mode reaches it here too. Say the rule once and stop, instead of a
        # traceback or a full leg that silently writes nothing.
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    lines = build_summary(report, args.min_accuracy)

    output_path = Path(args.output)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Summary written to {output_path}")

    # Also print to stdout for CI logs
    print(report.to_summary())


if __name__ == "__main__":
    main()
