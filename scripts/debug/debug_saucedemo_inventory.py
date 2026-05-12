#!/usr/bin/env python3
"""Debug: scrape SauceDemo inventory page and show what Add-to-Cart buttons look like."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.placeholder_resolver import PlaceholderResolver  # noqa: E402
from src.scraper import PageScraper  # noqa: E402


async def main() -> None:
    scraper = PageScraper()
    resolver = PlaceholderResolver()

    # Scrape the inventory page (where the elements should be after login)
    url = "https://www.saucedemo.com/inventory.html"
    print(f"Scraping: {url}")
    print()

    elements, error, final_url = await scraper.scrape_url(url)
    if error:
        print(f"  Scraping error: {error}")
        return

    print(f"  Scraped {len(elements)} elements from: {final_url}")
    print()

    # Show all elements
    print("=" * 80)
    print("ALL SCRAPED ELEMENTS")
    print("=" * 80)
    for i, elem in enumerate(elements):
        selector = str(elem.get("selector", ""))[:80]
        text = str(elem.get("text", ""))[:50]
        role = str(elem.get("role", ""))[:20]
        elem_id = str(elem.get("id", ""))[:40]
        href = str(elem.get("href", ""))[:60]
        visible = elem.get("is_visible", True)
        vis_marker = " ✅" if visible else " ⛔"
        print(f"  [{i:2d}]{vis_marker} [{role:15s}] text='{text}' id='{elem_id}' -> {selector}")
        if href:
            print(f"         href={href}")
    print()

    # Now test the specific placeholder that fails
    print("=" * 80)
    print("PLACEHOLDER RESOLUTION TESTS")
    print("=" * 80)

    test_placeholders = [
        ("CLICK", "add to cart button for Sauce Labs Backpack"),
        ("CLICK", "add to cart button"),
        ("CLICK", "Sauce Labs Backpack add to cart"),
        ("CLICK", "shopping cart icon"),
        ("CLICK", "cart icon"),
        ("ASSERT", "cart badge updated"),
        ("CLICK", "shopping cart"),
    ]

    for action, description in test_placeholders:
        print(f"\n  Placeholder: ({action}) '{description}'")

        # Show ranked candidates
        ranked = resolver.rank_candidates(action, description, elements)
        print(f"    Ranked {len(ranked)} candidates:")
        for score, elem in ranked[:5]:
            selector = str(elem.get("selector", ""))[:60]
            text = str(elem.get("text", ""))[:40]
            elem_id = str(elem.get("id", ""))[:30]
            elem_text = str(elem.get("text", "")).strip()
            text_match = resolver.text_matches_description(elem_text, description)
            print(f"      score={score:3d} text_match={text_match!s:5s} text='{text}' id='{elem_id}' -> {selector}")

        # Full resolution
        best = resolver.find_best_element(action, description, elements)
        if best:
            resolved_selector = resolver._build_robust_locator(best)
            print(f"    ✅ Resolved to: {resolved_selector}")
        else:
            print("    ❌ No match found — will generate pytest.skip()")

    print()
    print("=" * 80)
    print("LOOKING FOR CART ICON / BADGE ELEMENTS")
    print("=" * 80)
    # Search for cart-related elements
    cart_elements = []
    for elem in elements:
        text = str(elem.get("text", "")).lower()
        selector = str(elem.get("selector", "")).lower()
        elem_id = str(elem.get("id", "")).lower()
        classes = str(elem.get("classes", "")).lower()
        if any(
            term in (text + selector + elem_id + classes) for term in ("cart", "basket", "bag", "shopping", "badge")
        ):
            cart_elements.append(elem)

    if cart_elements:
        print(f"  Found {len(cart_elements)} cart-related elements:")
        for elem in cart_elements:
            selector = str(elem.get("selector", ""))[:80]
            text = str(elem.get("text", ""))[:40]
            elem_id = str(elem.get("id", ""))[:30]
            classes = str(elem.get("classes", ""))[:40]
            print(f"    text='{text}' id='{elem_id}' classes='{classes}' -> {selector}")
    else:
        print("  No cart-related elements found on inventory page!")
        print("  (The cart icon/badge is likely on the login page or a header that appears after login)")

    # Also scrape the login page to see if cart icon is there
    print()
    print("=" * 80)
    print("SCRAPING LOGIN PAGE FOR CART ICON")
    print("=" * 80)
    login_elements, login_error, login_url = await scraper.scrape_url("https://saucedemo.com")
    if login_error:
        print(f"  Login page scraping error: {login_error}")
    else:
        print(f"  Scraped {len(login_elements)} elements from: {login_url}")
        for elem in login_elements:
            text = str(elem.get("text", "")).lower()
            selector = str(elem.get("selector", "")).lower()
            elem_id = str(elem.get("id", "")).lower()
            classes = str(elem.get("classes", "")).lower()
            if any(term in (text + selector + elem_id + classes) for term in ("cart", "basket", "bag", "shopping")):
                print(f"    text='{elem.get('text')}' id='{elem.get('id')}' -> {elem.get('selector')}")
        print("  (If no cart elements found, the cart icon only appears AFTER login)")


if __name__ == "__main__":
    asyncio.run(main())
