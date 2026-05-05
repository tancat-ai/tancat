#!/usr/bin/env python3
"""Debug pipeline — interactive placeholder resolution inspector.

Usage:
    python -m pytest scripts/debug_pipeline.py -v -k "test_debug" --no-cov

This script runs the placeholder resolution pipeline step-by-step and prints
diagnostics at each stage. It allows inspection of:
- Skeleton generation output
- Placeholder extraction
- DOM scraping results
- Candidate ranking scores
- Text validation results
- Final resolved locators

Run with DEBUG_PIPELINE=1 to enable verbose logging:
    DEBUG_PIPELINE=1 python -m pytest scripts/debug_pipeline.py -v -s

Or run directly:
    python scripts/debug_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG_PIPELINE") else logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_resolver import PlaceholderResolver
from src.scraper import PageScraper


# Sample test data — mirrors the real mock insurance site structure
SAMPLE_SKELETON = '''
def test_01_browse_products(page):
    page.goto("{{GOTO:home page}}")
    page.locator("{{{{CLICK:product category link}}}}").click()

def test_02_add_to_cart(page):
    page.locator("{{{{CLICK:Add to cart button next to a product}}}}").click()
    page.locator("{{{{ASSERT:cart content with items}}}}").is_visible()

def test_03_view_cart(page):
    page.locator("{{{{CLICK:Cart link or cart icon in the page header}}}}").click()
    page.locator("{{{{ASSERT:cart page with selected items}}}}").is_visible()
'''

SAMPLE_PLACEHOLDERS = [
    ("GOTO", "home page"),
    ("CLICK", "product category link"),
    ("CLICK", "Add to cart button next to a product"),
    ("ASSERT", "cart content with items"),
    ("CLICK", "Cart link or cart icon in the page header"),
    ("ASSERT", "cart page with selected items"),
]


def inspect_text_validation() -> None:
    """Inspect text_matches_description for real-world descriptions."""
    resolver = PlaceholderResolver()

    test_cases = [
        # (element_text, description, expected_match)
        ("Add to cart", "Add to cart button next to a product", True),
        ("Cart", "Cart link or cart icon in the page header", True),
        ("Continue Shopping", "Continue Shopping button", True),
        ("Add to cart", "Cart link or cart icon in the page header", False),
        ("Subscribe", "Continue Shopping button", False),
        ("View cart", "Go to cart", True),
        ("Checkout", "Proceed to checkout", True),
        ("Home", "Navigate to home page", True),
        ("", "Continue Shopping button", False),
        ("Login", "Sign in button", True),
    ]

    print("=" * 80)
    print("TEXT VALIDATION INSPECTION")
    print("=" * 80)

    all_pass = True
    for element_text, description, expected in test_cases:
        result = resolver.text_matches_description(element_text, description)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        if result != expected:
            all_pass = False
        print(
            f"  {status} | element='{element_text}' desc='{description}' -> {result} (expected {expected})"
        )

    print()
    if all_pass:
        print("All text validation checks passed!")
    else:
        print("Some text validation checks FAILED — review needed.")
    print()


async def inspect_placeholder_resolution(seed_url: str) -> None:
    """Run placeholder resolution against a real URL and print diagnostics."""
    print("=" * 80)
    print(f"PLACEHOLDER RESOLUTION INSPECTION — seed URL: {seed_url}")
    print("=" * 80)
    print()

    scraper = PageScraper()
    orchestrator = PlaceholderOrchestrator(seed_url)
    resolver = PlaceholderResolver()

    # Step 1: Scrape the seed URL
    print("[Step 1] Scraping seed URL...")
    elements, error, final_url = await scraper.scrape_url(seed_url)
    if error:
        print(f"  ⚠️  Scraping error: {error}")
    else:
        print(f"  Scraped {len(elements)} elements from {final_url or seed_url}")

    # Show top elements
    print("  Top elements:")
    for elem in elements[:10]:
        selector = str(elem.get("selector", ""))[:60]
        text = str(elem.get("text", ""))[:40]
        role = str(elem.get("role", ""))[:20]
        print(f"    [{role}] '{text}' -> {selector}")
    print()

    # Step 2: Resolve each placeholder
    print("[Step 2] Resolving placeholders...")
    scraped_data = {final_url or seed_url: elements}

    for action, description in SAMPLE_PLACEHOLDERS:
        print(f"\n  Placeholder: ({action}) '{description}'")

        # Rank candidates
        ranked = resolver.rank_candidates(action, description, elements)
        print(f"    Ranked {len(ranked)} candidates")

        if ranked:
            top_score = ranked[0][0]
            print(f"    Top score: {top_score}")
            for score, elem in ranked[:3]:
                selector = str(elem.get("selector", ""))[:50]
                text = str(elem.get("text", ""))[:40]
                elem_text = str(elem.get("text", "")).strip()
                text_match = resolver.text_matches_description(elem_text, description)
                print(f"      score={score} text='{text}' selector='{selector}' text_match={text_match}")

        # Try full resolution
        best = resolver.find_best_element(action, description, elements)
        if best:
            selector = resolver._build_robust_locator(best)
            print(f"    ✅ Resolved to: {selector}")
        else:
            print(f"    ❌ No match found — will generate pytest.skip()")

    print()


async def inspect_orchestrator_resolution(seed_url: str) -> None:
    """Run the full orchestrator resolution pipeline."""
    print("=" * 80)
    print(f"ORCHESTRATOR RESOLUTION INSPECTION — seed URL: {seed_url}")
    print("=" * 80)
    print()

    orchestrator = PlaceholderOrchestrator(seed_url)

    scraped_data: dict[str, list[dict[str, str]]] = {}
    scraped_errors: dict[str, str] = {}

    for action, description in SAMPLE_PLACEHOLDERS:
        print(f"  Resolving: ({action}) '{description}'")
        resolved_value, next_url = await orchestrator._resolve_placeholder_for_page(
            action=action,
            description=description,
            current_url=seed_url,
            scraped_data=scraped_data,
            scraped_errors=scraped_errors,
        )

        if "pytest.skip" in resolved_value:
            print(f"    ⚠️  SKIP: {resolved_value}")
        else:
            print(f"    ✅ Resolved: {resolved_value}")
            if next_url:
                print(f"       Next URL: {next_url}")

    print()


def inspect_skeleton_placeholders() -> None:
    """Inspect placeholder extraction from skeleton code."""
    print("=" * 80)
    print("SKELETON PLACEHOLDER EXTRACTION")
    print("=" * 80)
    print()

    from src.skeleton_parser import SkeletonParser

    parser = SkeletonParser()
    uses = parser.parse_placeholder_uses(SAMPLE_SKELETON)

    print(f"  Found {len(uses)} placeholder uses:")
    for use in uses:
        token = "{{{{" + f"({use.action}:{use.description})" + "}}}}"
        print(f"    Line {use.line_number}: {token}")

    print()


def main() -> None:
    """Run all inspections."""
    print("\n" + "=" * 80)
    print("DEBUG PIPELINE — Placeholder Resolution Inspector")
    print("=" * 80 + "\n")

    # Inspect text validation
    inspect_text_validation()

    # Inspect skeleton extraction
    inspect_skeleton_placeholders()

    # Run async inspections
    seed_url = os.environ.get("SEED_URL", "https://automationexercise.com")
    asyncio.run(inspect_placeholder_resolution(seed_url))
    asyncio.run(inspect_orchestrator_resolution(seed_url))

    print("=" * 80)
    print("DEBUG PIPELINE COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()