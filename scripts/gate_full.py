#!/usr/bin/env python3
"""gate_full.py — the full verification gate chain, in one command.

Test-Pack Restructure (2026-08-03 CLI review, work item 3): verification was
fragmented across manual commands — smoke, unit pytest, eval-static,
verify_production, export_gate — with no single "is the product ready?" entry
point. This script chains them in dependency order and reports a pass/fail
summary, exiting non-zero on the first gate that fails.

Gate order (each is a prerequisite for the next):

    Gate 1  smoke             offline, <1s   resolver/parser/import integrity
    Gate 2  unit pytest       offline         default suite (mock/offline layer)
    Gate 3  eval-static       offline, CI     resolution accuracy vs golden keys
    Gate 4  verify_production browser+LLM     full pipeline → execute → evidence
    Gate 5  export_gate       browser+local   exports are runnable + validated

Gates 4–5 need a running LLM (LM Studio on :8080) and, for live sites,
network — they are the *manual/dev* gates. Gates 1–3 are offline and CI-able;
CI already runs 1, 2, and 3 independently (smoke / test / eval-static jobs).

Usage:
    python scripts/gate_full.py                 # all gates
    python scripts/gate_full.py --offline       # gates 1-3 only (no LLM/network)
    python scripts/gate_full.py --skip <n>      # skip gate n (e.g. --skip 4)
    python scripts/gate_full.py --pytest-args "-k resolv"   # pass extra args to unit tests

Exit codes:
    0  All gates passed
    1  A gate failed (reported; chain stops)
    2  Usage error
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Windows consoles default to cp1252 — force UTF-8 so box-drawing output
# doesn't crash the script on the very first print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PYTHON = sys.executable

# Offline unit layer: the default pytest run (excludes slow/integration,
# which is exactly the mock/offline layer the test-pack restructure keeps).
UNIT_ADDOPTS = ["-q", "--tb=short", "-p", "no:cacheprovider"]


@dataclass
class GateResult:
    name: str
    command: list[str]
    passed: bool
    duration_s: float
    output_tail: str = ""


def _run_gate(name: str, command: list[str], timeout_s: int) -> GateResult:
    print(f"\n━━━ Gate: {name} — {' '.join(command)}")
    t0 = time.time()
    try:
        proc = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout_s)
        passed = proc.returncode == 0
        output = (proc.stdout or "") + (proc.stderr or "")
        tail = "\n".join(output.strip().splitlines()[-12:])
        status = "PASS" if passed else "FAIL"
        print(f"  └─ {status} in {time.time() - t0:.1f}s (exit {proc.returncode})")
        return GateResult(name, command, passed, time.time() - t0, tail)
    except subprocess.TimeoutExpired:
        print(f"  └─ FAIL in {time.time() - t0:.1f}s (timeout after {timeout_s}s)")
        return GateResult(name, command, False, time.time() - t0, f"TIMEOUT after {timeout_s}s")


def gate1_smoke() -> GateResult:
    return _run_gate("smoke", [PYTHON, "scripts/smoke.py", "--json"], timeout_s=120)


def gate2_unit(args: argparse.Namespace) -> GateResult:
    command = [PYTHON, "-m", "pytest", *UNIT_ADDOPTS, *args.pytest_args]
    return _run_gate("unit pytest (mock/offline layer)", command, timeout_s=args.unit_timeout)


def gate3_eval_static(args: argparse.Namespace) -> GateResult:
    command = [
        PYTHON,
        "scripts/eval/eval_harness.py",
        "run",
        "--mode",
        "static",
        f"--min-accuracy={args.min_accuracy}",
        "--no-persist",
    ]
    return _run_gate(f"eval-static (≥{args.min_accuracy}%)", command, timeout_s=300)


def gate4_verify_production() -> GateResult:
    return _run_gate("verify_production", [PYTHON, "scripts/verify_production.py"], timeout_s=1800)


def gate5_export_gate() -> GateResult:
    return _run_gate("export_gate (golden fixture)", [PYTHON, "scripts/export_gate.py"], timeout_s=1800)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gate_full",
        description="Full verification gate chain: smoke → unit → eval-static → verify_production → export_gate",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run only the offline gates (1-3) — no LLM/network needed",
    )
    parser.add_argument(
        "--skip",
        type=int,
        nargs="*",
        default=[],
        help="Gate number(s) to skip, e.g. --skip 4 5",
    )
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=79.0,
        help="Minimum eval-static resolution accuracy %% (default 79, CI floor)",
    )
    parser.add_argument(
        "--unit-timeout",
        type=int,
        default=1800,
        help="Timeout seconds for the unit pytest gate (default 1800)",
    )
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Extra arguments forwarded to the unit pytest gate (use -- before them)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skip = set(args.skip)

    gates: list[tuple[int, str, Callable[[], GateResult]]] = [
        (1, "smoke", gate1_smoke),
        (2, "unit pytest", lambda: gate2_unit(args)),
        (3, "eval-static", lambda: gate3_eval_static(args)),
        (4, "verify_production", gate4_verify_production),
        (5, "export_gate", gate5_export_gate),
    ]
    if args.offline:
        gates = [g for g in gates if g[0] <= 3]

    print("=" * 72)
    print("FULL VERIFICATION GATE — tancat-ai/tancat")
    print(f"mode: {'OFFLINE (gates 1-3)' if args.offline else 'FULL (gates 1-5)'}")
    print("=" * 72)

    results: list[GateResult] = []
    for number, name, fn in gates:
        if number in skip:
            print(f"\n━━━ Gate {number}: {name} — SKIPPED")
            continue
        result = fn()
        results.append(result)
        if not result.passed:
            print("\n" + "─" * 72)
            print(f"GATE {number} ({name}) FAILED — chain stopped.\n")
            print("Last output:")
            print(result.output_tail)
            print("\n" + "─" * 72)
            return 1

    print("\n" + "=" * 72)
    print("ALL GATES PASSED ✓")
    for result in results:
        print(f"  ✓ {result.name:28s} ({result.duration_s:.1f}s)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
