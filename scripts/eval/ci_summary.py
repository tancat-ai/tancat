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

from eval_runner import EvalRunner  # noqa: E402


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
    report = runner.run(mode=args.mode, persist=False)

    lines: list[str] = [
        "# Evaluation Harness Results",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Stories | {len(report.stories)} |",
        f"| Resolution accuracy | {report.resolution_accuracy():.1f}% |",
        f"| Skeleton completeness | {report.skeleton_completeness():.1f}% |",
        f"| Tests executed | {report.total_tests_executed} |",
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
    if args.min_accuracy is not None:
        acc = report.resolution_accuracy()
        if acc < args.min_accuracy:
            lines.append(f"⚠️ **Resolution accuracy {acc:.1f}% is below threshold {args.min_accuracy}%**")
            lines.append("")
        else:
            lines.append(f"✅ Evaluation passed: {acc:.1f}% >= {args.min_accuracy}%")
            lines.append("")

    output_path = Path(args.output)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Summary written to {output_path}")

    # Also print to stdout for CI logs
    print(report.to_summary())


if __name__ == "__main__":
    main()
