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
from typing import Any, TypedDict

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.verify_baseline import (  # noqa: E402
    BaselineComparison,
    compare_run,
    load_baseline,
    stable_gate_key,
)

DEFAULT_BASELINE_PATH = PROJECT_ROOT / "scripts" / "verify_production_baseline.json"

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


class SiteConfig(TypedDict):
    """Per-site configuration for the verification run."""

    url: str
    user_story: str
    conditions: str
    expected_min_tests: int
    expected_min_evidence_steps: int


SITES: dict[str, SiteConfig] = {
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

    @property
    def key(self) -> str:
        """Stable identity — strips the dynamic duration/provider suffix."""
        return stable_gate_key(self.name)


@dataclass
class SiteVerification:
    site_id: str
    gates: list[Gate] = field(default_factory=list)
    generated_code: str = ""
    output_dir: Path | None = None
    error: str = ""
    unresolved_placeholders: list[str] = field(default_factory=list)
    failed_tests: list[str] = field(default_factory=list)

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
    from src.journey_models import CredentialProfile
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
    # Demo sites gate cart/checkout behind auth (saucedemo's credentials are
    # printed on its own login page). Without a session the stateful scraper
    # captures the login wall, not the cart — same defaults as scripts/eval.
    credential_profile: CredentialProfile | None = None
    if site_id == "saucedemo":
        credential_profile = CredentialProfile(
            label="saucedemo",
            username=os.environ.get("SAUCEDEMO_USERNAME", "standard_user"),
            password=os.environ.get("SAUCEDEMO_PASSWORD", "secret_sauce"),
        )
    orchestrator = TestOrchestrator(
        generator,
        pom_mode=pom_mode,
        credential_profile=credential_profile,
    )

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
        result.unresolved_placeholders = list(unresolved)
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
    # Per-suite cap. Live sites plus LLM-variance in the generated waits mean a
    # 7-test suite can legitimately exceed the old 30s/test budget (observed:
    # automationexercise 7 tests ran past 210s while every test passed or was
    # skipped — tests 05/06 alone took 54.6s each). 60s/test with a 120s floor
    # keeps a runaway suite bounded without failing a healthy slow run.
    exec_timeout = max(120, min(600, len(test_funcs) * 60))
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
                "--timeout=120",
                "-v",
                "--tb=short",
                "--no-header",
            ],
            capture_output=True,
            text=True,
            timeout=exec_timeout,
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
        result.failed_tests = _parse_failed_tests(proc.stdout)
        print(f"  [{'OK' if run_pass else 'FAIL'}] Execution: {', '.join(detail_parts)}, {run_duration:.1f}s")

        if not run_pass and verbose:
            print(f"\n  PYTEST STDOUT:\n{proc.stdout}")
            print(f"  PYTEST STDERR:\n{proc.stderr}")

        # Save raw test output for debugging
        (output_dir / "pytest_output.txt").write_text(proc.stdout, encoding="utf-8")
        if proc.stderr:
            (output_dir / "pytest_stderr.txt").write_text(proc.stderr, encoding="utf-8")

        # AI-042-F3: chain the suite's fully-passing tests into GOTO flows
        # (same hook as the UI/CLI run service — keeps the product gate's
        # evidence feeding flow memory too). Best-effort, never breaks the run.
        try:
            from src.flow_memory import FlowMemoryStore

            FlowMemoryStore().learn_suite_flows(output_dir / "evidence")
        except Exception:
            pass

    except subprocess.TimeoutExpired as exc:
        # The suite cap fired — salvage whatever completed so the verdict is
        # informative instead of a bare "timeout" gate.
        partial_stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        (output_dir / "pytest_output.txt").write_text(partial_stdout, encoding="utf-8")
        result.failed_tests = _parse_failed_tests(partial_stdout)
        evidence_files = (
            list((output_dir / "evidence").glob("*.evidence.json")) if (output_dir / "evidence").exists() else []
        )
        run_duration = time.time() - run_start
        # Count only tests whose evidence sidecar records a terminal status;
        # the in-flight test's sidecar exists but still reads "running".
        completed = 0
        for ef in evidence_files:
            try:
                status = json.loads(ef.read_text(encoding="utf-8")).get("test", {}).get("status", "")
            except json.JSONDecodeError, OSError:
                status = ""
            if status in ("passed", "failed", "skipped"):
                completed += 1
        detail = (
            f"timed out after {exec_timeout:.0f}s — {completed}/{len(test_funcs)} tests completed "
            f"({len(evidence_files)} evidence file(s))"
        )
        result.gates.append(Gate("Test execution", False, detail))
        print(f"  [FAIL] Execution: {detail} ({run_duration:.1f}s)")
    except Exception as e:
        result.gates.append(Gate("Test execution", False, str(e)))
        print(f"  [FAIL] Execution: {e}")

    # --- Gate 11: Evidence output validation ---
    evidence_dir = output_dir / "evidence"
    if evidence_dir.exists():
        evidence_files = list(evidence_dir.glob("*.json"))
        # Evidence screenshots default to lossless WebP; PNG is still accepted
        # (AITEST_EVIDENCE_IMAGE_FORMAT=png, or evidence captured pre-2026-09-11).
        screenshot_files = [p for ext in ("*.webp", "*.png") for p in output_dir.rglob(ext)]

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
    parser.add_argument(
        "--baseline",
        nargs="?",
        const=str(DEFAULT_BASELINE_PATH),
        default=None,
        metavar="FILE",
        help=(
            "Compare the run against a recorded expected-red baseline and fail only on NEW failures "
            f"(default file: {DEFAULT_BASELINE_PATH.name})"
        ),
    )
    parser.add_argument(
        "--save-baseline",
        nargs="?",
        const=str(DEFAULT_BASELINE_PATH),
        default=None,
        metavar="FILE",
        help="Record the current run as the expected-red baseline, then exit",
    )
    parser.add_argument(
        "--check-baseline",
        nargs="?",
        const=str(DEFAULT_BASELINE_PATH),
        default=None,
        metavar="FILE",
        help="Validate the baseline file offline (no pipeline run) — used by CI",
    )
    return parser.parse_args()


def _check_baseline(path: Path) -> int:
    """Offline validation of a baseline file — no LLM, no browser."""
    print(f"Validating expected-red baseline: {path}")
    try:
        baseline = load_baseline(path)
    except (OSError, ValueError) as exc:
        print(f"  [FAIL] {exc}")
        return 1

    unknown = sorted(s for s in baseline.sites if s not in SITES)
    if unknown:
        print(f"  [FAIL] baseline references unknown site(s): {', '.join(unknown)}")
        return 1
    missing = sorted(s for s in SITES if s not in baseline.sites)
    if missing:
        print(f"  [WARN] baseline has no entry for: {', '.join(missing)}")

    print(f"  [OK] {len(baseline.sites)} site(s) — recorded {baseline.recorded} @ {baseline.recorded_commit}")
    for site_id, entry in baseline.sites.items():
        gates = ", ".join(entry.known_failing_gates) or "(none)"
        fragile = ", ".join(entry.expected_failing_tests) or "(none)"
        print(
            f"    - {site_id}: known-red=[{gates}], unresolved ceiling={entry.max_unresolved_placeholders}, "
            f"expected-failing tests=[{fragile}]"
        )
    return 0


def _parse_failed_tests(stdout: str) -> list[str]:
    """Extract failed test short names from pytest output.

    Matches the short-summary ``FAILED <path>::<name>`` lines; the name is
    truncated at any ``[...]`` parametrisation.
    """
    names: list[str] = []
    for match in re.finditer(r"^FAILED\s+\S+::(\w+)", stdout, re.M):
        name = match.group(1)
        if name not in names:
            names.append(name)
    return names


def _unresolved_descriptions(skip_lines: list[str]) -> list[str]:
    """Extract the quoted placeholder descriptions from emitted pytest.skip lines."""
    seen: set[str] = set()
    descriptions: list[str] = []
    for line in skip_lines:
        for desc in re.findall(r"'([^']+)'", line):
            if desc not in seen:
                seen.add(desc)
                descriptions.append(desc)
    return descriptions


def _recorded_commit() -> str:
    """Return the short HEAD sha, or ``"unknown"`` when not in a git checkout."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _write_baseline(path: Path, results: list[SiteVerification]) -> None:
    """Write the current run as the expected-red baseline JSON."""
    sites: dict[str, Any] = {}
    for r in results:
        # A re-recorded baseline keeps headroom: the emitted-skip count is
        # LLM-variance driven, so the ceiling is 2x the observed count (floor 2).
        unresolved_count = len(r.unresolved_placeholders)
        sites[r.site_id] = {
            "known_failing_gates": [g.key for g in r.gates if not g.passed],
            "max_unresolved_placeholders": max(2, unresolved_count * 2),
            "known_unresolved_placeholders": _unresolved_descriptions(r.unresolved_placeholders),
            "expected_failing_tests": list(r.failed_tests),
            "expected_min_tests": SITES[r.site_id]["expected_min_tests"],
        }
    payload: dict[str, Any] = {
        "version": 1,
        "recorded": datetime.now().strftime("%Y-%m-%d"),
        "recorded_commit": _recorded_commit(),
        "note": (
            "Expected-red baseline for scripts/verify_production.py. Only NEW gate failures, NEW failing "
            "tests, or an unresolved count above the ceiling fail the gate. Re-record with "
            "--save-baseline after the unresolved-ASSERT class (AI-058 / AI-064 / B-054 / B-055) is closed."
        ),
        "sites": sites,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n  [SAVED] expected-red baseline written to {path}")


def _run_pairs(r: SiteVerification) -> list[tuple[str, bool]]:
    return [(g.name, g.passed) for g in r.gates]


def _print_baseline_comparison(comparison: BaselineComparison) -> None:
    print(f"\n{'=' * 60}")
    print("EXPECTED-RED BASELINE COMPARISON")
    print(f"{'=' * 60}")
    for site in comparison.sites:
        print(f"\n  [{site.site_id}]")
        if site.tolerated_failures:
            print(f"    [known-red] tolerated: {', '.join(site.tolerated_failures)}")
        print(f"    [unresolved] {site.unresolved_count} / budget {site.unresolved_budget}")
        if site.tolerated_failed_tests:
            print(f"    [known-red] tolerated failing test(s): {', '.join(site.tolerated_failed_tests)}")
        for name in site.fixed_gates:
            print(f"    [IMPROVED ] known-red gate now passes: {name}")
        for name in site.new_failures:
            print(f"    [REGRESSED] NEW failure: {name}")
        for name in site.new_failed_tests:
            print(f"    [REGRESSED] NEW failing test: {name}")
    if comparison.new_failures or comparison.new_failed_tests:
        print("\n  NEW failures (not in baseline):")
        for name in comparison.new_failures:
            print(f"    - {name}")
        for name in comparison.new_failed_tests:
            print(f"    - test {name}")
    if comparison.fixed_gates:
        print("\n  IMPROVEMENTS (re-record the baseline to lock them in):")
        for name in comparison.fixed_gates:
            print(f"    - {name}")


async def main() -> int:
    args = parse_args()
    load_dotenv()

    if args.check_baseline:
        return _check_baseline(Path(args.check_baseline))

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

    # Record the run as the expected-red baseline, if asked, then stop — the
    # baseline file (not the run dirs) is the artifact of a save.
    if args.save_baseline:
        _write_baseline(Path(args.save_baseline), results)
        if not args.keep:
            import shutil as _shutil

            for r in results:
                if r.output_dir and r.output_dir.exists():
                    _shutil.rmtree(r.output_dir, ignore_errors=True)
        print(f"\n{'=' * 60}")
        print("VERDICT: BASELINE SAVED — expected-red state recorded.")
        print(f"{'=' * 60}")
        return 0

    # Compare against the expected-red baseline, if asked.
    comparison: BaselineComparison | None = None
    if args.baseline:
        baseline_path = Path(args.baseline)
        try:
            baseline = load_baseline(baseline_path)
        except (OSError, ValueError) as exc:
            print(f"\n[ERROR] Could not load baseline: {exc}")
            return 1
        runs = {r.site_id: (_run_pairs(r), r.unresolved_placeholders, r.failed_tests) for r in results}
        comparison = compare_run(baseline, runs)
        _print_baseline_comparison(comparison)

    regressed = comparison.regressed if comparison is not None else total_failed > 0

    # Cleanup — expected-red runs are the norm, so delete them; only keep a
    # directory when the run regressed (or the caller passed --keep).
    if not args.keep:
        import shutil as _shutil

        for r in results:
            if r.output_dir and r.output_dir.exists():
                if not regressed:
                    _shutil.rmtree(r.output_dir, ignore_errors=True)
                else:
                    print(f"  [KEPT] {r.output_dir} (regressed — keep for debugging)")

    if regressed:
        print(f"\n{'=' * 60}")
        if comparison is not None:
            print("VERDICT: FAIL — NEW failure(s) vs the expected-red baseline.")
        else:
            print("VERDICT: FAIL — Do NOT ship. Fix the failing gates above.")
        print(f"{'=' * 60}")
        return 1
    if comparison is not None:
        tolerated_gates = len(comparison.tolerated_failures)
        tolerated_tests = sum(len(s.tolerated_failed_tests) for s in comparison.sites)
        print(f"\n{'=' * 60}")
        print(
            f"VERDICT: PASS (baseline) — {tolerated_gates} known-red gate failure(s) "
            f"and {tolerated_tests} known-fragile failing test(s) tolerated, 0 new."
        )
        print(f"{'=' * 60}")
        return 0
    print(f"\n{'=' * 60}")
    print("VERDICT: PASS — Product is working as intended.")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = __import__("io").TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    sys.exit(asyncio.run(main()))
