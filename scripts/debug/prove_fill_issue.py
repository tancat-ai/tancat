#!/usr/bin/env python3
"""Proof script: demonstrate that FILL placeholders fail resolution.

Runs the full pipeline against saucedemo.com (which requires login) and
captures:
  1. The skeleton with FILL placeholders
  2. Which placeholders resolve and which become pytest.skip
  3. The final generated code

Usage:
    python scripts/debug/prove_fill_issue.py
    python scripts/debug/prove_fill_issue.py --provider ollama --model qwen3.5:9b
    python scripts/debug/prove_fill_issue.py --provider lm-studio
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=["auto", "ollama", "lm-studio", "openai", "openai-local"],
        default=None,
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    load_dotenv()

    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.skeleton_parser import SkeletonParser
    from src.test_generator import TestGenerator

    if args.provider:
        LLMClient.set_session_provider(args.provider, base_url=args.base_url, model=args.model)

    # --- Config ---
    url = "https://www.saucedemo.com"
    user_story = (
        "As a user, I want to log in to the shopping site, add items to my cart, "
        "and verify the items are in the cart."
    )
    conditions = (
        "1. Log in with username standard_user and password secret_sauce\n"
        "2. Add the Sauce Labs Backpack to the cart\n"
        "3. Click the cart icon to view the cart\n"
        "4. Verify the backpack appears in the cart with correct details\n"
        "(Total: 4 criteria)"
    )

    # --- Setup ---
    client = LLMClient()
    print(f"Provider: {client.provider_name} / {client.model}")
    print(f"URL: {url}")
    print()

    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator)

    # --- Step 1: Generate skeleton ---
    print("=" * 70)
    print("STEP 1: SKELETON GENERATION")
    print("=" * 70)

    skeleton = await generator.generate_skeleton(
        user_story, conditions, target_urls=[url], expected_count=4,
    )
    parser_obj = SkeletonParser()
    skeleton = parser_obj.normalise_placeholder_actions(skeleton)

    print(skeleton)
    print()

    # Extract FILL placeholders
    fill_placeholders = parser_obj.parse_placeholders(skeleton)
    fill_items = [(a, d) for a, d in fill_placeholders if a == "FILL"]
    print(f"Total placeholders: {len(fill_placeholders)}")
    print(f"FILL placeholders: {len(fill_items)}")
    for action, desc in fill_items:
        print(f"  {action}: '{desc}'")
    print()

    # --- Step 2: Run full pipeline ---
    print("=" * 70)
    print("STEP 2: FULL PIPELINE")
    print("=" * 70)

    final_code = await orchestrator.run_pipeline(
        user_story=user_story,
        conditions=conditions,
        target_urls=[url],
    )

    print()

    # --- Step 3: Analyse results ---
    print("=" * 70)
    print("STEP 3: RESULTS")
    print("=" * 70)

    result = orchestrator.last_result
    if result:
        print(f"\nScraped pages: {len(result.scraped_pages)}")
        for page_url, elements in result.scraped_pages.items():
            print(f"  {page_url}: {len(elements)} elements")

        unresolved = result.unresolved_placeholders
        print(f"\nUnresolved placeholders (pytest.skip lines): {len(unresolved)}")
        for u in unresolved:
            print(f"  {u}")

    # Check final code for FILL-related skips
    skips = [line.strip() for line in final_code.splitlines() if "pytest.skip" in line]
    print(f"\npytest.skip lines in final code: {len(skips)}")
    for s in skips:
        print(f"  {s}")

    # Check which FILL placeholders resolved
    print(f"\nFILL placeholder resolution status:")
    for action, desc in fill_items:
        # Check if the description appears in a skip line
        in_skip = any(desc.lower().split()[0] in s.lower() for s in skips)
        # Check if the description appears in an evidence_tracker.fill call
        in_code = f"'{desc}'" in final_code or f'"{desc}"' in final_code

        if in_skip:
            status = "❌ UNRESOLVED (pytest.skip)"
        elif in_code or not in_skip:
            # Check if it appears in a fill call
            fill_calls = re.findall(r"evidence_tracker\.fill\([^)]+\)", final_code)
            desc_words = desc.lower().split()
            matched = any(
                any(w in call.lower() for w in desc_words)
                for call in fill_calls
            )
            if matched:
                status = "✅ RESOLVED"
            else:
                status = "⚠️ UNCLEAR"
        else:
            status = "❌ UNRESOLVED"

        print(f"  {status}  FILL: '{desc}'")

    # --- Step 4: Show final code ---
    print()
    print("=" * 70)
    print("FINAL GENERATED CODE")
    print("=" * 70)
    for i, line in enumerate(final_code.splitlines(), 1):
        print(f"  {i:3d} | {line}")

    # --- Step 5: Verdict ---
    print()
    print("=" * 70)
    print("VERDICT")
    print("=" * 70)

    if fill_items:
        unresolved_count = sum(
            1 for _, desc in fill_items
            if any(desc.lower().split()[0] in s.lower() for s in skips)
        )
        resolved_count = len(fill_items) - unresolved_count

        print(f"\n  FILL placeholders: {len(fill_items)}")
        print(f"  Resolved:          {resolved_count}")
        print(f"  Unresolved:        {unresolved_count}")

        if unresolved_count > 0:
            print(f"\n  ❌ ISSUE CONFIRMED: {unresolved_count}/{len(fill_items)} FILL placeholders failed to resolve")
            print("     These will generate pytest.skip() in the output.")
            return 1
        else:
            print(f"\n  ✅ All FILL placeholders resolved successfully")
            return 0
    else:
        print("\n  ⚠️ No FILL placeholders in skeleton — cannot test this scenario")
        return 2


if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    except Exception:
        pass

    sys.exit(asyncio.run(main()))
