#!/usr/bin/env python3
"""Debug script to verify POM mode test generation.

Run this to generate tests with POM mode enabled and inspect the output.
Uses the automationexercise.com site as a test target.

Usage:
    python scripts/debug/debug_pom_mode.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.orchestrator import TestOrchestrator  # noqa: E402
from src.placeholder_orchestrator import PlaceholderOrchestrator  # noqa: E402
from src.skeleton_parser import SkeletonParser  # noqa: E402
from src.test_generator import TestGenerator  # noqa: E402
from src.user_story_parser import FeatureParser  # noqa: E402

USER_STORY = (
    "As a shopper, I want to browse the Dress category on automationexercise.com, "
    "add a product to my cart, and verify the cart contains the item."
)

SEED_URL = "https://automationexercise.com/"


async def main() -> None:
    """Run the pipeline with POM mode enabled and dump output."""
    print("=" * 80)
    print("POM Mode Debug Script")
    print("=" * 80)
    print()

    # Parse user story
    parser = FeatureParser()
    result = parser.parse(USER_STORY)
    if not result.success or result.specification is None:
        print(f"Parse failed: {result.error_message}")
        sys.exit(1)
    spec = result.specification
    requirement_model = parser.build_requirement_model(spec)
    print(f"User story: {spec.user_story}")
    print(f"Acceptance criteria: {len(spec.acceptance_criteria)} explicit criteria")
    for i, crit in enumerate(spec.acceptance_criteria, 1):
        print(f"  {i}. {crit}")
    print(f"Requirement model: {requirement_model.count} requirements (source: {requirement_model.source})")
    for i, req in enumerate(requirement_model.lines, 1):
        print(f"  {i}. {req}")
    print()

    # Build orchestrator with POM mode ON
    test_generator = TestGenerator()
    orchestrator = PlaceholderOrchestrator(
        starting_url=SEED_URL,
        pom_mode=True,  # <- POM mode enabled
    )

    print(f"POM mode: {orchestrator.pom_mode}")
    print()

    # Generate skeleton code
    print("--- Generating skeleton code ---")
    conditions_text = requirement_model.to_numbered_text()
    skeleton_code = await test_generator.generate_skeleton(
        USER_STORY,
        conditions_text,
        target_urls=[SEED_URL],
        expected_count=requirement_model.count,
    )
    parser_s = SkeletonParser()
    skeleton_code = parser_s.normalise_placeholder_actions(skeleton_code)
    print(f"Skeleton code ({len(skeleton_code)} chars):")
    print(skeleton_code[:2000])
    print("...")
    print()

    # Parse journeys from skeleton
    print("--- Parsing journeys ---")
    journeys = parser_s.parse_test_journeys(skeleton_code)
    if not journeys:
        print("WARNING: No journeys parsed from skeleton! Dumping skeleton for inspection:")
        print(skeleton_code[:3000])
        print("...")
    print(f"Journeys: {len(journeys)}")
    for journey in journeys:
        print(f"  - {journey.test_name} (lines {journey.start_line}-{journey.end_line})")
        print(f"    Steps: {len(journey.steps)}")
        for step in journey.steps:
            print(f"      - {step.raw_line}")
            for ph in step.placeholders:
                print(f"        [{ph.action}] {ph.description} -> {ph.token}")
    print()

    # Scrape pages
    print("--- Scraping pages ---")
    pages_to_scrape = orchestrator._build_candidate_urls(
        seed_urls=[SEED_URL],
        page_requirements=[],
        journeys=journeys,
        user_story=USER_STORY,
        conditions=conditions_text,
    )
    print(f"Pages to scrape: {len(pages_to_scrape)}")
    for url in pages_to_scrape[:5]:
        print(f"  - {url}")
    if len(pages_to_scrape) > 5:
        print(f"  ... and {len(pages_to_scrape) - 5} more")
    print()

    scraped_data: dict[str, list[dict[str, str]]] = {}
    scraped_errors: dict[str, str] = {}
    for url in pages_to_scrape:
        print(f"  Scraping: {url}")
        await orchestrator._ensure_scraped(url, scraped_data, scraped_errors)
        print(f"    -> {len(scraped_data.get(url, []))} elements")

    # Upgrade stateful pages
    scraped_data = await orchestrator._upgrade_stateful_pages(scraped_data)
    print()

    # Build page objects
    print("--- Building page objects ---")
    # Build page objects from ALL scraped pages (not just seed URLs)
    # This ensures we have page objects for discovered URLs like /category_products/3, /view_cart, etc.
    all_scraped_urls = list(scraped_data.keys())
    print(f"[DEBUG] Scraped URLs: {all_scraped_urls}")
    scraped_pages = orchestrator._build_scraped_page_records(
        all_scraped_urls, scraped_data, scraped_errors
    )
    page_objects = orchestrator._build_page_object_artifacts(scraped_pages)
    print(f"Page objects: {len(page_objects)}")
    for po in page_objects:
        print(f"  - {po.class_name} ({po.module_name}) for {po.url}")
        print(f"    Methods: {len(po.methods)}")
        for method in po.methods[:5]:
            print(f"      - {method}")
    print()

    # Resolve placeholders
    print("--- Resolving placeholders (POM mode) ---")

    # Debug: show what page objects we have
    print(f"[DEBUG] Generated page objects: {len(page_objects)}")
    for po in page_objects:
        print(f"  - {po.class_name} ({po.module_name}) for {po.url}")

    resolved_code = await orchestrator._replace_placeholders_sequentially(
        skeleton_code=skeleton_code,
        journeys=journeys,
        page_requirements=[],
        seed_urls=[SEED_URL],
        scraped_data=scraped_data,
        scraped_errors=scraped_errors,
    )

    # Inject POM imports and instantiations
    pom_imports = orchestrator._build_pom_imports(page_objects)
    pom_instantiation = orchestrator._build_pom_instantiation(page_objects)

    print("--- POM Imports ---")
    for imp in pom_imports:
        print(f"  {imp}")
    print()

    print("--- POM Instantiation ---")
    for inst in pom_instantiation:
        print(f"  {inst}")
    print()

    # Inject POM imports and instantiation into the resolved code
    if pom_imports:
        resolved_code = TestOrchestrator._inject_pom_imports(resolved_code, pom_imports)
    if pom_instantiation:
        resolved_code = TestOrchestrator._inject_pom_instantiation(resolved_code, pom_instantiation)

    print("--- Resolved code (first 5000 chars) ---")
    print(resolved_code[:5000])
    print("...")
    print()

    # Write to file for inspection
    output_dir = project_root / "generated_tests"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "debug_pom_mode_test.py"
    output_file.write_text(resolved_code)
    print(f"Full output written to: {output_file}")
    print()

    # Check for double-wrapping
    print("--- Checking for double-wrapping bugs ---")
    lines = resolved_code.splitlines()
    double_wrap_count = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Check for page.click(page.XXX.click(...)) patterns
        if "page." in stripped and ".click(" in stripped:
            # Count page. occurrences
            page_count = stripped.count("page.")
            if page_count > 1:
                print(f"  [WARN] Line {i}: possible double-wrapping: {stripped[:120]}")
                double_wrap_count += 1
    if double_wrap_count == 0:
        print("  [OK] No double-wrapping detected!")
    else:
        print(f"  [WARN] Found {double_wrap_count} potential double-wrapping issues!")
    print()

    # Check for POM method calls
    print("--- Checking for POM method calls ---")
    pom_call_count = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        has_click = ".click(" in stripped
        # Check for direct page.click() calls (not home_page.click())
        has_direct_page_call = bool(re.search(r'\bpage\.\w+\(', stripped))
        no_evidence = "evidence_tracker" not in stripped
        has_parens = "(" in stripped and ")" in stripped
        if has_click and not has_direct_page_call and no_evidence and has_parens:
            pom_call_count += 1
            print(f"  Line {i}: {stripped[:120]}")
        elif has_click and has_direct_page_call:
            print(f"  [DEBUG] Line {i} has direct page. call: {stripped[:80]}")
    print(f"  Found {pom_call_count} POM method calls")


if __name__ == "__main__":
    asyncio.run(main())
