#!/usr/bin/env python
"""Validate placeholder resolution fixes.

Runs skeleton generation → scraping → placeholder resolution and reports
whether the quote normalization + text-content bonus fixes improve results.

Usage:
    .venv/Scripts/python.exe scripts/debug/validate_fixes.py
"""

import asyncio
import re
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import nest_asyncio  # noqa: E402

nest_asyncio.apply()

from src.llm_client import LLMClient  # noqa: E402
from src.placeholder_resolver import PlaceholderResolver  # noqa: E402
from src.scraper import PageScraper  # noqa: E402
from src.skeleton_parser import SkeletonParser  # noqa: E402
from src.test_generator import TestGenerator  # noqa: E402

TARGET_URL = "https://automationexercise.com"

USER_STORY = "As a customer, I want to browse products and add them to my cart"

CONDITIONS = """1. Navigate to the automationexercise.com home page
2. Click the 'Products' link in the header navigation
3. Click 'Add to cart' for a product
4. Verify confirmation message appears"""


async def main():
    # ── Setup LLM ───────────────────────────────────────────────────────
    LLMClient.set_session_provider(provider="lm-studio", model=None)
    client = LLMClient()
    print(f"Using: provider={client.provider_name}, model={client.model}")

    # ── Generate skeleton ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 1: SKELETON GENERATION")
    print("=" * 60)

    generator = TestGenerator(client=client)
    raw_skeleton = await generator.generate_skeleton(
        user_story=USER_STORY,
        conditions=CONDITIONS,
        target_urls=[TARGET_URL],
        expected_count=6,
    )
    skeleton = SkeletonParser.normalise_placeholder_actions(raw_skeleton)

    TOKEN_RE = re.compile(r"\{\{(\w+):([^}]+)\}\}")
    tokens = TOKEN_RE.findall(skeleton)

    print(f"\nTokens found: {len(tokens)}")
    for kind, desc in tokens:
        print(f"  [{kind:10s}] {desc}")

    unique_tokens = sorted({(kind, desc.strip()) for kind, desc in tokens})
    print(f"\nUnique placeholders: {len(unique_tokens)}")
    for kind, desc in unique_tokens:
        print(f"  [{kind:10s}] {desc}")

    # ── Scrape ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 2: SCRAPING")
    print("=" * 60)

    scraper = PageScraper()
    raw_result = await scraper.scrape_url(TARGET_URL)
    candidates, error, final_url = raw_result

    if error:
        print(f"Scrape error: {error}")
        return
    print(f"Scraped URL: {final_url}")
    print(f"Candidates scraped: {len(candidates)}")

    # Show tag breakdown
    from collections import Counter

    tag_counts = Counter(e.get("tag", "unknown") for e in candidates)
    print("\nTag breakdown:")
    for tag, count in tag_counts.most_common(10):
        print(f"  <{tag}>: {count}")

    # ── Resolve placeholders ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 3: PLACEHOLDER RESOLUTION (with fixes)")
    print("=" * 60)

    resolver = PlaceholderResolver()

    resolved = 0
    text_mismatch = 0
    no_candidates = 0
    details = []

    for action, desc in unique_tokens:
        scored = resolver.rank_candidates(action, desc, candidates)

        if scored:
            top_score, top_elem = scored[0]
            selector = (top_elem.get("selector") or "")[:80]
            elem_text = (top_elem.get("text") or "")[:60]

            # Text validation
            if top_elem.get("text"):
                text_valid = resolver.text_matches_description(top_elem.get("text", ""), desc)
            else:
                text_valid = True

            status = "RESOLVED" if text_valid else "MISMATCH"
            if text_valid:
                resolved += 1
            else:
                text_mismatch += 1

            detail = {
                "token": f"{{{action}:{desc}}}",
                "status": status,
                "selector": selector,
                "score": top_score,
                "candidates": len(scored),
                "elem_text": elem_text,
                "text_valid": text_valid,
            }
            details.append(detail)

            print(f"\n  [{status:10s}] {{{action}:{desc}}}")
            print(f"           -> {selector}")
            print(f"           (score={top_score:.2f}, candidates={len(scored)})")
            if elem_text:
                print(f'           text: "{elem_text}"')
            if not text_valid:
                print("           ⚠️  TEXT VALIDATION FAILED")
        else:
            no_candidates += 1
            print(f"\n  [NO_CANDS]  {{{action}:{desc}}}")

    # ── Summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = len(unique_tokens)
    print(f"Total unique placeholders: {total}")
    print(f"  Resolved:       {resolved} ({resolved / total * 100:.0f}%)")
    print(f"  Text mismatch:  {text_mismatch}")
    print(f"  No candidates:  {no_candidates}")

    # Check specifically for the "Products" token
    print("\n" + "-" * 60)
    print("KEY CHECK: 'Products' link resolution")
    print("-" * 60)
    for d in details:
        if "products" in d["token"].lower() or "products" in d["selector"].lower():
            print(f"  Token:    {d['token']}")
            print(f"  Status:   {d['status']}")
            print(f"  Selector: {d['selector']}")
            print(f"  Score:    {d['score']:.2f}")
            print(f'  Text:     "{d["elem_text"]}"')
            if d["status"] == "RESOLVED":
                print("  ✅ Products link resolved correctly!")
            else:
                print("  ❌ Products link still has issues")

    # Check for "Add to cart" resolution
    print("\n" + "-" * 60)
    print("KEY CHECK: 'Add to cart' button resolution")
    print("-" * 60)
    for d in details:
        if "add to cart" in d["token"].lower():
            print(f"  Token:    {d['token']}")
            print(f"  Status:   {d['status']}")
            print(f"  Selector: {d['selector']}")
            print(f"  Score:    {d['score']:.2f}")
            print(f'  Text:     "{d["elem_text"]}"')


if __name__ == "__main__":
    asyncio.run(main())
