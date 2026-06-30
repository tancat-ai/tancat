#!/usr/bin/env python3
"""Unified debug CLI for AI-Playwright-Test-Generator.

Quick diagnostic commands for pipeline debugging. All commands are callable
without IDE interaction.

Usage:
    python scripts/debug.py --help
    python scripts/debug.py text-validation        # offline — resolver logic
    python scripts/debug.py skeleton               # offline — placeholder parsing
    python scripts/debug.py scrape <url>           # scrape and dump elements
    python scripts/debug.py resolve <url> --action CLICK --desc "add to cart"
    python scripts/debug.py resolve <url> --action ASSERT --desc "cart items" --pom
    python scripts/debug.py score <url> --desc "cart icon"
    python scripts/debug.py pipeline <url> --story "..." [--pom]
    python scripts/debug.py pom <url> --story "..."  # POM mode pipeline trace

Commands that require a browser (scrape, resolve, score, pipeline, pom) need
Playwright browsers installed: playwright install chromium

Commands that require an LLM (pipeline, pom) need .env configured.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Offline commands — no browser or LLM needed
# ---------------------------------------------------------------------------

def cmd_text_validation(argv: list[str] | None = None) -> int:
    """Validate text_matches_description against known cases."""
    from src.placeholder_resolver import PlaceholderResolver

    resolver = PlaceholderResolver()

    test_cases: list[tuple[str, str, bool]] = [
        ("Add to cart", "Add to cart button next to a product", True),
        ("Cart", "Cart link or cart icon in the page header", True),
        ("Continue Shopping", "Continue Shopping button", True),
        ("Add to cart", "Cart link or cart icon in the page header", True),  # B-012: raw text match; action-verb guard is in orchestrator
        ("Subscribe", "Continue Shopping button", False),
        ("View cart", "Go to cart", True),
        ("Checkout", "Proceed to checkout", True),
        ("Home", "Navigate to home page", True),
        ("", "Continue Shopping button", False),
        ("Login", "Sign in button", True),
        ("Your cart is empty!", "cart content with items", False),
        ("Cart is empty", "cart page with selected items", False),
        ("Items in your cart", "cart content with items", True),
        ("Logout", "Sign out button", True),
        ("Sign Up", "Register account", True),
    ]

    print("=" * 70)
    print("TEXT VALIDATION — resolver.text_matches_description()")
    print("=" * 70)

    passed = 0
    failed = 0
    for element_text, description, expected in test_cases:
        result = resolver.text_matches_description(element_text, description)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] '{element_text}' vs '{description}' -> {result} (expected {expected})")

    print()
    print(f"Results: {passed} passed, {failed} failed ({passed + failed} total)")
    print()
    return 1 if failed else 0


def cmd_skeleton(argv: list[str] | None = None) -> int:
    """Inspect placeholder extraction from sample skeleton code."""
    from src.skeleton_parser import SkeletonParser

    parser = SkeletonParser()

    sample = """
import pytest
from playwright.sync_api import Page


def test_01_browse_products(page: Page) -> None:
    page.goto("{{GOTO:home page}}")
    page.locator("{{{{CLICK:product category link}}}}").click()


def test_02_add_to_cart(page: Page) -> None:
    page.locator("{{{{FILL:search bar}}}}").fill("dress")
    page.locator("{{{{CLICK:search button}}}}").click()
    page.locator("{{{{ASSERT:product listing}}}}").is_visible()


def test_03_view_cart(page: Page) -> None:
    page.locator("{{{{CLICK:Cart link}}}}").click()
    page.locator("{{{{ASSERT:cart contents}}}}").is_visible()
"""

    print("=" * 70)
    print("SKELETON INSPECTION — placeholder parsing")
    print("=" * 70)
    print()

    # Placeholder uses
    uses = parser.parse_placeholder_uses(sample)
    print(f"parse_placeholder_uses(): {len(uses)} tokens")
    for use in uses:
        token = '{{{{' + f'({use.action}:{use.description})' + '}}}}'
        print(f'  Line {use.line_number}: {token}')

    # Placeholders (deduped)
    placeholders = parser.parse_placeholders(sample)
    print(f"\nparse_placeholders(): {len(placeholders)} unique")
    for action, description in placeholders:
        print(f"  ({action}) '{description}'")

    # Journeys
    journeys = parser.parse_test_journeys(sample)
    print(f"\nparse_test_journeys(): {len(journeys)} journeys")
    for j in journeys:
        print(
            f"  {j.test_name}: {len(j.steps)} steps, "
            f"{len(j.placeholders)} placeholders (lines {j.start_line}-{j.end_line})"
        )

    # Normalisation
    raw = 'page.locator("{{{{CLICK:product link}}}}").click()'
    normalised = parser.normalise_placeholder_actions(raw)
    print("\nnormalise_placeholder_actions():")
    print(f"  in:  {raw}")
    print(f"  out: {normalised}")

    print()
    return 0


# ---------------------------------------------------------------------------
# Browser commands — need Playwright
# ---------------------------------------------------------------------------

async def _do_scrape(url: str, headed: bool = False) -> int:
    """Scrape a URL and dump elements."""
    from src.scraper import PageScraper

    print("=" * 70)
    print(f"SCRAPE — {url}")
    print("=" * 70)
    print()

    scraper = PageScraper()
    elements, error, final_url = await scraper.scrape_url(url)

    if error:
        print(f"  [ERROR] {error}")
        return 1

    display_url = final_url or url
    print(f"  Scraped {len(elements)} elements from: {display_url}")
    print()
    print(f"  {'Text':<35} {'Role':<15} {'Selector'}")
    print(f"  {'─' * 35} {'─' * 15} {'─' * 40}")

    for elem in elements[:50]:
        text = str(elem.get("text", ""))[:34] or "(empty)"
        role = str(elem.get("role", ""))[:14] or "(none)"
        selector = str(elem.get("selector", ""))[:45]
        print(f"  {text:<35} {role:<15} {selector}")

    if len(elements) > 50:
        print(f"\n  ... and {len(elements) - 50} more elements")

    print()
    return 0


async def _do_resolve(url: str, action: str, description: str, pom_mode: bool = False) -> int:
    """Resolve a single placeholder against scraped data."""
    from src.placeholder_resolver import PlaceholderResolver
    from src.scraper import PageScraper

    print("=" * 70)
    print(f"RESOLVE — ({action}) '{description}' on {url}")
    if pom_mode:
        print("  POM mode: element-to-method mapping")
    print("=" * 70)
    print()

    scraper = PageScraper()
    resolver = PlaceholderResolver()

    elements, error, final_url = await scraper.scrape_url(url)
    if error:
        print(f"  [ERROR] Scraping failed: {error}")
        return 1

    display_url = final_url or url
    print(f"  Scraped {len(elements)} elements from: {display_url}")
    print()

    ranked = resolver.rank_candidates(action, description, elements)
    print(f"  Ranked {len(ranked)} candidates")
    print()

    if not ranked:
        print("  No candidates found.")
        print()
        return 1

    print(f"  {'Score':<8} {'Text':<30} {'Selector'}")
    print(f"  {'─' * 8} {'─' * 30} {'─' * 40}")
    for score, elem in ranked[:10]:
        text = str(elem.get("text", ""))[:29] or "(empty)"
        selector = str(elem.get("selector", ""))[:45]
        print(f"  {score:<8} {text:<30} {selector}")

    # Show text match for top candidate
    if ranked:
        top = ranked[0][1]
        top_text = str(top.get("text", "")).strip()
        match = resolver.text_matches_description(top_text, description)
        print(f"\n  Top candidate text match: {match}")

        # Show top candidate selector
        top_sel = top.get("selector", "(none)")
        top_id = top.get("id", "") or top.get("name", "")
        if top_id:
            top_sel = f"#{top_id} ({top_sel})"
        print(f"  Resolved selector: {top_sel}")

        if pom_mode:
            print("\n  [POM mode] This element would be mapped to a POM method.")
            print(f"  Method hint: {action.lower()}_{description.replace(' ', '_')[:20]}")

    print()
    return 0


async def _do_score(url: str, description: str) -> int:
    """Score all elements against a description across action types."""
    from src.placeholder_resolver import PlaceholderResolver
    from src.scraper import PageScraper

    print("=" * 70)
    print(f"SCORE — '{description}' on {url}")
    print("=" * 70)
    print()

    scraper = PageScraper()
    resolver = PlaceholderResolver()

    elements, error, final_url = await scraper.scrape_url(url)
    if error:
        print(f"  [ERROR] Scraping failed: {error}")
        return 1

    display_url = final_url or url
    print(f"  Scraped {len(elements)} elements from: {display_url}")
    print()

    for action in ["CLICK", "FILL", "ASSERT"]:
        ranked = resolver.rank_candidates(action, description, elements)
        print(f"  ({action}) top 3:")
        for score, elem in ranked[:3]:
            text = str(elem.get("text", ""))[:25] or "(empty)"
            selector = str(elem.get("selector", ""))[:45]
            print(f"    score={score:<4} text='{text}' -> {selector}")
        if not ranked:
            print("    (no candidates)")
        print()

    return 0


# ---------------------------------------------------------------------------
# Full pipeline commands — need LLM + browser
# ---------------------------------------------------------------------------

async def _do_pipeline(url: str, story: str, conditions: str | None, pom_mode: bool,
                       provider: str | None = None) -> int:
    """Run the full skeleton-first pipeline with tracing."""
    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.skeleton_parser import SkeletonParser
    from src.test_generator import TestGenerator

    mode_label = "POM" if pom_mode else "Standard"
    print("=" * 70)
    print(f"PIPELINE ({mode_label}) — {url}")
    print(f"  Story: {story}")
    print("=" * 70)
    print()

    if provider:
        LLMClient.set_session_provider(provider)

    client = LLMClient()
    print(f"  LLM: {client.provider_name} / {client.model}")
    print()

    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=pom_mode)

    default_conditions = (
        "1. Navigate to the home page\n"
        "2. Perform a key interaction\n"
        "3. Verify the result\n"
        "(Total: 3 criteria)"
    )
    conditions_text = conditions or default_conditions

    parser = SkeletonParser()

    # Phase 1: Skeleton
    print("[Phase 1] Generating skeleton...")
    start = time.time()
    skeleton = await generator.generate_skeleton(
        story, conditions_text, target_urls=[url], expected_count=3,
    )
    duration = time.time() - start
    skeleton = parser.normalise_placeholder_actions(skeleton)
    placeholders = parser.parse_placeholders(skeleton)
    journeys = parser.parse_test_journeys(skeleton)

    print(f"  Skeleton: {len(skeleton)} chars, {len(placeholders)} placeholders, "
          f"{len(journeys)} journeys ({duration:.1f}s)")
    print()
    print("  Skeleton preview:")
    for line in skeleton.splitlines()[:20]:
        print(f"    {line}")
    if len(skeleton.splitlines()) > 20:
        print(f"    ... ({len(skeleton.splitlines()) - 20} more lines)")
    print()

    # Phase 2: Full pipeline
    print("[Phase 2] Running full pipeline...")
    start = time.time()
    final_code = await orchestrator.run_pipeline(
        user_story=story,
        conditions=conditions_text,
        target_urls=[url],
    )
    duration = time.time() - start

    result = orchestrator.last_result
    print(f"  Pipeline complete in {duration:.1f}s")
    print()

    # Results
    if result:
        print(f"  Scraped pages: {len(result.scraped_pages)}")
        for page_url, elems in result.scraped_pages.items():
            short = page_url[-50:] if len(page_url) > 50 else page_url
            print(f"    {short}: {len(elems)} elements")

        print(f"  Unresolved placeholders: {len(result.unresolved_placeholders)}")
        for u in result.unresolved_placeholders[:10]:
            print(f"    [SKIP] {u}")

        if pom_mode and result.generated_page_objects:
            print(f"  Generated POM classes: {len(result.generated_page_objects)}")
            for pom in result.generated_page_objects:
                print(f"    class {pom.class_name}: {len(pom.methods)} methods")
        print()

    # Output analysis
    print("[Output Analysis]")
    unresolved = [line.strip() for line in final_code.splitlines() if "pytest.skip(" in line]
    ph_artifacts = re.findall(r"\{\{\{\{(\w+):", final_code)
    has_evidence = "evidence_tracker." in final_code
    has_evidence_mark = "@pytest.mark.evidence" in final_code
    test_funcs = re.findall(r"^def\s+test_\w+", final_code, re.M)

    checks = [
        ("No unresolved placeholders", len(unresolved) == 0,
         f"{len(unresolved)} pytest.skip lines"),
        ("No placeholder artifacts", len(ph_artifacts) == 0,
         f"{len(ph_artifacts)} tokens remaining"),
        ("Evidence tracker calls", has_evidence,
         "found" if has_evidence else "missing"),
        ("@pytest.mark.evidence", has_evidence_mark,
         "found" if has_evidence_mark else "missing"),
        (f"Test functions ({len(test_funcs)})", len(test_funcs) >= 1,
         str(test_funcs)),
    ]
    if pom_mode:
        has_pom_class = "class " in final_code and "(page:" in final_code
        checks.append(("POM class present", has_pom_class,
                       "found" if has_pom_class else "missing"))

    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {detail}")

    print()
    # Final code preview
    print("[Final Code — first 60 lines]")
    for i, line in enumerate(final_code.splitlines()[:60], 1):
        print(f"  {i:3d} | {line}")
    if len(final_code.splitlines()) > 60:
        print(f"  ... ({len(final_code.splitlines()) - 60} more lines)")
    print()

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="debug",
        description="Unified debug CLI for AI-Playwright-Test-Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  text-validation    Offline: test text_matches_description logic
  skeleton           Offline: inspect placeholder parsing on sample code
  scrape <url>       Scrape a URL and dump interactive elements
  resolve <url>      Resolve a single placeholder against scraped elements
                     Requires --action and --desc
  score <url>        Score all elements against a description
                     Requires --desc
  pipeline <url>     Full skeleton-first pipeline trace
                     Requires --story
  pom <url>          Same as pipeline but with POM mode enabled

Examples:
  python scripts/debug.py text-validation
  python scripts/debug.py skeleton
  python scripts/debug.py scrape https://saucedemo.com
  python scripts/debug.py resolve https://saucedemo.com --action CLICK --desc "add to cart"
  python scripts/debug.py resolve https://saucedemo.com --action ASSERT --desc "cart items" --pom
  python scripts/debug.py score https://saucedemo.com --desc "cart icon"
  python scripts/debug.py pipeline https://saucedemo.com --story "I want to login and checkout"
  python scripts/debug.py pom https://saucedemo.com --story "I want to login and checkout"
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Debug command")

    # text-validation
    subparsers.add_parser("text-validation", help="Test text validation logic (offline)")

    # skeleton
    subparsers.add_parser("skeleton", help="Inspect placeholder parsing (offline)")

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="Scrape and dump elements")
    p_scrape.add_argument("url", help="URL to scrape")

    # resolve
    p_resolve = subparsers.add_parser("resolve", help="Resolve a single placeholder")
    p_resolve.add_argument("url", help="URL to scrape")
    p_resolve.add_argument("--action", required=True, choices=["CLICK", "FILL", "ASSERT", "GOTO"],
                           help="Placeholder action type")
    p_resolve.add_argument("--desc", required=True, help="Placeholder description")
    p_resolve.add_argument("--pom", action="store_true", help="Show POM mode hints")

    # score
    p_score = subparsers.add_parser("score", help="Score elements against description")
    p_score.add_argument("url", help="URL to scrape")
    p_score.add_argument("--desc", required=True, help="Description to score against")

    # pipeline
    p_pipe = subparsers.add_parser("pipeline", help="Full pipeline trace (Standard mode)")
    p_pipe.add_argument("url", help="Target URL")
    p_pipe.add_argument("--story", required=True, help="User story")
    p_pipe.add_argument("--conditions", help="Acceptance conditions")
    p_pipe.add_argument("--provider", help="LLM provider override")

    # pom
    p_pom = subparsers.add_parser("pom", help="Full pipeline trace (POM mode)")
    p_pom.add_argument("url", help="Target URL")
    p_pom.add_argument("--story", required=True, help="User story")
    p_pom.add_argument("--conditions", help="Acceptance conditions")
    p_pom.add_argument("--provider", help="LLM provider override")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Offline commands
    if args.command == "text-validation":
        return cmd_text_validation()
    if args.command == "skeleton":
        return cmd_skeleton()

    # Browser commands
    if args.command == "scrape":
        return asyncio.run(_do_scrape(args.url))
    if args.command == "resolve":
        return asyncio.run(_do_resolve(args.url, args.action, args.desc, args.pom))
    if args.command == "score":
        return asyncio.run(_do_score(args.url, args.desc))

    # Full pipeline
    if args.command == "pipeline":
        return asyncio.run(_do_pipeline(args.url, args.story, args.conditions, pom_mode=False,
                                        provider=args.provider))
    if args.command == "pom":
        return asyncio.run(_do_pipeline(args.url, args.story, args.conditions, pom_mode=True,
                                        provider=args.provider))

    parser.print_help()
    return 1


if __name__ == "__main__":
    # Windows UTF-8 fix
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    sys.exit(main())
