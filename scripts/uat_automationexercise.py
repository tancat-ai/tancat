#!/usr/bin/env python3
"""UAT script for automationexercise.com — end-to-end pipeline validation.

Runs the full skeleton-first pipeline against automationexercise.com with a
realistic e-commerce user story. This exercises:
- Skeleton generation with placeholder syntax
- DOM scraping of a real multi-product page
- Placeholder resolution with text validation
- Navigation vs action verb disambiguation

Usage:
    python scripts/uat_automationexercise.py
    python scripts/uat_automationexercise.py --provider ollama --model qwen3.5:9b
    python scripts/uat_automationexercise.py --provider lm-studio --model qwen3.6-27b

NOTE: When running through Cline, use LM Studio with the same model Cline is
already using (e.g. qwen3.6-27b) to avoid GPU VRAM contention from loading
two models simultaneously.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


USER_STORY = (
    "As a customer, I want to browse products on the website and add them to my cart "
    "so that I can purchase them later."
)

CONDITIONS = (
    "1. Navigate to the automationexercise.com home page\n"
    "2. Click the 'Products' link in the header navigation to go to the products page\n"
    "3. On the products page, click the 'Add to cart' button next to a product (e.g. Blue Top)\n"
    "4. Verify a confirmation message appears indicating the product was added to cart\n"
    "5. Click the 'Cart' link in the header navigation to go to the cart page\n"
    "6. Verify the cart page displays the product that was added with its name and price\n"
)

TARGET_URLS = ["https://automationexercise.com"]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="UAT: automationexercise.com pipeline validation")
    parser.add_argument(
        "--provider",
        choices=["ollama", "lm-studio", "openai"],
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
    return parser.parse_args()


async def run_uat() -> None:
    args = parse_args()
    load_dotenv()

    # Configure the LLM provider — use session-level settings so all pipeline
    # components (TestGenerator, Orchestrator, etc.) share the same provider.
    # This avoids loading a second model when running through Cline.
    if args.provider:
        LLMClient.set_session_provider(
            provider=args.provider,
            base_url=args.base_url,
            model=args.model,
        )
        provider_info = f"{args.provider}" + (f" / {args.model}" if args.model else "")
    else:
        provider_info = "from .env"

    print("=" * 80)
    print("UAT: automationexercise.com Pipeline Validation")
    print("=" * 80)
    print()
    print(f"LLM Provider: {provider_info}")
    print()
    print(f"User Story: {USER_STORY}")
    print()
    print(f"Conditions:\n{CONDITIONS}")
    print()
    print(f"Target URLs: {TARGET_URLS}")
    print()
    print("-" * 80)

    try:
        # Create client without explicit provider — it will pick up the session
        # settings from set_session_provider() above, or fall back to .env.
        client = LLMClient()
        print(f"Using: provider={client.provider_name}, model={client.model}")
        print()
        generator = TestGenerator(client=client)
        orchestrator = TestOrchestrator(generator)

        print("\n[Phase 1] Generating test skeletons with LLM...")
        final_code = await orchestrator.run_pipeline(
            user_story=USER_STORY,
            conditions=CONDITIONS,
            target_urls=TARGET_URLS,
        )

        print("\n[Phase 1] Complete.")
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

        # Check for placeholder artifacts that should have been resolved
        if "{{{" in final_code:
            print("⚠️  UAT WARNING: Unresolved placeholders found in generated code.")
            print("   The placeholder resolution pipeline may have failed.")
        else:
            print("✅ No unresolved placeholders found.")

        # Check for key patterns — evidence_tracker is the expected pattern,
        # not raw page.goto/.click() since the pipeline wraps all interactions.
        checks = {
            "test_01": "test_01" in final_code,
            "test_02": "test_02" in final_code,
            "test_03": "test_03" in final_code,
            "test_04": "test_04" in final_code,
            "test_05": "test_05" in final_code,
            "test_06": "test_06" in final_code,
            "evidence_tracker.navigate": "evidence_tracker.navigate" in final_code,
            "evidence_tracker.click": "evidence_tracker.click" in final_code,
            "evidence_tracker.assert_visible": "evidence_tracker.assert_visible" in final_code,
            "pytest.mark.evidence": "@pytest.mark.evidence" in final_code,
            "dismiss_consent_overlays": "dismiss_consent_overlays" in final_code,
        }

        print("\n[Validation]")
        all_pass = True
        for check_name, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}: {'found' if passed else 'MISSING'}")
            if not passed:
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
    asyncio.run(run_uat())