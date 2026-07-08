#!/usr/bin/env python3
"""Reliability diagnostic for the test generation engine.

Runs the pipeline against multiple user stories and sites, executes the
generated tests, and reports pass/fail rates to identify inconsistency patterns.

Usage:
    python scripts/reliability_test.py --help
    python scripts/reliability_test.py --stories all --runs 3
    python scripts/reliability_test.py --stories saucedemo --runs 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict[str, Any]] = {
    "saucedemo_login": {
        "url": "https://www.saucedemo.com",
        "user_story": (
            "As a user, I want to log in to the SauceDemo shopping site "
            "so that I can browse and purchase products."
        ),
        "conditions": (
            "1. Navigate to the saucedemo.com home page\n"
            "2. Enter username 'standard_user' in the username field\n"
            "3. Enter password 'secret_sauce' in the password field\n"
            "4. Click the 'Login' button\n"
            "5. Verify the products page loads after successful login\n"
            "6. Verify product items are displayed on the page\n"
        ),
    },
    "saucedemo_full": {
        "url": "https://www.saucedemo.com",
        "user_story": (
            "As a user, I want to log in, add items to my cart, "
            "and complete checkout on the SauceDemo site."
        ),
        "conditions": (
            "1. Log in with username standard_user and password secret_sauce\n"
            "2. Add at least one item (e.g. Sauce Labs Backpack) to the cart\n"
            "3. Navigate to the shopping cart page\n"
            "4. Verify the added item appears correctly in the cart\n"
            "5. Navigate to the checkout page\n"
            "6. Complete the checkout process and verify success\n"
        ),
    },
    "automationexercise_browse": {
        "url": "https://automationexercise.com",
        "user_story": (
            "As a shopper, I want to browse products on automationexercise.com "
            "and add items to my cart."
        ),
        "conditions": (
            "1. Navigate to the automationexercise.com home page\n"
            "2. Click the 'Products' link in the header navigation\n"
            "3. On the products page, click 'Add to cart' next to a product\n"
            "4. Verify a confirmation message appears\n"
            "5. Click the 'Cart' link in the header\n"
            "6. Verify the cart page displays the added product\n"
        ),
    },
    "automationexercise_register": {
        "url": "https://automationexercise.com",
        "user_story": (
            "As a new user, I want to register an account on automationexercise.com "
            "so that I can log in and make purchases."
        ),
        "conditions": (
            "1. Navigate to the automationexercise.com home page\n"
            "2. Click the 'Signup / Login' link in the header\n"
            "3. On the login page, click 'New User Signup'\n"
            "4. Fill in the name and email fields\n"
            "5. Click the 'Signup' button\n"
            "6. Verify the account is created and login form appears\n"
        ),
    },
    "automationexercise_contact": {
        "url": "https://automationexercise.com",
        "user_story": (
            "As a user, I want to use the contact form on automationexercise.com "
            "to send a message to the site owners."
        ),
        "conditions": (
            "1. Navigate to the automationexercise.com home page\n"
            "2. Click the 'Contact Us' link in the header\n"
            "3. Fill in the name field\n"
            "4. Fill in the email field\n"
            "5. Fill in the subject field\n"
            "6. Fill in the message field\n"
            "7. Upload an image using the file upload field\n"
            "8. Click the 'Submit' button\n"
            "9. Verify a success message is displayed\n"
        ),
    },
}


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    scenario: str
    run_num: int
    generation_duration: float = 0.0
    run_duration: float = 0.0
    generated_code: str = ""
    test_count: int = 0
    skip_count: int = 0
    unresolved_count: int = 0
    pages_scraped: int = 0
    test_pass: bool | None = None
    errors: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_scenario(
    scenario_id: str,
    config: dict[str, Any],
    run_num: int,
    output_base: Path,
) -> RunResult:
    """Run the pipeline for one scenario."""
    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.test_generator import TestGenerator

    result = RunResult(scenario=scenario_id, run_num=run_num)

    try:
        client = LLMClient()
    except Exception as e:
        result.errors.append(f"LLMClient init failed: {e}")
        return result

    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=True)

    # Pipeline
    try:
        start = time.time()
        final_code = await orchestrator.run_pipeline(
            user_story=config["user_story"],
            conditions=config["conditions"],
            target_urls=[config["url"]],
        )
        result.generation_duration = time.time() - start
        result.generated_code = final_code
    except Exception as e:
        result.errors.append(f"Pipeline failed: {e}")
        return result

    # Analysis
    result.test_count = len(re.findall(r"^def\s+test_\w+", final_code, re.M))
    result.skip_count = len(re.findall(r"pytest\.skip\(", final_code))
    result.unresolved_count = result.skip_count  # skips == unresolved placeholders

    pipeline_result = orchestrator.last_result
    if pipeline_result:
        result.pages_scraped = len(pipeline_result.scraped_pages)
        result.unresolved_count = len(pipeline_result.unresolved_placeholders)

    # Save generated code for inspection
    run_dir = output_base / f"{scenario_id}_run{run_num}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "test_generated.py").write_text(final_code, encoding="utf-8")

    # Save page objects
    if pipeline_result and pipeline_result.generated_page_objects:
        pages_dir = run_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        (pages_dir / "__init__.py").write_text("", encoding="utf-8")
        for page_obj in pipeline_result.generated_page_objects:
            (pages_dir / f"{page_obj.module_name}.py").write_text(
                page_obj.module_source, encoding="utf-8"
            )
            result.generated_files.append(f"pages/{page_obj.module_name}.py")

    # Try to run the tests
    import subprocess
    confest_content = '''"""Conftest for generated tests."""
from pathlib import Path
from typing import Any
from playwright.sync_api import Page
import pytest
from src.evidence_tracker import EvidenceTracker

@pytest.fixture()
def evidence_tracker(page: Page, request: Any) -> EvidenceTracker:
    test_name = getattr(request.node, "name", "unknown_test")
    condition_ref = ""
    story_ref = ""
    for mark in request.node.iter_markers("evidence"):
        condition_ref = mark.kwargs.get("condition_ref", condition_ref)
        story_ref = mark.kwargs.get("story_ref", story_ref)
    tracker = EvidenceTracker(
        page=page,
        test_name=test_name,
        condition_ref=condition_ref or "unknown",
        story_ref=story_ref or "unknown",
    )
    yield tracker
    if tracker.steps:
        tracker.write(status="passed")
'''
    (run_dir / "conftest.py").write_text(confest_content, encoding="utf-8")

    result.generated_files.append("test_generated.py")

    try:
        run_start = time.time()
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", str(run_dir),
                "-o", "addopts=",
                "-o", f"pythonpath={run_dir}",
                "--browser=chromium",
                "-v", "--tb=line", "--no-header",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        result.run_duration = time.time() - run_start
        result.test_pass = proc.returncode == 0

        # Parse test results
        for line in proc.stdout.splitlines():
            if "PASSED" in line or "FAILED" in line or "SKIPPED" in line:
                result.generated_files.append(line.strip()[:100])

        if not result.test_pass:
            # Capture first error
            for line in proc.stderr.splitlines() + proc.stdout.splitlines():
                if "Error" in line or "error" in line or "FAILED" in line:
                    result.errors.append(line.strip()[:200])
                    if len(result.errors) >= 5:
                        break

    except subprocess.TimeoutExpired:
        result.errors.append("Test execution timed out (120s)")
        result.test_pass = False
    except Exception as e:
        result.errors.append(f"Test execution error: {e}")

    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[RunResult]) -> None:
    """Print a summary report."""
    print(f"\n{'=' * 80}")
    print("RELIABILITY DIAGNOSTIC REPORT")
    print(f"{'=' * 80}")

    scenarios = sorted({r.scenario for r in results})
    for scenario in scenarios:
        scenario_results = [r for r in results if r.scenario == scenario]
        print(f"\n--- {scenario} ({len(scenario_results)} runs) ---")

        tests_gen = [r.test_count for r in scenario_results]
        skips = [r.skip_count for r in scenario_results]
        unresolved = [r.unresolved_count for r in scenario_results]
        pages = [r.pages_scraped for r in scenario_results]
        passed = sum(1 for r in scenario_results if r.test_pass)
        total = len(scenario_results)

        print(f"  Tests generated:    min={min(tests_gen)} max={max(tests_gen)} avg={sum(tests_gen)/len(tests_gen):.1f}")
        print(f"  pytest.skip lines:  min={min(skips)} max={max(skips)} avg={sum(skips)/len(skips):.1f}")
        print(f"  Unresolved ph:      min={min(unresolved)} max={max(unresolved)} avg={sum(unresolved)/len(unresolved):.1f}")
        print(f"  Pages scraped:      min={min(pages)} max={max(pages)} avg={sum(pages)/len(pages):.1f}")
        print(f"  Test execution:     {passed}/{total} passed ({100*passed/total:.0f}%)")

        for r in scenario_results:
            status = "PASS" if r.test_pass else ("FAIL" if r.test_pass is False else "N/A")
            error_summary = "; ".join(r.errors[:2]) if r.errors else ""
            print(f"    Run {r.run_num}: {r.test_count} tests, {r.skip_count} skips, "
                  f"{r.pages_scraped} pages, {status:.4s} | gen={r.generation_duration:.0f}s run={r.run_duration:.0f}s")
            if error_summary:
                print(f"      Error: {error_summary}")

    print(f"\n{'=' * 80}")
    overall_passed = sum(1 for r in results if r.test_pass)
    overall_total = len([r for r in results if r.test_pass is not None])
    print(f"Overall: {overall_passed}/{overall_total} tests passed "
          f"({100*overall_passed/overall_total:.0f}%)" if overall_total else "No tests executed")
    print(f"{'=' * 80}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Test generation reliability diagnostic")
    parser.add_argument(
        "--stories",
        default="all",
        help="Comma-separated scenario IDs or 'all' (default: all)",
    )
    parser.add_argument("--runs", type=int, default=3, help="Runs per scenario (default: 3)")
    parser.add_argument(
        "--output",
        default="generated_tests/reliability_results",
        help="Output directory (default: generated_tests/reliability_results)",
    )
    parser.add_argument("--save", default="reliability_report.json", help="JSON report path")
    args = parser.parse_args()

    # Resolve scenarios
    if args.stories == "all":
        chosen = list(SCENARIOS.keys())
    else:
        chosen = [s.strip() for s in args.stories.split(",")]
        for s in chosen:
            if s not in SCENARIOS:
                print(f"Unknown scenario: {s}. Available: {list(SCENARIOS.keys())}")
                sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[RunResult] = []
    total_runs = len(chosen) * args.runs
    completed = 0

    for scenario_id in chosen:
        config = SCENARIOS[scenario_id]
        for run_num in range(1, args.runs + 1):
            completed += 1
            print(f"\n[{completed}/{total_runs}] {scenario_id} run {run_num}")
            r = await run_scenario(scenario_id, config, run_num, output_dir)
            results.append(r)

            status = "PASS" if r.test_pass else ("FAIL" if r.test_pass is False else "ERR")
            print(f"  -> {r.test_count} tests, {r.skip_count} skips, {r.pages_scraped} pages, {status}")
            if r.errors:
                print(f"  -> Errors: {r.errors[0][:120]}")

    # Report
    print_report(results)

    # Save JSON
    save_path = Path(args.save)
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "scenarios": chosen,
        "runs_per_scenario": args.runs,
        "results": [
            {
                "scenario": r.scenario,
                "run_num": r.run_num,
                "generation_duration": r.generation_duration,
                "run_duration": r.run_duration,
                "test_count": r.test_count,
                "skip_count": r.skip_count,
                "unresolved_count": r.unresolved_count,
                "pages_scraped": r.pages_scraped,
                "test_pass": r.test_pass,
                "errors": r.errors,
                "generated_files_dir": f"{args.output}/{r.scenario}_run{r.run_num}",
            }
            for r in results
        ],
    }
    save_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"Report saved to {save_path}")


if __name__ == "__main__":
    asyncio.run(main())
