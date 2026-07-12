#!/usr/bin/env python3
"""Production verification — end-to-end gate that proves the product works.

Unlike the unit test suite (which validates internals with mocks) and
UAT (which checks generated code statically), this script:

  1. Runs the full generation pipeline against known sites
  2. Executes the generated tests against the REAL website
  3. Validates the evidence output (screenshots, step logs, sidecars)
  4. Produces a clear PASS / FAIL verdict

Use this BEFORE declaring a feature done, or after changes that touch
the generation / resolution / evidence pipeline.

Usage:
    # Quick gate — both sites, runs generated tests
    python scripts/verify_production.py

    # Single site
    python scripts/verify_production.py saucedemo

    # Show the browser
    python scripts/verify_production.py --headed

    # Verbose — print generated code and test output
    python scripts/verify_production.py --verbose

Exit codes:
    0  All gates passed — product is working
    1  One or more gates failed — do NOT ship
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import textwrap
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
# Sites
# ---------------------------------------------------------------------------

SAUCEDEMO_STORY = (
    "As a user, I want to log in to the shopping site, add items to my cart, "
    "proceed to checkout, and complete the checkout process."
)

SAUCEDEMO_CONDITIONS = (
    "1. Log in with username standard_user and password secret_sauce\n"
    "2. Add at least one item (e.g. Sauce Labs Backpack) to the cart\n"
    "3. Navigate to the shopping cart page\n"
    "4. Verify the added item appears correctly in the cart\n"
    "5. Click the checkout button\n"
    "6. Fill in checkout form and submit, verify success message"
)

AUTOMATIONEXERCISE_STORY = (
    "As a customer, I want to browse products on the website and add them to my cart so that I can purchase them later."
)

AUTOMATIONEXERCISE_CONDITIONS = (
    "1. Navigate to the automationexercise.com home page and verify it loads\n"
    "2. Click the 'Products' link in the header navigation\n"
    "3. On the products page, click 'Add to cart' next to a product\n"
    "4. Verify a confirmation popup appears and close it\n"
    "5. Click the 'Cart' link in the header\n"
    "6. Verify the cart page displays the added product with details\n"
    "7. Click 'Proceed to checkout' and verify the checkout page loads"
)

SITES = {
    "saucedemo": {
        "url": "https://www.saucedemo.com",
        "user_story": SAUCEDEMO_STORY,
        "conditions": SAUCEDEMO_CONDITIONS,
        "expected_min_tests": 5,
        "expected_min_evidence_steps": 3,
    },
    "automationexercise": {
        "url": "https://automationexercise.com",
        "user_story": AUTOMATIONEXERCISE_STORY,
        "conditions": AUTOMATIONEXERCISE_CONDITIONS,
        "expected_min_tests": 5,
        "expected_min_evidence_steps": 4,
    },
}

# ---------------------------------------------------------------------------
# Conftest for generated tests
# ---------------------------------------------------------------------------

CONFTEST_TEMPLATE = textwrap.dedent('''\
    """Conftest for production verification tests."""
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
            test_package_dir=Path(request.node.fspath).parent,
        )
        yield tracker
        if tracker.steps:
            tracker.write(status="passed")
''')


# ---------------------------------------------------------------------------
# Gate results
# ---------------------------------------------------------------------------


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SiteVerification:
    site_id: str
    gates: list[Gate] = field(default_factory=list)
    generated_code: str = ""
    output_dir: Path | None = None
    error: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for g in self.gates if g.passed)

    @property
    def failed(self) -> int:
        return sum(1 for g in self.gates if not g.passed)

    @property
    def total(self) -> int:
        return len(self.gates)


# ---------------------------------------------------------------------------
# Core verification
# ---------------------------------------------------------------------------


async def verify_site(
    site_id: str,
    url: str,
    user_story: str,
    conditions: str,
    expected_min_tests: int,
    expected_min_evidence_steps: int,
    verbose: bool = False,
    pom_mode: bool = True,
) -> SiteVerification:
    """Run the full verification pipeline for one site."""
    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.test_generator import TestGenerator

    result = SiteVerification(site_id=site_id)
    sep = "\n" + "-" * 60
    print(f"{sep}\n  VERIFY: {site_id} ({'POM' if pom_mode else 'Flat'})\n{sep}")

    # --- Gate 1: LLM client ---
    try:
        # Use the provider configured in .env rather than auto-detect.
        # Auto-detect probes LM Studio (port 1234) first and can pick the
        # wrong provider when Cline has LM Studio running concurrently.
        provider = os.environ.get("LLM_PROVIDER", "") or None
        client = LLMClient(provider=provider)
        result.gates.append(Gate(f"LLM connected ({client.provider_name}/{client.model})", True))
        print(f"  [OK] LLM: {client.provider_name}/{client.model}")
    except Exception as e:
        result.gates.append(Gate("LLM connected", False, str(e)))
        result.error = str(e)
        print(f"  [FAIL] LLM: {e}")
        return result

    # --- Gate 2: Pipeline generation ---
    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=pom_mode)

    try:
        t0 = time.time()
        final_code = await orchestrator.run_pipeline(
            user_story=user_story,
            conditions=conditions,
            target_urls=[url],
        )
        gen_duration = time.time() - t0
        result.generated_code = final_code
        result.gates.append(Gate(f"Pipeline generation ({gen_duration:.1f}s)", True, f"{len(final_code)} chars"))
        print(f"  [OK] Pipeline: {gen_duration:.1f}s, {len(final_code)} chars")
    except Exception as e:
        result.gates.append(Gate("Pipeline generation", False, str(e)))
        result.error = str(e)
        print(f"  [FAIL] Pipeline: {e}")
        return result

    # --- Gate 3: No unresolved placeholders ---
    ph_matches = re.findall(r"\{\{\{\{(\w+):", final_code)
    if ph_matches:
        result.gates.append(
            Gate("No unresolved placeholders", False, f"{len(ph_matches)} remaining: {', '.join(set(ph_matches))}")
        )
        print(f"  [FAIL] Unresolved placeholders: {set(ph_matches)}")
    else:
        result.gates.append(Gate("No unresolved placeholders", True, "clean"))
        print("  [OK] No unresolved placeholders")

    # --- Gate 4: Test function count ---
    test_funcs = re.findall(r"^def\s+test_\w+", final_code, re.M)
    ok = len(test_funcs) >= expected_min_tests
    result.gates.append(Gate(f"Test functions >= {expected_min_tests}", ok, f"{len(test_funcs)} found"))
    print(f"  [{'OK' if ok else 'FAIL'}] Test functions: {len(test_funcs)} (need >= {expected_min_tests})")

    # --- Gate 5: Evidence tracker present ---
    ev_calls = final_code.count("evidence_tracker.")
    ok = ev_calls > 0
    result.gates.append(Gate("Evidence tracker calls", ok, f"{ev_calls} calls"))
    print(f"  [{'OK' if ok else 'FAIL'}] Evidence tracker: {ev_calls} calls")

    # --- Gate 6: pytest.mark.evidence decorators ---
    ev_marks = final_code.count("@pytest.mark.evidence")
    ok = ev_marks > 0
    result.gates.append(Gate("pytest.mark.evidence decorators", ok, f"{ev_marks} found"))
    print(f"  [{'OK' if ok else 'FAIL'}] @pytest.mark.evidence: {ev_marks}")

    # --- Gate 7: No pytest.skip (or minimal) ---
    skip_lines = [line.strip() for line in final_code.splitlines() if "pytest.skip(" in line]
    ok = len(skip_lines) == 0
    result.gates.append(Gate("No pytest.skip", ok, f"{len(skip_lines)} skip line(s)"))
    print(f"  [{'OK' if ok else 'WARN'}] pytest.skip: {len(skip_lines)} lines")

    # --- Gate 8: POM imports (if POM mode) ---
    if pom_mode:
        has_pom = "from pages." in final_code or "import pages" in final_code
        result.gates.append(Gate("POM imports present", has_pom, "found" if has_pom else "missing"))
        print(f"  [{'OK' if has_pom else 'FAIL'}] POM imports: {'found' if has_pom else 'missing'}")

    # --- Gate 9: Unresolved from pipeline metadata ---
    pipeline_result = orchestrator.last_result
    if pipeline_result:
        unresolved = pipeline_result.unresolved_placeholders
        ok = len(unresolved) == 0
        result.gates.append(Gate("Pipeline resolved all placeholders", ok, f"{len(unresolved)} unresolved"))
        print(f"  [{'OK' if ok else 'FAIL'}] Pipeline unresolved: {len(unresolved)}")

    # --- Gate 10: Write and execute tests ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = PROJECT_ROOT / "generated_tests" / f"verify_{site_id}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    result.output_dir = output_dir

    (output_dir / "conftest.py").write_text(CONFTEST_TEMPLATE, encoding="utf-8")
    (output_dir / f"test_{site_id}.py").write_text(final_code, encoding="utf-8")

    # Write POM pages
    if pom_mode and pipeline_result and pipeline_result.generated_page_objects:
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        (pages_dir / "__init__.py").write_text("", encoding="utf-8")
        for page_obj in pipeline_result.generated_page_objects:
            (pages_dir / f"{page_obj.module_name}.py").write_text(page_obj.module_source, encoding="utf-8")
        print(f"  [INFO] Wrote {len(pipeline_result.generated_page_objects)} POM page objects")

    if verbose:
        print(f"\n{'=' * 60}")
        print("GENERATED CODE:")
        print(final_code)
        print(f"{'=' * 60}\n")

    # Execute the generated tests
    print(f"\n  [RUN] Executing tests against {site_id}...")
    try:
        run_start = time.time()
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(output_dir),
                "-o",
                "addopts=",
                "-o",
                f"pythonpath={PROJECT_ROOT}",
                "--browser=chromium",
                "--screenshot=only-on-failure",
                "-v",
                "--tb=short",
                "--no-header",
            ],
            capture_output=True,
            text=True,
            timeout=max(60, min(180, len(test_funcs) * 25)),
            cwd=str(PROJECT_ROOT),
        )
        run_duration = time.time() - run_start
        run_pass = proc.returncode == 0

        # Parse results
        passed_match = re.search(r"(\d+) passed", proc.stdout)
        failed_match = re.search(r"(\d+) failed", proc.stdout)
        error_match = re.search(r"(\d+) errors?", proc.stdout)
        skipped_match = re.search(r"(\d+) skipped", proc.stdout)

        detail_parts = []
        if passed_match:
            detail_parts.append(f"{passed_match.group(1)} passed")
        if failed_match:
            detail_parts.append(f"{failed_match.group(1)} failed")
        if error_match:
            detail_parts.append(f"{error_match.group(1)} errors")
        if skipped_match:
            detail_parts.append(f"{skipped_match.group(1)} skipped")

        result.gates.append(
            Gate(
                f"Test execution ({run_duration:.1f}s)",
                run_pass,
                ", ".join(detail_parts) if detail_parts else f"exit {proc.returncode}",
            )
        )
        print(f"  [{'OK' if run_pass else 'FAIL'}] Execution: {', '.join(detail_parts)}, {run_duration:.1f}s")

        if not run_pass and verbose:
            print(f"\n  PYTEST STDOUT:\n{proc.stdout}")
            print(f"  PYTEST STDERR:\n{proc.stderr}")

        # Save raw test output for debugging
        (output_dir / "pytest_output.txt").write_text(proc.stdout, encoding="utf-8")
        if proc.stderr:
            (output_dir / "pytest_stderr.txt").write_text(proc.stderr, encoding="utf-8")

    except subprocess.TimeoutExpired:
        result.gates.append(Gate("Test execution", False, "timeout after {max(60, min(180, len(test_funcs) * 25))}s"))
        print("  [FAIL] Execution: timeout after {max(60, min(180, len(test_funcs) * 25))}s")
    except Exception as e:
        result.gates.append(Gate("Test execution", False, str(e)))
        print(f"  [FAIL] Execution: {e}")

    # --- Gate 11: Evidence output validation ---
    evidence_dir = output_dir / "evidence"
    if evidence_dir.exists():
        evidence_files = list(evidence_dir.glob("*.json"))
        screenshot_files = list(output_dir.rglob("*.png"))

        ok = len(evidence_files) > 0
        result.gates.append(Gate("Evidence JSON generated", ok, f"{len(evidence_files)} file(s)"))
        print(f"  [{'OK' if ok else 'FAIL'}] Evidence JSON: {len(evidence_files)} file(s)")

        # Validate evidence content
        if evidence_files:
            total_steps = 0
            for ef in evidence_files:
                try:
                    data = json.loads(ef.read_text(encoding="utf-8"))
                    steps = data.get("steps", [])
                    total_steps += len(steps)
                    # Check steps have meaningful content
                    for step in steps:
                        action = step.get("action", "")
                        if not action:
                            ok = False
                except json.JSONDecodeError, KeyError:
                    ok = False

            result.gates.append(
                Gate(
                    f"Evidence steps >= {expected_min_evidence_steps}",
                    total_steps >= expected_min_evidence_steps,
                    f"{total_steps} total steps",
                )
            )
            print(f"  [{'OK' if total_steps >= expected_min_evidence_steps else 'FAIL'}] Evidence steps: {total_steps}")

        # Check screenshots on failure
        if screenshot_files:
            result.gates.append(Gate("Failure screenshots captured", True, f"{len(screenshot_files)} screenshot(s)"))
    else:
        result.gates.append(Gate("Evidence JSON generated", False, "evidence dir missing"))
        print("  [FAIL] Evidence directory not found")

    # --- Summary ---
    p = result.passed
    f = result.failed
    print(f"\n  [{site_id}] {p}/{result.total} gates passed ({f} failed)")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Production verification gate")
    parser.add_argument("site", nargs="*", default=[], help="Site(s) to verify")
    parser.add_argument("--all-sites", action="store_true", help="Verify all sites")
    parser.add_argument("--flat", action="store_true", help="Flat mode (default: POM)")
    parser.add_argument("--headed", action="store_true", help="Show browser")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print generated code and test output")
    parser.add_argument("--keep", action="store_true", help="Keep output directories (default: delete on pass)")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    load_dotenv()

    if args.headed:
        import os

        os.environ["PLAYWRIGHT_HEADLESS"] = "0"

    pom_mode = not args.flat

    if args.all_sites:
        site_ids = list(SITES.keys())
    elif args.site:
        site_ids = list(args.site)
    else:
        # Default: both sites
        site_ids = list(SITES.keys())

    print("=" * 60)
    print(f"PRODUCTION VERIFICATION — {'POM' if pom_mode else 'Flat'} mode")
    print(f"Sites: {', '.join(site_ids)}")
    print("=" * 60)

    results: list[SiteVerification] = []
    for site_id in site_ids:
        if site_id not in SITES:
            print(f"\n[ERROR] Unknown site: {site_id}. Available: {', '.join(SITES.keys())}")
            return 1
        config = SITES[site_id]
        r = await verify_site(
            site_id=site_id,
            url=config["url"],
            user_story=config["user_story"],
            conditions=config["conditions"],
            expected_min_tests=config["expected_min_tests"],
            expected_min_evidence_steps=config["expected_min_evidence_steps"],
            verbose=args.verbose,
            pom_mode=pom_mode,
        )
        results.append(r)

    # Overall
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_checks = sum(r.total for r in results)

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total_passed}/{total_checks} gates passed ({total_failed} failed)")

    # Cleanup
    if not args.keep:
        for r in results:
            if r.output_dir and r.output_dir.exists():
                if total_failed == 0:
                    # Clean up on full success
                    import shutil as _shutil

                    _shutil.rmtree(r.output_dir, ignore_errors=True)
                else:
                    print(f"  [KEPT] {r.output_dir} (failed — keep for debugging)")

    if total_failed > 0:
        print(f"\n{'=' * 60}")
        print("VERDICT: FAIL — Do NOT ship. Fix the failing gates above.")
        print(f"{'=' * 60}")
        return 1
    else:
        print(f"\n{'=' * 60}")
        print("VERDICT: PASS — Product is working as intended.")
        print(f"{'=' * 60}")
        return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = __import__("io").TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    sys.exit(asyncio.run(main()))
