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
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _EVAL_DIR.parent.parent
for _path in (str(_PROJECT_ROOT), str(_EVAL_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from eval_evidence import MissingEvidenceError, RunEvidence, read_run_evidence  # noqa: E402
from eval_metrics import HarnessReport, StoryResult, count_false_greens  # noqa: E402
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


def _kept_story_state(evidence: RunEvidence) -> dict[str, dict[str, Any]]:
    """The per-story test state the run itself recorded in ``results.json``."""
    state: dict[str, dict[str, Any]] = {}
    for entry in evidence.results.get("stories", []) or []:
        if isinstance(entry, dict) and entry.get("story_id"):
            state[str(entry["story_id"])] = entry
    return state


def _carry_kill_state(
    story: StoryResult,
    recorded: dict[str, Any] | None,
    per_test: dict[str, str],
) -> None:
    """Carry a killed run's state through a re-score (d-0084, t-1163).

    The run already wrote the truth: ``results.json`` says ``tests_timed_out`` and
    the counts, and the kept ``junit/`` holds the outcomes that got in before the
    kill. A re-score must copy that rather than recompute it and default it to
    zero - recomputing turned a killed story into a clean partial and dropped the
    KILLED marker entirely.

    Absence stays absent (``None``) so the summary can say "not recorded". A value
    the run did not write is never rendered as a clean 0: a zero failures count on
    a killed story is a claim, and this function must not invent one.
    """
    if not recorded or not recorded.get("tests_timed_out"):
        return

    story.tests_timed_out = True

    failed = recorded.get("tests_failed")
    if not isinstance(failed, int):
        # The kept junit can answer this one when results.json predates d-0084.
        failed = sum(1 for outcome in per_test.values() if outcome in ("FAILED", "ERROR")) if per_test else None
    story.tests_failed = failed

    collected = recorded.get("tests_collected")
    story.tests_collected = collected if isinstance(collected, int) else None

    not_run = recorded.get("tests_not_run")
    if not isinstance(not_run, int):
        not_run = max(collected - story.tests_executed, 0) if isinstance(collected, int) else None
    story.tests_not_run = not_run

    story.tests_kill_clock = str(recorded.get("tests_kill_clock") or "")
    story.tests_kill_limit_s = recorded.get("tests_kill_limit_s")
    story.tests_kill_elapsed_s = recorded.get("tests_kill_elapsed_s")


def _full_dataset_label() -> str:
    """Name the dataset the gate is read against, without a number that drifts.

    t-1187: the old wording said "the full 113", which went stale the moment a
    golden was added. The count is read from the committed dataset at print time;
    when it cannot be read, the phrase alone says it.
    """
    dataset_dir = _EVAL_DIR / "dataset"
    try:
        total = 0
        for golden_file in sorted(dataset_dir.glob("*.json")):
            data = json.loads(golden_file.read_text(encoding="utf-8"))
            for criterion in data.get("golden_resolutions", []):
                total += len(criterion.get("placeholders", []))
    except OSError, ValueError:
        return "the full dataset"
    return f"the full dataset ({total} placeholders)" if total else "the full dataset"


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
    kept = _kept_story_state(evidence)
    for story in results:
        code = evidence.code_map.get(story.story_id, "")
        per_test = evidence.per_test(story.story_id)
        passed = sum(1 for outcome in per_test.values() if outcome == "PASSED")
        story.tests_executed = len(per_test)
        story.tests_passed = passed
        story.tests_false_positive = count_false_greens(story, code, per_test, passed)
        # t-1163: a killed story must not re-score as a clean partial.
        _carry_kill_state(story, kept.get(story.story_id), per_test)

    report = HarnessReport(stories=results)

    # B-101: same report/warn alignment figure as a live run, recomputed from
    # the kept evidence's code_map. Never a pass/fail gate.
    try:
        from eval_alignment import compute_alignment

        report.alignment = compute_alignment(dataset_dir, evidence.code_map).to_dict()
    except Exception:  # never let the warn metric break a re-score
        report.alignment = None

    return report


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
        print(
            f"GATE 1 (resolution accuracy): {correct}/{total} = {report.resolution_accuracy():.1f}%  "
            f"(the >= 90% target is read against {_full_dataset_label()} in full --regenerate mode "
            "- see scripts/eval/README.md)"
        )
        print(f"GATE 2 (hollow passes):       {hollow}  (need 0)")
        print("=" * 70)

    known = _known_scores()
    if known and not args.json:
        recorded_at = known.get("recorded_at")
        prefix = "Recorded last re-score" + (f" (as of {recorded_at})" if recorded_at else "")
        gate2 = known.get("gate2_false_greens")
        gate2_text = "not measured in this mode" if gate2 is None else str(gate2)
        # j-0244: a recorded figure carries its mode and its seed. When the
        # record has them, print them - a bare percentage is what let the
        # with-pack headline read as a pure resolution score (d-0060).
        figure_label = str(known.get("label") or "").strip()
        if figure_label:
            print(f"\n{prefix}: {figure_label}; gate 2 {gate2_text}.")
        else:
            print(
                f"\n{prefix}: "
                f"gate 1 {known.get('gate1_correct')}/{known.get('gate1_total')} "
                f"({known.get('gate1_accuracy_pct')}%), gate 2 {gate2_text}."
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
