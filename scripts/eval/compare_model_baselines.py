"""Diff two model baselines (before/after fine-tuning) in one command.

Workflow (docs/sessions/2026-08-09_unsloth_training_runbook.md §6) — capture a
baseline BEFORE training, re-run AFTER pointing :8080 at the fine-tuned model,
then compare:

    python scripts/eval/eval_model_baseline.py \\
        --save training_data/model_baseline_finetuned.json
    python scripts/eval/compare_model_baselines.py

Auto-discovery: when no explicit paths are given, every
``training_data/model_baseline_*.json`` is collected; if exactly two exist the
OLDER file (mtime) is treated as "before", the newer as "after". Explicit
``--before`` / ``--after`` always win.

Per-story rows are matched by ``story_head`` so regressions/improvements are
attributed to individual stories, not just aggregate rates.

Exit codes: 0 = no regressions (improved or unchanged), 1 = usage/IO error,
2 = at least one regression (matches the eval-harness quality-gate
convention).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GLOB = PROJECT_ROOT / "training_data" / "model_baseline_*.json"

#: (key, display label, good direction) — "higher"/"lower" moves are good;
#: "info" metrics are reported but never flagged as regressions.
AGGREGATE_METRICS: list[tuple[str, str, str]] = [
    ("valid_skeleton_rate", "Valid skeleton rate", "higher"),
    ("criteria_cover_rate", "Criteria cover rate", "higher"),
    ("hallucinated_login_rate", "Hallucinated login", "lower"),
    ("total_skip_lines", "Skip lines", "lower"),
    ("total_placeholders", "Placeholders", "info"),
    ("errors", "LLM errors", "lower"),
]

_FLOAT_EPS = 1e-9


def load_baseline(path: Path) -> dict:
    """Load + validate a baseline JSON written by ``eval_model_baseline.py``.

    Raises:
        OSError: file unreadable.
        ValueError: not a baseline file (missing ``per_story``).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "per_story" not in data:
        raise ValueError(f"{path} is not a model baseline file (missing 'per_story')")
    return data


def index_stories(data: dict) -> dict[str, dict]:
    """Index ``per_story`` rows by ``story_head`` (the story's first 60 chars)."""
    return {str(row.get("story_head", "")): row for row in data.get("per_story", [])}


def _is_rate(value: object) -> bool:
    """True only for float metrics (0..1 rates); ints are counts."""
    return isinstance(value, float)


def _regressed(direction: str, before: object, after: object) -> bool:
    """True when a numeric metric moved against its good direction."""
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return False
    if isinstance(before, bool) or isinstance(after, bool):
        return False
    if direction == "higher":
        return after < before - _FLOAT_EPS
    if direction == "lower":
        return after > before + _FLOAT_EPS
    return False


def aggregate_deltas(before: dict, after: dict) -> list[dict]:
    """Per-metric before/after/delta rows with a regression verdict."""
    rows: list[dict] = []
    for key, label, direction in AGGREGATE_METRICS:
        b = before.get(key, 0)
        a = after.get(key, 0)
        rows.append(
            {
                "key": key,
                "label": label,
                "before": b,
                "after": a,
                "delta": a - b if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None,
                "direction": direction,
                "regression": _regressed(direction, b, a),
            }
        )
    return rows


def story_regressed(before: dict, after: dict) -> bool:
    """True when a story's skeleton quality moved against any gate."""
    return (
        (before.get("valid_skeleton") is True and after.get("valid_skeleton") is not True)
        or (before.get("criteria_cover") is True and after.get("criteria_cover") is not True)
        or (before.get("hallucinated_login") is False and after.get("hallucinated_login") is not False)
        or (int(after.get("skip_lines", 0) or 0) > int(before.get("skip_lines", 0) or 0))
        or (before.get("error") is None and after.get("error") is not None)
    )


def story_improved(before: dict, after: dict) -> bool:
    """True when a story's skeleton quality moved toward any gate."""
    return (
        (before.get("valid_skeleton") is not True and after.get("valid_skeleton") is True)
        or (before.get("criteria_cover") is not True and after.get("criteria_cover") is True)
        or (before.get("hallucinated_login") is not False and after.get("hallucinated_login") is False)
        or (int(before.get("skip_lines", 0) or 0) > int(after.get("skip_lines", 0) or 0))
        or (before.get("error") is not None and after.get("error") is None)
    )


def compare_stories(
    before_rows: dict[str, dict],
    after_rows: dict[str, dict],
) -> tuple[list[dict], list[dict], list[str]]:
    """Match stories by ``story_head``; return (regressed, improved, unmatched)."""
    regressed: list[dict] = []
    improved: list[dict] = []
    unmatched: list[str] = []
    for head, a in after_rows.items():
        b = before_rows.get(head)
        if b is None:
            unmatched.append(head)
            continue
        if story_regressed(b, a):
            regressed.append({"story_head": head, "before": b, "after": a})
        elif story_improved(b, a):
            improved.append({"story_head": head, "before": b, "after": a})
    return regressed, improved, unmatched


def build_report(before_path: Path, after_path: Path) -> dict:
    """Full machine-readable comparison report."""
    before = load_baseline(before_path)
    after = load_baseline(after_path)
    before_index = index_stories(before)
    after_index = index_stories(after)
    regressed, improved, unmatched = compare_stories(before_index, after_index)
    deltas = aggregate_deltas(before, after)
    aggregate_regressed = any(d["regression"] for d in deltas)
    verdict = "regression" if (aggregate_regressed or regressed) else "no-regression"
    return {
        "before": {"path": str(before_path), "meta": before.get("model"), "stories": len(before_index)},
        "after": {"path": str(after_path), "meta": after.get("model"), "stories": len(after_index)},
        "deltas": deltas,
        "stories_matched": len(after_index) - len(unmatched),
        "story_regressions": regressed,
        "story_improvements": improved,
        "story_unmatched": unmatched,
        "verdict": verdict,
    }


def _fmt(value: object) -> str:
    if _is_rate(value):
        return f"{value:.1%}"
    return str(value)


def _fmt_delta(row: dict) -> str:
    b, a = row["before"], row["after"]
    if _is_rate(b) and _is_rate(a):
        pp = (a - b) * 100
        return f"{pp:+.1f}pp"
    return f"{a - b:+d}"


def print_report(report: dict) -> None:
    """Human-readable rendering of a build_report() result."""
    b, a = report["before"], report["after"]
    print("=== MODEL BASELINE COMPARISON ===")
    print(f"  before: {b['path']}")
    print(f"    model: {b['meta']} | stories: {b['stories']}")
    print(f"  after : {a['path']}")
    print(f"    model: {a['meta']} | stories: {a['stories']}")
    print()
    print(f"  {'metric':<22} {'before':>10} {'after':>10} {'delta':>10}  verdict")
    for d in report["deltas"]:
        verdict = "regression" if d["regression"] else "ok"
        print(f"  {d['label']:<22} {_fmt(d['before']):>10} {_fmt(d['after']):>10} {_fmt_delta(d):>10}  {verdict}")
    print()
    regressed, improved, unmatched = (
        report["story_regressions"],
        report["story_improvements"],
        report["story_unmatched"],
    )
    print(
        f"  story-level: {report['stories_matched']} matched, "
        f"{len(regressed)} regressed, {len(improved)} improved, {len(unmatched)} unmatched"
    )
    if regressed:
        print("  regressed stories:")
        for r in regressed:
            print(f"    - {r['story_head']}")
    if improved:
        print("  improved stories:")
        for r in improved:
            print(f"    + {r['story_head']}")
    if unmatched:
        print("  unmatched (only in 'after', story set may have changed):")
        for head in unmatched:
            print(f"    ? {head}")
    print()
    if report["verdict"] == "regression":
        print("VERDICT: regressions detected - training delta is NOT positive.")
    else:
        print("VERDICT: no regressions - training delta is neutral or positive.")


def compare(before_path: Path, after_path: Path, *, json_out: bool = False) -> int:
    """Run the comparison; returns the process exit code (0/2)."""
    report = build_report(before_path, after_path)
    if json_out:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)
    return 2 if report["verdict"] == "regression" else 0


def _discover() -> tuple[Path, Path]:
    """Auto-pick (before, after) from training_data/model_baseline_*.json."""
    candidates = sorted(DEFAULT_GLOB.parent.glob(DEFAULT_GLOB.name))
    if not candidates:
        raise SystemExit(
            f"No {DEFAULT_GLOB} found — run eval_model_baseline.py first, or pass --before/--after explicitly."
        )
    if len(candidates) == 1:
        raise SystemExit(
            f"Only one baseline found ({candidates[0].name}) - re-run "
            "eval_model_baseline.py after training to create the 'after' file, "
            "or pass --before/--after explicitly."
        )
    if len(candidates) > 2:
        raise SystemExit(
            f"{len(candidates)} baselines found — ambiguous; pass --before/--after explicitly.\n"
            f"  {', '.join(p.name for p in candidates)}"
        )
    # Older file = "before" (captured pre-training), newer = "after".
    ordered = sorted(candidates, key=lambda p: (p.stat().st_mtime, p.name))
    return ordered[0], ordered[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, help="Baseline JSON (pre-training); auto-discovered when omitted")
    parser.add_argument("--after", type=Path, help="Baseline JSON (post-training); auto-discovered when omitted")
    parser.add_argument("--json", action="store_true", help="Print machine-readable report JSON")
    args = parser.parse_args()

    try:
        before, after = (args.before, args.after) if args.before and args.after else _discover()
        if args.before and not args.after:
            raise SystemExit("--after is required when --before is given.")
        if args.after and not args.before:
            raise SystemExit("--before is required when --after is given.")
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    sys.exit(compare(before, after, json_out=args.json))


if __name__ == "__main__":
    main()
