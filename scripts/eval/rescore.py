#!/usr/bin/env python
"""rescore.py — recompute the held-out gate score from a run's kept evidence.

**No model call, no browser, no live site.** Gate 1 (resolution accuracy) is
static: the kept emitted code against the golden keys. Gate 2 (hollow passes)
is re-applied from the kept per-test outcomes. Both use the same rules as a live
run (``eval_metrics.count_false_greens``), so a re-score and a run agree.

The evidence comes from a run made with ``--evidence-dir`` (see
``scripts/eval/eval_evidence.py``). A run directory that is missing its evidence
is reported as *cannot recompute*, never read as a zero.

Usage::

    python scripts/eval/rescore.py --run-dir scratch/eval_runs/2026-09-30_heldout
    python scripts/eval/rescore.py --run-dir <dir> --expect-gate1 82 --expect-gate2 3

Exit codes: 0 = scored, 2 = a score did not match ``--expect-*``,
5 = evidence missing or incomplete (the score cannot be recomputed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _EVAL_DIR.parent.parent
for _path in (str(_PROJECT_ROOT), str(_EVAL_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from eval_evidence import MissingEvidenceError, read_run_evidence  # noqa: E402
from eval_metrics import HarnessReport, count_false_greens  # noqa: E402
from golden_validator import validate_dataset  # noqa: E402

# The last re-score that was recorded, before the evidence was deleted. The next
# live held-out run must reproduce this (or explain the difference).
KNOWN_GATE_SCORES_PATH = _EVAL_DIR / "known_gate_scores.json"


def _known_scores() -> dict:
    """Return the recorded gate scores, or {} when the file is absent."""
    if not KNOWN_GATE_SCORES_PATH.is_file():
        return {}
    try:
        return json.loads(KNOWN_GATE_SCORES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {}


def rescore(run_dir: Path, dataset_dir: Path) -> HarnessReport:
    """Recompute the gate score from *run_dir*'s kept evidence.

    Raises:
        MissingEvidenceError: the run directory is missing evidence, so the
            score cannot be recomputed.
    """
    evidence = read_run_evidence(run_dir)

    # Gate 1: static, from the kept emitted code against the golden keys.
    results = validate_dataset(dataset_dir, evidence.code_map, verdict_map=evidence.verdict_map)

    # Gate 2: re-apply the false-green rule to the kept per-test outcomes.
    for story in results:
        code = evidence.code_map.get(story.story_id, "")
        per_test = evidence.per_test(story.story_id)
        passed = sum(1 for outcome in per_test.values() if outcome == "PASSED")
        story.tests_executed = len(per_test)
        story.tests_passed = passed
        story.tests_false_positive = count_false_greens(story, code, per_test, passed)

    return HarnessReport(stories=results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rescore",
        description="Recompute the held-out gate score from a run's kept evidence (no model call).",
    )
    parser.add_argument("--run-dir", required=True, help="Run directory kept by eval_harness --evidence-dir")
    parser.add_argument(
        "--dataset", help="Golden keys directory (default: the run's manifest, else scripts/eval/dataset)"
    )
    parser.add_argument(
        "--expect-gate1", type=int, help="Fail (exit 2) unless the correct-resolution count equals this"
    )
    parser.add_argument("--expect-gate2", type=int, help="Fail (exit 2) unless the false-green count equals this")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if args.dataset:
        dataset_dir = Path(args.dataset)
    else:
        # Prefer the dataset the run recorded; fall back to the committed one.
        try:
            recorded = read_run_evidence(run_dir).manifest.get("dataset")
        except MissingEvidenceError:
            recorded = None
        dataset_dir = Path(recorded) if recorded else _EVAL_DIR / "dataset"

    try:
        report = rescore(run_dir, dataset_dir)
    except MissingEvidenceError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "The score cannot be recomputed. Re-run the held-out set with --evidence-dir to produce scorable evidence.",
            file=sys.stderr,
        )
        return 5

    correct = report.correct_resolutions
    total = report.total_placeholders
    hollow = report.total_false_positives

    if args.json:
        print(
            json.dumps(
                {
                    "run_dir": str(run_dir),
                    "gate1_correct": correct,
                    "gate1_total": total,
                    "gate1_accuracy_pct": round(report.resolution_accuracy(), 1),
                    "gate2_false_greens": hollow,
                },
                indent=1,
            )
        )
    else:
        print(report.to_summary())
        print("\n" + "=" * 70)
        print(f"GATE 1 (resolution accuracy): {correct}/{total} = {report.resolution_accuracy():.1f}%  (need >= 90%)")
        print(f"GATE 2 (hollow passes):       {hollow}  (need 0)")
        print("=" * 70)

    known = _known_scores()
    if known and not args.json:
        print(
            "\nRecorded last re-score: "
            f"gate 1 {known.get('gate1_correct')}/{known.get('gate1_total')} "
            f"({known.get('gate1_accuracy_pct')}%), gate 2 {known.get('gate2_false_greens')}."
        )

    exit_code = 0
    if args.expect_gate1 is not None and correct != args.expect_gate1:
        print(f"MISMATCH: gate 1 correct = {correct}, expected {args.expect_gate1}", file=sys.stderr)
        exit_code = 2
    if args.expect_gate2 is not None and hollow != args.expect_gate2:
        print(f"MISMATCH: gate 2 hollow passes = {hollow}, expected {args.expect_gate2}", file=sys.stderr)
        exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
