"""One-off: measure saucedemo's SPA soft-404 behavior with the project's Playwright setup.

Answers for Fix A (soft-404 recovery):
1. What status does page.goto() report for /inventory.html?
2. After networkidle, has the SPA bootstrapped (URL rewritten, real content)?
3. Does waiting longer change the rendered state?
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import sync_playwright  # noqa: E402

URLS = [
    "https://www.saucedemo.com/inventory.html",
    "https://www.saucedemo.com/cart.html",
    "https://www.saucedemo.com/?/inventory.html",
]


def probe(url: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(30_000)
        try:
            response = page.goto(url, wait_until="networkidle", timeout=30_000)
            status = response.status if response else "None"
            url_after = page.url
            title = page.title()
            body_len = len(page.evaluate("document.body ? document.body.innerText : ''"))
            has_spa_marker = "Single Page Apps for GitHub Pages" in (
                page.content()[:3000] or ""
            )
            print(f"\n=== {url}")
            print(f"  goto status        : {status}")
            print(f"  page.url after     : {url_after}")
            print(f"  title              : {title!r}")
            print(f"  body text length   : {body_len}")
            print(f"  spa shell present  : {has_spa_marker}")
            # Wait 2s more — does the app bootstrap later?
            page.wait_for_timeout(2000)
            print(f"  +2s title          : {page.title()!r}")
            print(f"  +2s url            : {page.url}")
            print(
                f"  +2s body text      : {len(page.evaluate('document.body ? document.body.innerText : \"\"'))}"
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR: {e}")
        finally:
            browser.close()


if __name__ == "__main__":
    for u in URLS:
        probe(u)
        time.sleep(0.5)
