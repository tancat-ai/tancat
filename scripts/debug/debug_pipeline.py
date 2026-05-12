#!/usr/bin/env python3
"""Debug pipeline — full end-to-end placeholder trace.

Runs the skeleton-first pipeline step-by-step and prints diagnostics at each
stage so the exact point of failure is visible rather than inferred.

Usage:
    # Full trace (skeleton → scrape → resolve → final code)
    python scripts/debug_pipeline.py --url https://saucedemo.com --story "As a user I want to login"

    # Inspect text validation logic only
    python scripts/debug_pipeline.py --text-validation

    # Inspect skeleton placeholder extraction
    python scripts/debug_pipeline.py --skeleton-inspection

    # Full pipeline trace with verbose stage output
    PIPELINE_DEBUG=1 python scripts/debug_pipeline.py --url https://saucedemo.com --story "..."

Each stage prints:
  Stage 1 — Skeleton: placeholders found
  Stage 2 — Scrape: elements per page
  Stage 3 — Resolve: candidate ranking + selected locator per placeholder
  Stage 4 — Final code: whether each resolved locator survived into output
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG_PIPELINE") else logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Sample data for standalone inspections ────────────────────────────

SAMPLE_SKELETON = """
def test_01_browse_products(page):
    page.goto("{{GOTO:home page}}")
    page.locator("{{{{CLICK:product category link}}}}").click()

def test_02_add_to_cart(page):
    page.locator("{{{{CLICK:Add to cart button next to a product}}}}").click()
    page.locator("{{{{ASSERT:cart content with items}}}}").is_visible()

def test_03_view_cart(page):
    page.locator("{{{{CLICK:Cart link or cart icon in the page header}}}}").click()
    page.locator("{{{{ASSERT:cart page with selected items}}}}").is_visible()
"""

SAMPLE_PLACEHOLDERS = [
    ("GOTO", "home page"),
    ("CLICK", "product category link"),
    ("CLICK", "Add to cart button next to a product"),
    ("ASSERT", "cart content with items"),
    ("CLICK", "Cart link or cart icon in the page header"),
    ("ASSERT", "cart page with selected items"),
]

# ── Stage 0: Text Validation Inspection ───────────────────────────────


def inspect_text_validation() -> None:
    """Inspect text_matches_description for real-world descriptions."""
    from src.placeholder_resolver import PlaceholderResolver

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
    print("STAGE 0 — TEXT VALIDATION INSPECTION")
    print("=" * 80)

    all_pass = True
    for element_text, description, expected in test_cases:
        result = resolver.text_matches_description(element_text, description)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        if result != expected:
            all_pass = False
        print(f"  {status} | element='{element_text}' desc='{description}' -> {result} (expected {expected})")

    print()
    if all_pass:
        print("All text validation checks passed!")
    else:
        print("Some text validation checks FAILED — review needed.")
    print()


# ── Stage A: Skeleton Placeholder Extraction ──────────────────────────


def inspect_skeleton_placeholders() -> None:
    """Inspect placeholder extraction from skeleton code."""
    from src.skeleton_parser import SkeletonParser

    parser = SkeletonParser()

    print("=" * 80)
    print("STAGE A — SKELETON PLACEHOLDER EXTRACTION")
    print("=" * 80)
    print()

    uses = parser.parse_placeholder_uses(SAMPLE_SKELETON)
    print(f"  Found {len(uses)} placeholder uses:")
    for use in uses:
        token = "{{{{" + f"({use.action}:{use.description})" + "}}}}"
        print(
            f"    Line {use.line_number}: ({use.action}) '{use.description}' -> {token}"
        )

    placeholders = parser.parse_placeholders(SAMPLE_SKELETON)
    print(f"\n  parse_placeholders() returned {len(placeholders)} placeholders:")
    for action, description in placeholders:
        print(f"    ({action}) '{description}'")

    journeys = parser.parse_test_journeys(SAMPLE_SKELETON)
    print(f"\n  parse_test_journeys() returned {len(journeys)} journeys:")
    for j in journeys:
        print(f"    {j.test_name} (lines {j.start_line}-{j.end_line}, steps={len(j.steps)}, placeholders={len(j.placeholders)})")

    print()


# ── Stage B: Placeholder Resolution Inspection (async) ────────────────


async def inspect_placeholder_resolution(seed_url: str) -> None:
    """Run placeholder resolution against a real URL and print diagnostics."""
    from src.placeholder_resolver import PlaceholderResolver
    from src.scraper import PageScraper

    print("=" * 80)
    print(f"STAGE B — PLACEHOLDER RESOLUTION INSPECTION  (seed: {seed_url})")
    print("=" * 80)
    print()

    scraper = PageScraper()
    resolver = PlaceholderResolver()

    # Step 1: Scrape the seed URL
    print("[Scrape] Fetching seed URL...")
    elements, error, final_url = await scraper.scrape_url(seed_url)
    if error:
        print(f"  ⚠️  Scraping error: {error}")
    else:
        display_url = final_url if final_url else seed_url
        print(f"  Scraped {len(elements)} elements from {display_url}")

    # Show top elements
    print("  Top elements:")
    for elem in elements[:15]:
        selector = str(elem.get("selector", ""))[:60]
        text = str(elem.get("text", ""))[:40]
        role = str(elem.get("role", ""))[:20]
        print(f"    [{role}] '{text}' -> {selector}")
    print()

    # Step 2: Resolve each placeholder
    print("[Resolve] Ranking candidates for each placeholder...")
    for action, description in SAMPLE_PLACEHOLDERS:
        print(f"\n  Placeholder: ({action}) '{description}'")

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
            resolved_selector = resolver._build_robust_locator(best)
            print(f"    ✅ Resolved to: {resolved_selector}")
        else:
            print("    ❌ No match found — will generate pytest.skip()")

    print()


# ── Stage C: Full Pipeline Trace ──────────────────────────────────────


def _extract_placeholder_pattern() -> re.Pattern:
    """Regex that matches {{{ACTION:description}}} tokens."""
    return re.compile(r"\{\{\{\{(\w+):([^}]+)\}\}\}")


async def trace_full_pipeline(url: str, user_story: str, conditions: str | None = None) -> None:
    """Run the full pipeline and trace each placeholder through all stages.

    This is the critical diagnostic: it shows whether a locator resolved
    in Stage 3 actually survives into the final code in Stage 4.
    """
    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.skeleton_parser import SkeletonParser
    from src.test_generator import TestGenerator

    print("=" * 80)
    print("STAGE C — FULL PIPELINE TRACE")
    print(f"  URL: {url}")
    print(f"  Story: {user_story}")
    print(f"  Conditions: {conditions or '(auto-detect)'}")
    print("=" * 80)
    print()

    parser = SkeletonParser()
    ph_regex = _extract_placeholder_pattern()

    # ── Stage 1: Generate Skeleton ──────────────────────────────────
    print("─" * 60)
    print("STAGE 1 — SKELETON GENERATION")
    print("─" * 60)

    llm_client = LLMClient()
    test_generator = TestGenerator(client=llm_client)
    orchestrator = TestOrchestrator(test_generator)

    default_conditions = (
        "1. Navigate to the home page\n"
        "2. Login with valid credentials\n"
        "3. Add a product to the cart\n"
        "(Total: 3 criteria)"
    )
    conditions_text = conditions or default_conditions

    try:
        skeleton_code = await test_generator.generate_skeleton(
            user_story,
            conditions_text,
            target_urls=[url],
            expected_count=3,
        )
    except Exception as e:
        print(f"  ❌ Skeleton generation failed: {e}")
        print("\n  NOTE: If the LLM is unavailable, use --text-validation or")
        print("  --skeleton-inspection for offline diagnostics.")
        return

    skeleton_code = parser.normalise_placeholder_actions(skeleton_code)
    placeholders = parser.parse_placeholders(skeleton_code)
    journeys = parser.parse_test_journeys(skeleton_code)

    print(f"  Skeleton generated ({len(skeleton_code)} chars)")
    print(f"  Placeholders found: {len(placeholders)}")
    print(f"  Journeys found: {len(journeys)}")

    # Collect all placeholder tokens from the skeleton
    skeleton_tokens: list[tuple[str, str, str]] = []  # (token, action, description)
    for match in ph_regex.finditer(skeleton_code):
        skeleton_tokens.append((match.group(0), match.group(1), match.group(2)))

    print("\n  Placeholder tokens in skeleton:")
    for token, action, desc in skeleton_tokens:
        print(f"    ({action}) '{desc}'")
        print(f"      token: {token}")
    print()

    # ── Stage 2: Scrape ─────────────────────────────────────────────
    print("─" * 60)
    print("STAGE 2 — DOM SCRAPING")
    print("─" * 60)

    # We need to run the pipeline to get scraped data, so let it run.
    # Then we inspect the results.
    print("  Running full pipeline (this triggers scraping + resolution)...")
    print()

    try:
        final_code = await orchestrator.run_pipeline(
            user_story=user_story,
            conditions=conditions_text,
            target_urls=[url],
        )
    except Exception as e:
        print(f"  ❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return

    result = orchestrator.last_result
    if result is None:
        print("  ❌ PipelineRunResult not captured")
        return

    # ── Stage 2 (post-pipeline): Show scraped data ──────────────────
    print("─" * 60)
    print("STAGE 2 — SCRAPED DATA (post-pipeline)")
    print("─" * 60)

    for page_url, elements in result.scraped_pages.items():
        short_url = page_url[-60:] if len(page_url) > 60 else page_url
        print(f"  Page: {short_url} -> {len(elements)} elements")
        for elem in elements[:5]:
            selector = str(elem.get("selector", ""))[:50]
            text = str(elem.get("text", ""))[:30]
            print(f"    '{text}' -> {selector}")
        if len(elements) > 5:
            print(f"    ... and {len(elements) - 5} more")
    print()

    # ── Stage 3: Resolution Results ─────────────────────────────────
    print("─" * 60)
    print("STAGE 3 — PLACEHOLDER RESOLUTION")
    print("─" * 60)

    unresolved = result.unresolved_placeholders
    print(f"  Unresolved placeholders: {len(unresolved)}")
    for u in unresolved:
        print(f"    ⚠️  {u}")
    print()

    # ── Stage 4: Token Survival Analysis ────────────────────────────
    print("─" * 60)
    print("STAGE 4 — TOKEN SURVIVAL ANALYSIS")
    print("─" * 60)
    print()
    print("  Checking each skeleton placeholder against final code:")
    print()

    survived_count = 0
    dropped_count = 0

    for token, action, desc in skeleton_tokens:
        # Check if the raw token still appears (shouldn't — it should be replaced)
        token_in_skeleton = token in skeleton_code
        token_in_final = token in final_code

        # Check if the resolved locator appears in final code
        # The resolved value wraps the locator, so we check for key parts
        # Since we don't have the resolved value directly here, check if
        # evidence_tracker calls exist for this action type
        if action == "CLICK":
            # Look for evidence_tracker.click with the description as label
            label_pattern = f"label={repr(desc)}"
            click_call = "evidence_tracker.click(" in final_code and desc.lower() in final_code.lower()
            locator_survived = click_call or label_pattern in final_code
        elif action == "FILL":
            fill_call = "evidence_tracker.fill(" in final_code and desc.lower() in final_code.lower()
            locator_survived = fill_call
        elif action == "ASSERT":
            assert_call = "evidence_tracker.assert_visible(" in final_code and desc.lower() in final_code.lower()
            locator_survived = assert_call
        elif action in ("GOTO", "URL"):
            goto_call = "evidence_tracker.navigate(" in final_code
            locator_survived = goto_call
        else:
            locator_survived = None

        status_icon = "✅" if locator_survived else "❌" if not locator_survived else "⚠️"
        survival_str = "YES" if locator_survived else "NO" if not locator_survived else "UNKNOWN"

        print(f"  {status_icon} ({action}) '{desc}'")
        print(f"     token in skeleton: {token_in_skeleton}")
        print(f"     token in final:    {token_in_final} (should be False — replaced)")
        print(f"     locator survived:  {survival_str}")

        if locator_survived:
            survived_count += 1
        else:
            dropped_count += 1

        print()

    # ── Summary ─────────────────────────────────────────────────────
    print("─" * 60)
    print("STAGE 4 — SUMMARY")
    print("─" * 60)
    print()
    print(f"  Total placeholders:     {len(skeleton_tokens)}")
    print(f"  Survived to final:      {survived_count}")
    print(f"  Dropped (FAILED):       {dropped_count}")
    print(f"  Unresolved (pytest.skip): {len(unresolved)}")
    print()

    if dropped_count > 0:
        print("  ⚠️  LOCATORS WERE DROPPED — the pipeline resolved them but they")
        print("  did not appear in the final code. Investigate:")
        print("    1. replace_token_in_line() pattern matching")
        print("    2. normalise_generated_code() transformations")
        print("    3. token format mismatches between skeleton and resolution")
        print()

    # Show final code snippet
    print("─" * 60)
    print("FINAL CODE (first 80 lines)")
    print("─" * 60)
    final_lines = final_code.splitlines()
    for i, line in enumerate(final_lines[:80], 1):
        print(f"  {i:3d} | {line}")
    if len(final_lines) > 80:
        print(f"  ... and {len(final_lines) - 80} more lines")
    print()


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Debug pipeline — placeholder resolution inspector")
    ap.add_argument(
        "--url",
        help="Seed URL to scrape (e.g., https://saucedemo.com)",
    )
    ap.add_argument(
        "--story",
        help="User story for skeleton generation",
    )
    ap.add_argument(
        "--conditions",
        help="Acceptance conditions (one per line, or comma-separated)",
    )
    ap.add_argument(
        "--text-validation",
        action="store_true",
        help="Run text validation inspection only (offline)",
    )
    ap.add_argument(
        "--skeleton-inspection",
        action="store_true",
        help="Run skeleton placeholder extraction only (offline)",
    )

    args = ap.parse_args()

    # Offline inspections
    if args.text_validation:
        inspect_text_validation()
        return

    if args.skeleton_inspection:
        inspect_skeleton_placeholders()
        return

    # Full pipeline trace (requires URL + LLM)
    if args.url:
        story = args.story or "As a user I want to interact with the application"
        conditions = args.conditions
        asyncio.run(trace_full_pipeline(args.url, story, conditions))
        return

    # Default: run all offline inspections, then ask for URL
    print("\n" + "=" * 80)
    print("DEBUG PIPELINE — Placeholder Resolution Inspector")
    print("=" * 80 + "\n")

    inspect_text_validation()
    inspect_skeleton_placeholders()

    # Async inspections need a URL
    seed_url = os.environ.get("SEED_URL", "https://saucedemo.com")
    print(f"No --url provided. Using SEED_URL env var or default: {seed_url}")
    asyncio.run(inspect_placeholder_resolution(seed_url))

    print("=" * 80)
    print("DEBUG PIPELINE COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
