#!/usr/bin/env python3
"""Unified UAT runner for AI-Playwright-Test-Generator.

End-to-end pipeline validation against real websites. Produces human-readable
output and machine-readable JSON for CI/regression comparison.

POM mode is the default — use --flat to run standard mode.

Usage:
    # Single site (POM mode default)
    python scripts/uat.py saucedemo
    python scripts/uat.py automationexercise

    # Both sites
    python scripts/uat.py --all-sites

    # Flat mode (non-POM)
    python scripts/uat.py saucedemo --flat

    # With test execution
    python scripts/uat.py saucedemo --run

    # Save baseline for regression comparison
    python scripts/uat.py --all-sites --save baseline.json

    # Compare against baseline
    python scripts/uat.py --all-sites --compare baseline.json

    # LLM provider override
    python scripts/uat.py saucedemo --provider lm-studio --model qwen3.6-27b

    # Headed mode (show browser)
    python scripts/uat.py saucedemo --headed
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import subprocess
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
# Site configurations
# ---------------------------------------------------------------------------


@dataclass
class SiteConfig:
    """Configuration for a UAT target site."""

    name: str
    url: str
    user_story: str
    conditions: str
    expected_min_tests: int = 1
    expected_min_criteria: int = 1


SITES: dict[str, SiteConfig] = {
    "automationexercise": SiteConfig(
        name="automationexercise.com",
        url="https://automationexercise.com",
        user_story=(
            "As a customer, I want to browse products on the website and add them "
            "to my cart so that I can purchase them later."
        ),
        conditions=(
            "1. Navigate to the automationexercise.com home page\n"
            "2. Click the 'Products' link in the header navigation\n"
            "3. On the products page, click 'Add to cart' next to a product\n"
            "4. Verify a confirmation message appears\n"
            "5. Click the 'Cart' link in the header\n"
            "6. Verify the cart page displays the added product\n"
        ),
        expected_min_criteria=6,
    ),
    "saucedemo": SiteConfig(
        name="saucedemo.com",
        url="https://www.saucedemo.com",
        user_story=(
            "As a user, I want to log in to the shopping site, add items to my cart, "
            "proceed to checkout, and complete the checkout process."
        ),
        conditions=(
            "1. Log in with username standard_user and password secret_sauce\n"
            "2. Add at least one item (e.g. Sauce Labs Backpack) to the cart\n"
            "3. Navigate to the shopping cart page\n"
            "4. Verify the added item appears correctly in the cart\n"
            "5. Navigate to the checkout page\n"
            "6. Complete the checkout process and verify success\n"
        ),
        expected_min_criteria=6,
    ),
}


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SiteResult:
    site_id: str
    site_name: str
    pom_mode: bool
    checks: list[CheckResult] = field(default_factory=list)
    generated_code: str = ""
    generation_duration: float = 0.0
    run_duration: float = 0.0
    run_pass: bool | None = None
    error: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def total(self) -> int:
        return len(self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "site_name": self.site_name,
            "pom_mode": self.pom_mode,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks],
            "generation_duration_s": round(self.generation_duration, 2),
            "run_duration_s": round(self.run_duration, 2),
            "run_pass": self.run_pass,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Conftest template
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
    if tracker.steps:
        tracker.write(status="passed")
'''


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


async def run_site_uat(
    site_id: str,
    config: SiteConfig,
    pom_mode: bool,
    run_tests: bool = False,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> SiteResult:
    """Run the full pipeline UAT for one site."""
    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.test_generator import TestGenerator

    result = SiteResult(site_id=site_id, site_name=config.name, pom_mode=pom_mode)

    mode_label = "POM" if pom_mode else "Flat"
    print(f"\n{'=' * 70}")
    print(f"UAT: {config.name} ({mode_label} mode)")
    print(f"{'=' * 70}")
    print()

    if provider:
        LLMClient.set_session_provider(provider, base_url=base_url, model=model)

    try:
        client = LLMClient()
        result.checks.append(
            CheckResult(
                f"LLM client ({client.provider_name} / {client.model})",
                True,
            )
        )
    except Exception as e:
        result.error = f"LLMClient failed: {e}"
        result.checks.append(CheckResult("LLM client", False, str(e)))
        return result

    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=pom_mode)

    # Phase 1: Pipeline
    try:
        start = time.time()
        final_code = await orchestrator.run_pipeline(
            user_story=config.user_story,
            conditions=config.conditions,
            target_urls=[config.url],
        )
        result.generation_duration = time.time() - start
        result.generated_code = final_code

        result.checks.append(
            CheckResult(
                f"Pipeline generation ({result.generation_duration:.1f}s)",
                len(final_code) > 100,
                f"{len(final_code)} chars",
            )
        )
    except Exception as e:
        result.error = f"Pipeline failed: {e}"
        result.checks.append(CheckResult("Pipeline generation", False, str(e)))
        return result

    # Validation checks
    # 1. Code length
    result.checks.append(
        CheckResult(
            "Generated code substantive",
            len(final_code) > 200,
            f"{len(final_code)} chars",
        )
    )

    # 2. No unresolved placeholders
    ph_tokens = re.findall(r"\{\{\{\{(\w+):", final_code)
    result.checks.append(
        CheckResult(
            "No unresolved placeholder tokens",
            len(ph_tokens) == 0,
            f"{len(ph_tokens)} remaining tokens" if ph_tokens else "clean",
        )
    )

    # 3. pytest.skip count
    skip_lines = [line.strip() for line in final_code.splitlines() if "pytest.skip(" in line]
    result.checks.append(
        CheckResult(
            "Minimal pytest.skip usage",
            len(skip_lines) <= 2,  # Allow some skips for edge cases
            f"{len(skip_lines)} skip lines" if skip_lines else "no skips",
        )
    )

    # 4. Evidence tracker
    result.checks.append(
        CheckResult(
            "Evidence tracker calls present",
            "evidence_tracker." in final_code,
            str(final_code.count("evidence_tracker.")) + " calls",
        )
    )

    # 5. pytest.mark.evidence
    result.checks.append(
        CheckResult(
            "@pytest.mark.evidence decorators",
            "@pytest.mark.evidence" in final_code,
            str(final_code.count("@pytest.mark.evidence")) + " decorators",
        )
    )

    # 6. Test count
    criteria_count = len(re.findall(r"^\d+\.", config.conditions, re.M))
    test_funcs = re.findall(r"^def\s+test_\w+", final_code, re.M)
    result.checks.append(
        CheckResult(
            f"Test functions generated ({len(test_funcs)})",
            len(test_funcs) >= criteria_count - 1,  # Allow 1 missing
            f"{len(test_funcs)} tests vs {criteria_count} criteria",
        )
    )

    # 7. POM-specific checks
    if pom_mode:
        # In POM mode the test file imports page objects — classes live in pages/ directory.
        has_pom_usage = "from pages." in final_code or "import pages" in final_code
        result.checks.append(
            CheckResult(
                "POM page objects used in tests",
                has_pom_usage,
                "found" if has_pom_usage else "missing",
            )
        )

    # Pipeline result metadata
    pipeline_result = orchestrator.last_result
    if pipeline_result:
        result.checks.append(
            CheckResult(
                f"Pages scraped ({len(pipeline_result.scraped_pages)})",
                len(pipeline_result.scraped_pages) > 0,
                ", ".join(p[-40:] for p in pipeline_result.scraped_pages.keys()),
            )
        )

        if pom_mode:
            result.checks.append(
                CheckResult(
                    f"POM classes generated ({len(pipeline_result.generated_page_objects)})",
                    len(pipeline_result.generated_page_objects) > 0,
                    ", ".join(p.class_name for p in pipeline_result.generated_page_objects),
                )
            )

        result.checks.append(
            CheckResult(
                f"Unresolved placeholders ({len(pipeline_result.unresolved_placeholders)})",
                len(pipeline_result.unresolved_placeholders) <= 2,
                json.dumps(pipeline_result.unresolved_placeholders[:5]),
            )
        )

    # Phase 2: Run tests (optional)
    if run_tests:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path("generated_tests") / f"uat_{site_id}_{timestamp}"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "conftest.py").write_text(CONFTEST_TEMPLATE, encoding="utf-8")
            (output_dir / f"test_{site_id}.py").write_text(final_code, encoding="utf-8")

            # Write POM pages/ directory so tests can import from pages.*
            if pom_mode and pipeline_result and pipeline_result.generated_page_objects:
                pages_dir = output_dir / "pages"
                pages_dir.mkdir(parents=True, exist_ok=True)
                (pages_dir / "__init__.py").write_text("", encoding="utf-8")
                for page_obj in pipeline_result.generated_page_objects:
                    (pages_dir / f"{page_obj.module_name}.py").write_text(page_obj.module_source, encoding="utf-8")

            print(f"\n  [Run] Executing tests against {config.name}...")
            run_start = time.time()
            proc = subprocess.run(
                [
                    sys.executable, "-m", "pytest", str(output_dir),
                    "-o", "addopts=",
                    "-o", "norecursedirs=.git .venv",
                    "-o", f"pythonpath={output_dir}",
                    "--browser=chromium",
                    "--screenshot=only-on-failure",
                    "-v", "--tb=short", "--no-header",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            result.run_duration = time.time() - run_start
            result.run_pass = proc.returncode == 0

            # Parse pytest output for pass/fail counts
            passed_match = re.search(r"(\d+) passed", proc.stdout)
            failed_match = re.search(r"(\d+) failed", proc.stdout)
            skipped_match = re.search(r"(\d+) skipped", proc.stdout)

            detail_parts = []
            if passed_match:
                detail_parts.append(f"{passed_match.group(1)} passed")
            if failed_match:
                detail_parts.append(f"{failed_match.group(1)} failed")
            if skipped_match:
                detail_parts.append(f"{skipped_match.group(1)} skipped")

            result.checks.append(
                CheckResult(
                    f"Test execution ({result.run_duration:.1f}s)",
                    proc.returncode == 0,
                    ", ".join(detail_parts) if detail_parts else f"exit code {proc.returncode}",
                )
            )

            # Keep output dir for debugging — don't delete
            # import shutil
            # shutil.rmtree(output_dir, ignore_errors=True)

        except subprocess.TimeoutExpired:
            result.checks.append(
                CheckResult(
                    "Test execution",
                    False,
                    "timeout after 120s",
                )
            )
        except Exception as e:
            result.checks.append(
                CheckResult(
                    "Test execution",
                    False,
                    str(e),
                )
            )

    # Summary
    p = result.passed
    f = result.failed
    print(f"\n  Summary: {p} passed, {f} failed ({result.total} checks)")
    if pom_mode:
        print("  Mode: POM")
    else:
        print("  Mode: Flat")

    return result


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare_results(baseline: dict[str, Any], current: dict[str, Any]) -> None:
    """Compare current results against a saved baseline."""
    print(f"\n{'=' * 70}")
    print("REGRESSION COMPARISON")
    print(f"{'=' * 70}")
    print(f"  Baseline: {baseline.get('timestamp', 'unknown')}")
    print(f"  Current:  {current.get('timestamp', 'unknown')}")
    print()

    baseline_sites = {s["site_id"]: s for s in baseline.get("sites", [])}
    current_sites = {s["site_id"]: s for s in current.get("sites", [])}

    all_site_ids = sorted(set(list(baseline_sites.keys()) + list(current_sites.keys())))

    for site_id in all_site_ids:
        b_site = baseline_sites.get(site_id, {})
        c_site = current_sites.get(site_id, {})

        b_checks = {c["name"]: c["passed"] for c in b_site.get("checks", [])}
        c_checks = {c["name"]: c["passed"] for c in c_site.get("checks", [])}

        all_check_names = sorted(set(list(b_checks.keys()) + list(c_checks.keys())))

        print(f"  [{site_id}]")
        for name in all_check_names:
            b_val = b_checks.get(name)
            c_val = c_checks.get(name)

            if b_val is None:
                status = "NEW"
            elif c_val is None:
                status = "REMOVED"
            elif b_val == c_val:
                status = "SAME"
            elif c_val and not b_val:
                status = "IMPROVED"
            else:
                status = "REGRESSED"

            icon = {"NEW": "?", "REMOVED": "-", "SAME": "=", "IMPROVED": "^", "REGRESSED": "v"}.get(status, "?")
            print(f"    [{icon}] {name}: {b_val} -> {c_val} ({status})")

        # Generation time comparison
        b_time = b_site.get("generation_duration_s", 0)
        c_time = c_site.get("generation_duration_s", 0)
        if b_time and c_time:
            diff = c_time - b_time
            pct = diff / b_time * 100 if b_time else 0
            print(f"    [time] {b_time:.1f}s -> {c_time:.1f}s ({'+' if diff > 0 else ''}{pct:+.0f}%)")

        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified UAT runner for AI-Playwright-Test-Generator",
    )

    parser.add_argument(
        "site",
        nargs="?",
        choices=list(SITES.keys()),
        default=None,
        help="Site to validate (omit for --all-sites)",
    )
    parser.add_argument(
        "--all-sites",
        action="store_true",
        help="Run UAT against all configured sites",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Run in Flat mode (default: POM mode)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute generated tests against the real site",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "lm-studio", "openai", "openai-local"],
        default=None,
        help="LLM provider (default: from .env)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Provider base URL override",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode",
    )
    parser.add_argument(
        "--save",
        metavar="FILE",
        default=None,
        help="Save results to JSON file for later comparison",
    )
    parser.add_argument(
        "--compare",
        metavar="FILE",
        default=None,
        help="Load results JSON and compare against current run",
    )

    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    load_dotenv()

    if args.headed:
        os.environ["PLAYWRIGHT_HEADLESS"] = "0"

    pom_mode = not args.flat

    # Determine sites
    if args.all_sites:
        site_ids = list(SITES.keys())
    elif args.site:
        site_ids = [args.site]
    else:
        # Default: run default site
        site_ids = ["automationexercise"]

    print("=" * 70)
    print(f"UAT Runner — {'POM' if pom_mode else 'Flat'} mode")
    print(f"Sites: {', '.join(site_ids)}")
    print(f"Run tests: {'yes' if args.run else 'no'}")
    print("=" * 70)

    results: list[SiteResult] = []
    for site_id in site_ids:
        config = SITES[site_id]
        site_result = await run_site_uat(
            site_id=site_id,
            config=config,
            pom_mode=pom_mode,
            run_tests=args.run,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
        )
    results.append(site_result)

    # Overall summary
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_checks = sum(r.total for r in results)

    print(f"\n{'=' * 70}")
    print(f"OVERALL: {total_passed} passed, {total_failed} failed ({total_checks} total)")
    print(f"{'=' * 70}")

    # Save / Compare
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "pom_mode": pom_mode,
        "sites": [r.to_dict() for r in results],
    }

    if args.compare:
        try:
            baseline = json.loads(Path(args.compare).read_text(encoding="utf-8"))
            compare_results(baseline, output_data)
        except Exception as e:
            print(f"\n[ERROR] Failed to load baseline: {e}")
            return 1

    if args.save:
        Path(args.save).write_text(json.dumps(output_data, indent=2), encoding="utf-8")
        print(f"\nResults saved to: {args.save}")

    return 1 if total_failed else 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    sys.exit(asyncio.run(main()))
