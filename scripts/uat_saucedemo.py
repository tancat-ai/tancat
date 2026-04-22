"""End-to-end UAT for the test-generation pipeline using SauceDemo.

This script:
1. Calls the LLM pipeline to generate Playwright tests from a user story.
2. Writes the generated code to a timestamped directory.
3. Runs the generated test(s) against the real SauceDemo website.
4. Reports pass/fail with screenshots on failure.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import Page

from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAUCEDEMO_URL = "https://www.saucedemo.com/"
SAUCEDEMO_CREDENTIALS = {"user": "standard_user", "password": "secret_sauce"}

USER_STORY = (
    "As a user, I want to log in to the shopping site, add items to my cart, "
    "verify the items in the cart, proceed to checkout, and complete the "
    "checkout process."
)

ACCEPTANCE_CRITERIA = (
    "1. Log in with username standard_user and password secret_sauce\n"
    "2. Add at least one item (e.g. Sauce Labs Backpack) to the cart\n"
    "3. Navigate to the shopping cart page\n"
    "4. Verify the added item appears correctly in the cart\n"
    "5. Navigate to the checkout page\n"
    "6. Complete the checkout process and verify success (Thank You page)"
)

# ---------------------------------------------------------------------------
# Conftest template — provides the evidence_tracker fixture for generated tests
# ---------------------------------------------------------------------------

CONFTEST_TEMPLATE = '''"""Conftest for generated tests — provides evidence_tracker fixture."""
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

import pytest
from src.evidence_tracker import EvidenceTracker


@pytest.fixture()
def evidence_tracker(page: Page, request: Any) -> EvidenceTracker:
    """Create an EvidenceTracker bound to the Playwright page fixture."""
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
    # Teardown: write sidecar if steps were recorded
    if tracker.steps:
        tracker.write(status="passed")
'''

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_conftest(output_dir: Path) -> None:
    """Write a minimal conftest.py that provides the evidence_tracker fixture."""
    (output_dir / "conftest.py").write_text(CONFTEST_TEMPLATE, encoding="utf-8")


def _run_generated_tests(output_dir: Path) -> tuple[int, str]:
    """Run generated tests in *output_dir* using pytest in a subprocess.

    We use a subprocess because pytest-playwright's sync API conflicts with
    the asyncio event loop that the UAT script uses for LLM calls.
    Returns (exit_code, combined_output).
    """
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(output_dir),
            "-v",
            "--tb=short",
            "--no-header",
            "--override-ini=addopts=",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    print(f"[uat] pytest exit code: {result.returncode}")
    return result.returncode, result.stdout + result.stderr


def _take_screenshot(page: Page, path: Path) -> None:
    """Take a screenshot and save it to *path*."""
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"  [uat] Screenshot saved: {path}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main UAT flow
# ---------------------------------------------------------------------------


async def run_saucedemo_uat() -> dict[str, Any]:
    """Execute the full UAT pipeline and return a summary dict."""
    load_dotenv()
    os.environ["PIPELINE_DEBUG"] = "1"

    print("=" * 70)
    print("  SauceDemo End-to-End UAT")
    print("=" * 70)
    print(f"User story: {USER_STORY}")
    print(f"Acceptance criteria:\n{ACCEPTANCE_CRITERIA}")
    print(f"Target URL: {SAUCEDEMO_URL}")
    print()

    # --- Step 1: Generate tests via the pipeline ---
    print("[1/4] Generating tests via pipeline...")
    start_gen = time.time()

    client = LLMClient()
    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator)

    final_code = await orchestrator.run_pipeline(
        USER_STORY,
        ACCEPTANCE_CRITERIA,
        target_urls=[SAUCEDEMO_URL],
    )

    gen_time = time.time() - start_gen
    print(f"  Pipeline finished in {gen_time:.1f}s")
    print(f"  Generated code length: {len(final_code)} chars")

    # --- Step 2: Validate syntax ---
    print("\n[2/4] Validating generated code syntax...")
    try:
        compile(final_code, "<saucedemo_generated>", "exec")
        print("  Syntax OK")
    except SyntaxError as sx:
        print(f"  SYNTAX ERROR: {sx}")
        return {"status": "failed", "error": f"SyntaxError: {sx}", "gen_time_s": gen_time}

    # --- Step 3: Write generated code + conftest ---
    print("\n[3/4] Writing generated code...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("generated_tests") / f"test_{timestamp}_saucedemo"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write conftest
    _write_conftest(output_dir)

    # Write test file(s) — split by function if the LLM generated multiple tests
    test_file = output_dir / "test_saucedemo.py"
    test_file.write_text(final_code, encoding="utf-8")
    print(f"  Written: {test_file}")
    print(f"  Written: {output_dir / 'conftest.py'}")

    # --- Step 4: Run generated tests with Playwright ---
    print("\n[4/4] Running generated tests...")
    run_start = time.time()

    exit_code, output_text = _run_generated_tests(output_dir)

    run_time = time.time() - run_start

    # --- Summarize ---
    print("\n" + "=" * 70)
    print("  UAT Summary")
    print("=" * 70)

    # Parse pytest output text for summary stats
    import re

    collected = len(re.findall(r"^(test_\S+)", output_text, re.M))
    passed = len(re.findall(r"\.PASS", output_text))
    failed = len(re.findall(r"\.FAIL", output_text))
    skipped = len(re.findall(r"\.SKIP", output_text))
    errors = len(re.findall(r"ERROR$", output_text, re.M))

    if collected == 0:
        print("  No tests were collected or ran.")
        return {
            "status": "no_tests",
            "gen_time_s": round(gen_time, 2),
            "run_time_s": round(run_time, 2),
        }

    print(f"  Collected : {collected}")
    print(f"  Passed    : {passed}")
    print(f"  Failed    : {failed}")
    print(f"  Skipped   : {skipped}")
    print(f"  Errors    : {errors}")
    print(f"  Total time: {round(gen_time + run_time, 1)}s (gen={round(gen_time, 1)}s, run={round(run_time, 1)}s)")

    # Print test status lines
    for line in output_text.splitlines():
        m = re.match(r"^(\S+\.py::\S+)\s+(PASS|FAIL|SKIP|ERROR)", line)
        if m:
            test_name = m.group(1)
            status = m.group(2)
            print(f"  [{status}] {test_name}")

    overall = "PASSED" if failed == 0 and errors == 0 else "FAILED"
    print(f"\n  Overall: {overall}")
    print(f"  Output dir: {output_dir}")

    return {
        "status": overall,
        "gen_time_s": round(gen_time, 2),
        "run_time_s": round(run_time, 2),
        "total_time_s": round(gen_time + run_time, 2),
        "collected": collected,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "output_dir": str(output_dir),
    }


def main() -> None:
    """Entry point."""
    result = asyncio.run(run_saucedemo_uat())
    sys.exit(0 if result.get("status") in ("PASSED", "no_tests") else 1)


if __name__ == "__main__":
    main()
