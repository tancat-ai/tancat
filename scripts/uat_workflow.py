"""3-stage UAT workflow for the AI-Playwright-Test-Generator.

This script provides a structured workflow for running UAT tests:
  Stage 1: Syntax-only validation (no LLM, runs in seconds)
  Stage 2: Full pipeline against a target URL (LLM required, 3-5 min)
  Stage 3: External site test (optional, never blocking Cline)

Each stage writes a structured JSON result to uat_result.json so Cline
can poll results with a simple file read instead of parsing stdout.

Usage:
    # Stage 1: Syntax-only (against mock site)
    python scripts/uat_workflow.py stage1

    # Stage 2: Full pipeline (default: automationexercise.com)
    python scripts/uat_workflow.py stage2 [--url URL] [--timeout N]

    # Stage 3: External site (optional)
    python scripts/uat_workflow.py stage3 --url https://www.automationexercise.com

    # Custom output path
    python scripts/uat_workflow.py stage2 --output my_result.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure the project root is on sys.path so cli packages resolve.
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

load_dotenv(dotenv_path=_project_root / ".env")

# Default URLs per stage
DEFAULT_URLS: dict[str, str] = {
    "stage1": "http://localhost:8000/mock_insurance_site.html",
    "stage2": "https://www.automationexercise.com",
    "stage3": "https://www.automationexercise.com",
}


def _write_result(result: dict[str, Any], output_path: str | None) -> None:
    """Write structured JSON result to file."""
    path = output_path or str(_project_root / "uat_result.json")
    Path(path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[RESULT] JSON result written to: {path}")


def _run_stage1(output_path: str | None = None, timeout: int = 600) -> dict[str, Any]:
    """Stage 1: Syntax-only validation against mock site (no LLM).

    This stage scrapes the mock site and validates generated code syntax.
    It runs in seconds since no LLM call is made for test generation.
    """
    from scripts.cli_e2e_validation import run_validation

    print("=" * 70)
    print("  Stage 1: Syntax-only validation (mock site)")
    print("=" * 70)
    print(f"  Target: {DEFAULT_URLS['stage1']}")
    print()

    start = time.time()
    result = run_validation(
        url=DEFAULT_URLS["stage1"],
        timeout=timeout,
        output_path=output_path,
    )
    elapsed = time.time() - start

    json_result = {
        "stage": 1,
        "status": "PASS" if result["all_valid"] else "FAIL",
        "generated_files": len(result["generated_files"]),
        "files": [str(f) for f in result["generated_files"]],
        "syntax_errors": [s["error"] for s in result["syntax_results"] if s["error"]],
        "errors": result["errors"],
        "elapsed_s": round(elapsed, 2),
        "target_url": DEFAULT_URLS["stage1"],
    }
    _write_result(json_result, output_path)

    print(f"\n  Stage 1 complete in {elapsed:.1f}s")
    return json_result


def _run_stage2(
    url: str | None = None,
    output_path: str | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """Stage 2: Full pipeline against target URL (LLM required).

    This stage runs the complete pipeline: LLM generation + scraping +
    placeholder resolution. Expect 3-5 minutes depending on model speed.
    """
    from scripts.cli_e2e_validation import run_validation

    target = url or DEFAULT_URLS["stage2"]
    print("=" * 70)
    print("  Stage 2: Full pipeline (LLM required)")
    print("=" * 70)
    print(f"  Target: {target}")
    print(f"  LLM timeout: {timeout}s")
    print()

    start = time.time()
    result = run_validation(
        url=target,
        timeout=timeout,
        output_path=output_path,
    )
    elapsed = time.time() - start

    json_result = {
        "stage": 2,
        "status": "PASS" if result["all_valid"] else "FAIL",
        "generated_files": len(result["generated_files"]),
        "files": [str(f) for f in result["generated_files"]],
        "syntax_errors": [s["error"] for s in result["syntax_results"] if s["error"]],
        "errors": result["errors"],
        "elapsed_s": round(elapsed, 2),
        "target_url": target,
    }
    _write_result(json_result, output_path)

    print(f"\n  Stage 2 complete in {elapsed:.1f}s")
    return json_result


def _run_stage3(
    url: str | None = None,
    output_path: str | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """Stage 3: External site test (optional, never blocking Cline).

    This stage is identical to Stage 2 but targets an external site.
    It should be run independently, never while Cline is active.
    """
    from scripts.cli_e2e_validation import run_validation

    target = url or DEFAULT_URLS["stage3"]
    print("=" * 70)
    print("  Stage 3: External site test (run independently)")
    print("=" * 70)
    print(f"  Target: {target}")
    print(f"  LLM timeout: {timeout}s")
    print("  WARNING: Do not run while Cline is using LM Studio.")
    print()

    start = time.time()
    result = run_validation(
        url=target,
        timeout=timeout,
        output_path=output_path,
    )
    elapsed = time.time() - start

    json_result = {
        "stage": 3,
        "status": "PASS" if result["all_valid"] else "FAIL",
        "generated_files": len(result["generated_files"]),
        "files": [str(f) for f in result["generated_files"]],
        "syntax_errors": [s["error"] for s in result["syntax_results"] if s["error"]],
        "errors": result["errors"],
        "elapsed_s": round(elapsed, 2),
        "target_url": target,
    }
    _write_result(json_result, output_path)

    print(f"\n  Stage 3 complete in {elapsed:.1f}s")
    return json_result


def main() -> int:
    """Entry point for the UAT workflow script."""
    parser = argparse.ArgumentParser(description="3-stage UAT workflow for AI-Playwright-Test-Generator")
    parser.add_argument(
        "stage",
        type=str,
        choices=["stage1", "stage2", "stage3"],
        help="Which stage to run: stage1 (syntax-only), stage2 (full pipeline), stage3 (external site)",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Target URL (overrides default for the stage)",
        default=None,
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="LLM timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path for JSON result file (default: uat_result.json)",
        default=None,
    )
    args = parser.parse_args()

    stage_map = {
        "stage1": _run_stage1,
        "stage2": _run_stage2,
        "stage3": _run_stage3,
    }

    runner = stage_map[args.stage]
    result = runner(url=args.url, output_path=args.output, timeout=args.timeout)  # type: ignore[operator]

    # Exit code: 0 for PASS, 1 for FAIL
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
