#!/usr/bin/env python3
"""UAT script for automationexercise.com — end-to-end pipeline validation.

Runs the full skeleton-first pipeline against automationexercise.com with a
realistic e-commerce user story. This exercises:
- Skeleton generation with placeholder syntax
- DOM scraping of a real multi-product page
- Placeholder resolution with text validation
- Navigation vs action verb disambiguation

Usage:
    python scripts/uat/uat_automationexercise.py --provider lm-studio
    python scripts/uat/uat_automationexercise.py --provider lm-studio --site saucedemo
    python scripts/uat/uat_automationexercise.py --provider lm-studio --headed
    python scripts/uat/uat_automationexercise.py --provider ollama --model qwen3.5:35b

NOTE: When running through Cline, use LM Studio with the same model Cline is
already using (e.g. qwen3.6-27b) to avoid GPU VRAM contention from loading
two models simultaneously. Use --headed to see the browser automation in real-time.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm_client import LLMClient  # noqa: E402
from src.orchestrator import TestOrchestrator  # noqa: E402
from src.test_generator import TestGenerator  # noqa: E402

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


DEFAULT_SITE = "automationexercise"
SITE_CONFIGS: dict[str, dict[str, Any]] = {
    "automationexercise": {
        "name": "automationexercise.com",
        "user_story": (
            "As a customer, I want to browse products on the website and add them to my cart "
            "so that I can purchase them later."
        ),
        "conditions": (
            "1. Navigate to the automationexercise.com home page\n"
            "2. Click the 'Products' link in the header navigation to go to the products page\n"
            "3. On the products page, click the 'Add to cart' button next to a product (e.g. Blue Top)\n"
            "4. Verify a confirmation message appears indicating the product was added to cart\n"
            "5. Click the 'Cart' link in the header navigation to go to the cart page\n"
            "6. Verify the cart page displays the product that was added with its name and price\n"
        ),
        "target_urls": ["https://automationexercise.com"],
    },
    "saucedemo": {
        "name": "saucedemo.com",
        "user_story": (
            "As a user, I want to log in to the shopping site, add items to my cart, "
            "verify the items in the cart, proceed to checkout, and complete the "
            "checkout process."
        ),
        "conditions": (
            "1. Log in with username standard_user and password secret_sauce\n"
            "2. Add at least one item (e.g. Sauce Labs Backpack) to the cart\n"
            "3. Navigate to the shopping cart page\n"
            "4. Verify the added item appears correctly in the cart\n"
            "5. Navigate to the checkout page\n"
            "6. Complete the checkout process and verify success (Thank You page)"
        ),
        "target_urls": ["https://www.saucedemo.com"],
    },
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="UAT pipeline validation for supported sites")
    parser.add_argument(
        "--site",
        choices=list(SITE_CONFIGS.keys()),
        default=DEFAULT_SITE,
        help=f"Site to validate (default: {DEFAULT_SITE})",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "lm-studio", "openai", "openai-local"],
        default=None,
        help="LLM provider (default: from .env or ollama)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: from provider default)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Provider base URL (default: from .env)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (show browser window)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the generated tests against the real site",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the generated tests to generated_tests/ directory",
    )
    parser.add_argument(
        "--verify-enrichment",
        action="store_true",
        help="Verify B-0XX scrape enrichment: check source modules have visibility + a11y code paths",
    )
    return parser.parse_args(argv)


def configure_windows_console_encoding() -> None:
    """Use UTF-8 console streams for emoji output when running as a script."""
    if sys.platform != "win32":
        return
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def _verify_b0xx_enrichment() -> bool:
    """Verify B-0XX enrichment code paths exist in source modules.

    Returns True if all checks pass, False otherwise.
    """
    print("\n[B-0XX Enrichment Verification]")
    print("-" * 60)

    journey_src = Path("src/journey_scraper.py").read_text()
    stateful_src = Path("src/stateful_scraper.py").read_text()

    enrichment_checks: dict[str, bool] = {
        # JourneyScraper checks (Path A + B + C from spec)
        "journey_scraper imports AccessibilityEnricher": "AccessibilityEnricher" in journey_src
        and "from src.accessibility_enricher import" in journey_src,
        "journey_scraper has _capture_element_visibility_sync helper": "_capture_element_visibility_sync"
        in journey_src,
        "journey_scraper has _capture_a11y_snapshot_sync helper": "_capture_a11y_snapshot_sync" in journey_src,
        "journey_scraper._scrape_current_page accepts context param": "context: Any | None = None" in journey_src
        or "context=None" in journey_src,
        # StatefulPageScraper checks (Phase 1 from spec)
        "stateful_scraper imports AccessibilityEnricher": "AccessibilityEnricher" in stateful_src
        and "from src.accessibility_enricher import" in stateful_src,
        "stateful_scraper has _capture_a11y_snapshot method": "_capture_a11y_snapshot" in stateful_src,
        "stateful_scraper calls AccessibilityEnricher.enrich()": "AccessibilityEnricher.enrich(" in stateful_src,
        # Module-level helpers for Path C (execute_journey_sync)
        "module-level enrichment helpers defined": journey_src.count("_capture_element_visibility_sync") >= 2
        and journey_src.count("_capture_a11y_snapshot_sync") >= 2,
    }

    all_pass = True
    for check_name, passed in enrichment_checks.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {check_name}")
        if not passed:
            all_pass = False

    print("-" * 60)
    return all_pass


def find_unresolved_placeholder_artifacts(final_code: str) -> tuple[list[str], bool]:
    """Return unresolved placeholder tokens and whether unresolved skip statements exist."""
    placeholders_found = re.findall(r"\{\{(?:CLICK|FILL|GOTO|URL|ASSERT):", final_code)
    skips_found = (
        'pytest.skip("Unresolved placeholder' in final_code
        or "pytest.skip('Unresolved placeholder" in final_code
        or 'pytest.skip("Skipping: unresolved placeholders' in final_code
        or "pytest.skip('Skipping: unresolved placeholders" in final_code
    )
    return placeholders_found, skips_found


async def run_uat() -> None:
    args = parse_args()
    load_dotenv()

    site_config = SITE_CONFIGS[args.site]

    # Enable headed mode if requested
    if args.headed:
        os.environ["PLAYWRIGHT_HEADLESS"] = "0"
        print("[Headed Mode] Browser window will be visible")
        print()

    # Configure the LLM provider — use session-level settings if requested.
    # Otherwise, LLMClient will auto-detect the active local provider.
    if args.provider:
        LLMClient.set_session_provider(
            provider=args.provider,
            base_url=args.base_url,
            model=args.model,
        )
        provider_info = f"{args.provider}" + (f" / {args.model}" if args.model else " (auto-detect model)")
    else:
        provider_info = "auto-detect"

    print("=" * 80)
    print(f"UAT: {site_config['name']} Pipeline Validation")
    print("=" * 80)
    print()
    print(f"UAT Site: {args.site}")
    print(f"LLM Provider: {provider_info}")
    print()

    # B-0XX enrichment verification (static check, no pipeline run needed)
    if args.verify_enrichment:
        enrich_pass = _verify_b0xx_enrichment()
        if enrich_pass:
            print("\n✅ B-0XX Enrichment VERIFIED: All code paths present.")
        else:
            print("\n❌ B-0XX Enrichment FAILED: Some code paths missing.")
        return

    print(f"User Story: {site_config['user_story']}")
    print()
    print(f"Conditions:\n{site_config['conditions']}")
    print()
    print(f"Target URLs: {site_config['target_urls']}")
    print()
    print("-" * 80)

    # Enable debug logging for the pipeline
    os.environ["PIPELINE_DEBUG"] = "1"

    try:
        # Create client without explicit provider — it will pick up the session
        # settings from set_session_provider() above, or fall back to .env.
        client = LLMClient()
        print(f"Using: provider={client.provider_name}, model={client.model}")
        print()
        generator = TestGenerator(client=client)
        orchestrator = TestOrchestrator(generator)

        print(f"\n[Phase 1] Generating test skeletons for {args.site}...")
        start_time = time.time()
        final_code = await orchestrator.run_pipeline(
            user_story=site_config["user_story"],
            conditions=site_config["conditions"],
            target_urls=site_config["target_urls"],
        )
        gen_duration = time.time() - start_time

        print(f"\n[Phase 1] Complete in {gen_duration:.1f}s.")
        print()

        print("-" * 80)
        print("GENERATED CODE")
        print("-" * 80)
        print(final_code)
        print("-" * 80)
        print()

        # Validate output
        if not final_code or len(final_code) < 100:
            print("❌ UAT FAILED: Generated code is too short or empty.")
            return

        all_pass = True

        # Check for placeholder artifacts that should have been resolved.
        placeholders_found, skips_found = find_unresolved_placeholder_artifacts(final_code)

        if placeholders_found or skips_found:
            print("⚠️  UAT WARNING: Unresolved placeholders or placeholder skips found in generated code.")
            if placeholders_found:
                print(f"   Found {len(placeholders_found)} placeholder tokens.")
            if skips_found:
                print("   Placeholder unresolved skip statements were inserted.")
            all_pass = False
        else:
            print("✅ No unresolved placeholders found.")

        # Dynamic validation based on criteria count
        num_criteria = len(re.findall(r"^\d+\.", site_config["conditions"], re.M))
        test_names = re.findall(r"^def\s+(test_\d+)", final_code, re.M)
        print(f"Expected test count: {num_criteria}")
        print(f"Generated test count: {len(test_names)}")

        checks = {
            "evidence_tracker.navigate": "evidence_tracker.navigate" in final_code,
            "evidence_tracker.click": "evidence_tracker.click" in final_code,
            "evidence_tracker.assert_visible": "evidence_tracker.assert_visible" in final_code,
            "pytest.mark.evidence": "@pytest.mark.evidence" in final_code,
        }

        # Site-specific checks
        if args.site == "automationexercise":
            checks["dismiss_consent_overlays"] = "dismiss_consent_overlays" in final_code

        # Add individual test checks
        for i in range(1, num_criteria + 1):
            test_id = f"test_{i:02d}"
            checks[test_id] = test_id in final_code

        print("\n[Validation]")
        for check_name, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}: {'found' if passed else 'MISSING'}")
            if not passed:
                all_pass = False

        # --- Save / Run ---
        if args.save or args.run:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path("generated_tests") / f"uat_{args.site}_{timestamp}"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Write conftest
            (output_dir / "conftest.py").write_text(CONFTEST_TEMPLATE, encoding="utf-8")

            # Write test file
            test_file = output_dir / f"test_{args.site}.py"
            test_file.write_text(final_code, encoding="utf-8")
            print(f"\n[Save] Saved generated tests to: {output_dir}")

            if args.run:
                print(f"\n[Phase 2] Running generated tests against {site_config['name']}...")
                run_start = time.time()
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        str(output_dir),
                        "-v",
                        "--tb=short",
                        "--no-header",
                    ],
                    capture_output=True,
                    text=True,
                )
                run_duration = time.time() - run_start
                print(result.stdout)
                if result.stderr:
                    print(result.stderr)

                if result.returncode == 0:
                    print(f"✅ Tests PASSED in {run_duration:.1f}s")
                else:
                    print(f"❌ Tests FAILED in {run_duration:.1f}s (exit code: {result.returncode})")
                    all_pass = False

        print()
        if all_pass:
            print("✅ UAT PASSED: All validation checks passed.")
        else:
            print("❌ UAT FAILED: Some validation checks did not pass.")

    except Exception as e:
        print(f"❌ UAT FAILED with exception: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    configure_windows_console_encoding()
    asyncio.run(run_uat())
