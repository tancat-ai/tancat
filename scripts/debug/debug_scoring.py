#!/usr/bin/env python3
"""Debug scoring for shopping cart icon element."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

from src.placeholder_resolver import PlaceholderResolver
from src.scraper import PageScraper

resolver = PlaceholderResolver()
scraper = PageScraper()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://www.saucedemo.com", wait_until="networkidle")
    page.fill("#user-name", "standard_user")
    page.fill("#password", "secret_sauce")
    page.click("#login-button")
    page.wait_for_load_state("networkidle")
    html = page.content()
    elements = scraper._extract_elements_from_html(html, base_url=page.url)
    browser.close()

# Find the shopping cart link element
print("=== Shopping cart link element ===")
for elem in elements:
    sel = str(elem.get("selector", ""))
    if "shopping-cart" in sel or "cart_link" in sel:
        print(f"  selector: {elem.get('selector')}")
        print(f"  text:     '{elem.get('text')}'")
        print(f"  data_test: '{elem.get('data_test')}'")
        print(f"  id:       '{elem.get('id')}'")
        print(f"  classes:  '{elem.get('classes')}'")
        print(f"  role:     '{elem.get('role')}'")
        print()

for desc in ["shopping cart icon", "cart icon", "shopping cart"]:
    print(f'=== Testing: "{desc}" ===')
    ranked = resolver.rank_candidates("CLICK", desc, elements)
    print(f"  Total ranked: {len(ranked)}")
    for score, elem in ranked[:8]:
        sel = str(elem.get("selector", ""))[:50]
        text = str(elem.get("text", ""))[:30]
        dt = str(elem.get("data_test", ""))[:30]
        eid = str(elem.get("id", ""))[:20]
        print(f"    score={score:3d} text='{text}' data_test='{dt}' id='{eid}' -> {sel}")
    print()
