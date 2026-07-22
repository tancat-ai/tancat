#!/usr/bin/env python
"""eval_harness.py — CLI entry point for the Automated Evaluation Harness.

Standalone CLI. Subcommands:
    run       Execute evaluation against golden keys
    baseline  Save current results as the reference baseline
    compare   Compare current results against the baseline
    dataset   Validate golden key files

Usage:
    python scripts/eval/eval_harness.py run --static
    python scripts/eval/eval_harness.py run --full
    python scripts/eval/eval_harness.py baseline --save
    python scripts/eval/eval_harness.py compare
    python scripts/eval/eval_harness.py dataset --validate
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Resolve project root (scripts/eval is one level deep)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATASET_DIR = _PROJECT_ROOT / "scripts" / "eval" / "dataset"
_CAPTURES_DIR = _PROJECT_ROOT / "scripts" / "eval" / "captures"
_DB_PATH = _PROJECT_ROOT / "evidence" / "run_results.sqlite"
_TEST_OUTPUT_DIR = _PROJECT_ROOT / "generated_tests"
_BASELINE_PATH = _PROJECT_ROOT / "scripts" / "eval" / "baseline.json"


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute the evaluation harness."""
    from eval_runner import EvalRunner

    dataset_dir = _DATASET_DIR if args.dataset is None else Path(args.dataset)
    captures_dir = _CAPTURES_DIR if args.captures is None else Path(args.captures)
    db_path = _DB_PATH if args.db is None else Path(args.db)
    test_output = _TEST_OUTPUT_DIR if args.test_output is None else Path(args.test_output)

    if not dataset_dir.exists():
        print(f"ERROR: Dataset directory not found: {dataset_dir}", file=sys.stderr)
        return 1
    if not captures_dir.exists():
        print(f"ERROR: Captures directory not found: {captures_dir}", file=sys.stderr)
        return 1

    runner = EvalRunner(
        dataset_dir=dataset_dir,
        code_dir=captures_dir,
        db_path=db_path,
        test_output_dir=test_output if args.mode == "full" else None,
        regenerate=args.regenerate,
    )

    report = runner.run(
        mode=args.mode,
        pytest_timeout=args.pytest_timeout,
        persist=not args.no_persist,
    )

    print(report.to_summary())

    # Exit code based on accuracy threshold
    if args.min_accuracy is not None:
        accuracy = report.resolution_accuracy()
        if accuracy < args.min_accuracy:
            print(f"\nWARNING: Accuracy {accuracy:.1f}% below threshold {args.min_accuracy:.1f}%", file=sys.stderr)
            return 2
    return 0


# ---------------------------------------------------------------------------
# Subcommand: baseline
# ---------------------------------------------------------------------------


def _cmd_baseline(args: argparse.Namespace) -> int:
    """Save or display the reference baseline."""
    if args.save:
        from eval_runner import EvalRunner

        runner = EvalRunner(
            dataset_dir=_DATASET_DIR,
            code_dir=_CAPTURES_DIR,
            db_path=_DB_PATH,
        )
        report = runner.run(mode="static", persist=True)
        _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _BASELINE_PATH.write_text(json.dumps(report.to_dict(), indent=2))
        print(f"Baseline saved to {_BASELINE_PATH}")
        print(report.to_summary())
        return 0

    # Display existing baseline
    if _BASELINE_PATH.exists():
        data = json.loads(_BASELINE_PATH.read_text())
        print(json.dumps(data, indent=2))
    else:
        print("No baseline found. Run with --save to create one.", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# Subcommand: compare
# ---------------------------------------------------------------------------


def _cmd_compare(args: argparse.Namespace) -> int:
    """Compare current results against the baseline."""
    if not _BASELINE_PATH.exists():
        print("No baseline found. Run 'baseline --save' first.", file=sys.stderr)
        return 1

    from eval_metrics import HarnessReport, compute_deltas, deltas_to_report
    from eval_runner import EvalRunner

    baseline_data = json.loads(_BASELINE_PATH.read_text())
    baseline = HarnessReport.from_dict(baseline_data)

    runner = EvalRunner(
        dataset_dir=_DATASET_DIR,
        code_dir=_CAPTURES_DIR,
        db_path=_DB_PATH,
    )
    current = runner.run(mode=args.mode, persist=True)

    print("\n" + "=" * 70)
    print("BASELINE COMPARISON")
    print("=" * 70)

    deltas = compute_deltas(baseline, current)
    print(deltas_to_report(deltas))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: dataset
# ---------------------------------------------------------------------------


def _cmd_dataset(args: argparse.Namespace) -> int:
    """Validate golden key files."""
    errors: list[str] = []
    warnings: list[str] = []
    count = 0

    for golden_file in sorted(_DATASET_DIR.glob("*.json")):
        count += 1
        try:
            from golden_validator import load_golden_key

            golden = load_golden_key(golden_file)

            if args.validate:
                # Check each golden resolution
                for i, crit in enumerate(golden.get("golden_resolutions", [])):
                    for j, ph in enumerate(crit.get("placeholders", [])):
                        if not ph.get("expected_locator"):
                            errors.append(f"{golden_file.name}: placeholder [{i}][{j}] missing expected_locator")
                        if ph.get("action") not in ("GOTO", "FILL", "CLICK", "ASSERT"):
                            errors.append(
                                f"{golden_file.name}: placeholder [{i}][{j}] invalid action '{ph.get('action')}'"
                            )

        except Exception as exc:
            errors.append(f"{golden_file.name}: {exc}")

    print(f"Dataset validation: {count} files checked")
    if warnings:
        for w in warnings:
            print(f"  WARNING: {w}")
    if errors:
        for error_msg in errors:
            print(f"  ERROR: {error_msg}")
        print(f"\n{len(errors)} error(s) found.", file=sys.stderr)
        return 1

    print(f"  OK: All {count} files valid")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_harness",
        description="Automated Evaluation Harness for AI-Playwright-Test-Generator",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- run ---
    run_parser = subparsers.add_parser("run", help="Execute evaluation")
    run_parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate code via the actual pipeline before validating",
    )
    run_parser.add_argument("--dataset", help="Path to dataset directory")
    run_parser.add_argument("--captures", help="Path to captures directory")
    run_parser.add_argument("--db", help="Path to SQLite database")
    run_parser.add_argument("--test-output", help="Path to generated test files")
    run_parser.add_argument(
        "--pytest-timeout",
        type=float,
        default=120.0,
        help="Timeout per pytest run in seconds (default: 120)",
    )
    run_parser.add_argument(
        "--min-accuracy",
        type=float,
        default=None,
        help="Minimum resolution accuracy threshold (%%). Exit code 2 if below.",
    )
    run_parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip persisting results to SQLite",
    )

    # --- baseline ---
    baseline_parser = subparsers.add_parser("baseline", help="Manage baseline")
    baseline_parser.add_argument("--save", action="store_true", help="Save current results as baseline")

    # --- compare ---
    compare_parser = subparsers.add_parser("compare", help="Compare against baseline")
    compare_parser.add_argument(
        "--mode",
        choices=["static", "full"],
        default="static",
        help="Evaluation mode (default: static)",
    )

    # --- dataset ---
    dataset_parser = subparsers.add_parser("dataset", help="Validate golden keys")
    dataset_parser.add_argument("--validate", action="store_true", help="Deep-validate all golden key fields")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        return 0

    handlers = {
        "run": _cmd_run,
        "baseline": _cmd_baseline,
        "compare": _cmd_compare,
        "dataset": _cmd_dataset,
    }

    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
