#!/usr/bin/env python3
"""Debug: login to SauceDemo, then scrape inventory page to see Add-to-Cart buttons."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.placeholder_resolver import PlaceholderResolver
from src.scraper import PageScraper


def main() -> None:
    """Login to SauceDemo, scrape inventory, then test resolution."""
    from playwright.sync_api import sync_playwright

    scraper = PageScraper()
    resolver = PlaceholderResolver()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        # Step 1: Login
        print("=" * 80)
        print("STEP 1: LOGIN TO SAUCEDEMO")
        print("=" * 80)
        page.goto("https://www.saucedemo.com", wait_until="networkidle")
        print(f"  Login page URL: {page.url}")

        page.fill("#user-name", "standard_user")
        page.fill("#password", "secret_sauce")
        page.click("#login-button")
        page.wait_for_load_state("networkidle")

        print(f"  After login URL: {page.url}")

        # Step 2: Scrape inventory page
        print()
        print("=" * 80)
        print("STEP 2: SCRAPE INVENTORY PAGE")
        print("=" * 80)

        html = page.content()
        elements = scraper._extract_elements_from_html(html, base_url=page.url)
        print(f"  Scraped {len(elements)} elements from: {page.url}")
        print()

        # Show ALL elements
        print("=" * 80)
        print("ALL ELEMENTS ON INVENTORY PAGE")
        print("=" * 80)
        for i, elem in enumerate(elements):
            selector = str(elem.get("selector", ""))[:80]
            text = str(elem.get("text", ""))[:50]
            role = str(elem.get("role", ""))[:15]
            elem_id = str(elem.get("id", ""))[:30]
            name = str(elem.get("name", ""))[:20]
            aria_label = str(elem.get("aria_label", ""))[:20]
            classes = str(elem.get("classes", ""))[:40]
            print(f"  [{i:2d}] [{role:13s}] text='{text}' id='{elem_id}' name='{name}' aria='{aria_label}'")
            print(f"        classes='{classes}'")
            print(f"        -> {selector}")
            print()

        # Step 3: Test resolution
        print("=" * 80)
        print("STEP 3: RESOLUTION TESTS")
        print("=" * 80)

        test_placeholders = [
            ("CLICK", "add to cart button for Sauce Labs Backpack"),
            ("CLICK", "add to cart button"),
            ("CLICK", "Sauce Labs Backpack"),
            ("CLICK", "shopping cart icon"),
            ("CLICK", "cart icon"),
            ("ASSERT", "cart badge updated"),
            ("ASSERT", "inventory page visible"),
            ("CLICK", "shopping cart"),
        ]

        for action, description in test_placeholders:
            print(f"\n  Placeholder: ({action}) '{description}'")

            ranked = resolver.rank_candidates(action, description, elements)
            print(f"    Ranked {len(ranked)} candidates:")
            for score, elem in ranked[:5]:
                sel = str(elem.get("selector", ""))[:50]
                text = str(elem.get("text", ""))[:30]
                elem_id = str(elem.get("id", ""))[:25]
                elem_text = str(elem.get("text", "")).strip()
                text_match = resolver.text_matches_description(elem_text, description)
                print(f"      score={score:3d} text_match={str(text_match):5s} text='{text}' id='{elem_id}' -> {sel}")

            best = resolver.find_best_element(action, description, elements)
            if best:
                resolved = resolver._build_robust_locator(best)
                best_text = str(best.get("text", ""))[:30]
                best_id = str(best.get("id", ""))[:25]
                print(f"    ✅ Resolved: text='{best_text}' id='{best_id}' -> {resolved}")
            else:
                print("    ❌ No match — will generate pytest.skip()")

        # Step 4: Look for cart-specific elements
        print()
        print("=" * 80)
        print("STEP 4: CART-RELATED ELEMENTS")
        print("=" * 80)
        cart_terms = ["cart", "basket", "bag", "shopping", "badge", "checkout"]
        cart_elements = []
        for elem in elements:
            haystack = (
                str(elem.get("text", "")) +
                str(elem.get("selector", "")) +
                str(elem.get("id", "")) +
                str(elem.get("classes", "")) +
                str(elem.get("aria_label", ""))
            ).lower()
            if any(term in haystack for term in cart_terms):
                cart_elements.append(elem)

        if cart_elements:
            print(f"  Found {len(cart_elements)} cart-related elements:")
            for elem in cart_elements:
                sel = str(elem.get("selector", ""))[:60]
                text = str(elem.get("text", ""))[:30]
                elem_id = str(elem.get("id", ""))[:25]
                print(f"    text='{text}' id='{elem_id}' -> {sel}")
        else:
            print("  No cart-related elements on inventory page.")
            print("  (Cart icon/badge is likely only visible after adding items)")

        browser.close()


if __name__ == "__main__":
    main()
