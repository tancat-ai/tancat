"""Playwright session-backed scraper for stateful pages (e.g., cart/checkout).

This module intentionally launches Playwright inside a dedicated subprocess on
Windows. Streamlit often runs app code in a background thread where Playwright's
browser-launch subprocesses can fail with `NotImplementedError`.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from src.scraper import PageScraper


class StatefulPageScraper:
    """Scrape pages using a Playwright browser context with a cart session."""

    def __init__(self, starting_url: str, *, timeout_ms: int = 30_000) -> None:
        self.starting_url = starting_url.strip()
        self.timeout_ms = timeout_ms
        self._html_scraper = PageScraper(timeout=30.0)

    async def scrape_url(self, url: str) -> list[dict[str, Any]]:
        """Async wrapper around the subprocess-backed scrape implementation."""
        target_url = (url or "").strip()
        if not target_url:
            return []
        scraped = await self.scrape_urls([target_url])
        return scraped.get(target_url, [])

    async def scrape_urls(self, urls: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Scrape multiple URLs in a single Playwright session."""
        cleaned = [url.strip() for url in urls if url and url.strip()]
        if not cleaned:
            return {}
        return await asyncio.to_thread(self._scrape_urls_via_subprocess, cleaned)

    def _scrape_urls_via_subprocess(self, urls: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Run the sync Playwright workflow in a clean subprocess main thread."""
        payload = {
            "starting_url": self.starting_url,
            "timeout_ms": self.timeout_ms,
            "urls": urls,
        }
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--stateful-scrape"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            timeout=max(120, int(self.timeout_ms / 1000) * max(1, len(urls))),
        )
        if completed.returncode != 0:
            return {url: [] for url in urls}

        try:
            data = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            return {url: [] for url in urls}

        if not isinstance(data, dict):
            return {url: [] for url in urls}

        output: dict[str, list[dict[str, Any]]] = {}
        for url in urls:
            elements = data.get(url, [])
            output[url] = elements if isinstance(elements, list) else []
        return output

    def _scrape_urls_sync(self, urls: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Sync implementation for multi-URL session scrape."""
        output: dict[str, list[dict[str, Any]]] = {}

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)

            try:
                self._seed_cart_session(page)
                for url in urls:
                    try:
                        page.goto(url, wait_until="domcontentloaded")
                        html = page.content()
                        output[url] = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001
                    except Exception:
                        output[url] = []
            finally:
                context.close()
                browser.close()

        return output

    def _seed_cart_session(self, page: Any) -> None:
        """Navigate + try to add one item to cart (best effort)."""
        if not self.starting_url:
            return

        page.goto(self.starting_url, wait_until="domcontentloaded")
        self._dismiss_consent_overlays(page)

        add_to_cart_selectors = [
            '[data-product-id="11"]',
            "[data-product-id]:visible",
            'a:has-text("Add to cart")',
            'button:has-text("Add to cart")',
            ".add-to-cart",
        ]
        for selector in add_to_cart_selectors:
            try:
                loc = page.locator(selector).first
                if loc.count() > 0:
                    try:
                        loc.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    loc.click(timeout=5000)
                    break
            except Exception:
                continue

        modal_dismiss_selectors = [
            'button:has-text("Continue Shopping")',
            'button:has-text("Close")',
            'button[aria-label="Close"]',
            ".close-modal",
            ".modal-footer button",
        ]
        for selector in modal_dismiss_selectors:
            try:
                loc = page.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    break
            except Exception:
                continue

    @staticmethod
    def _dismiss_consent_overlays(page: Any) -> None:
        selectors = [
            "button:has-text('Consent')",
            "button:has-text('Accept')",
            "button:has-text('Continue')",
            "button:has-text('OK')",
            "button:has-text('Got it')",
            "button:has-text('I Agree')",
            "button:has-text('Agree')",
            "button[aria-label='Close']",
            "button[aria-label='close']",
        ]
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    page.wait_for_timeout(300)
                    break
            except Exception:
                continue


def _run_subprocess_entry() -> int:
    """Entry point for the subprocess-backed stateful scrape."""
    payload = json.loads(sys.stdin.read() or "{}")
    if not isinstance(payload, dict):
        print("{}")
        return 1

    starting_url = str(payload.get("starting_url", "")).strip()
    timeout_ms = int(payload.get("timeout_ms", 30_000))
    raw_urls = payload.get("urls", [])
    urls = [str(url).strip() for url in raw_urls if str(url).strip()] if isinstance(raw_urls, list) else []

    scraper = StatefulPageScraper(starting_url=starting_url, timeout_ms=timeout_ms)
    output = scraper._scrape_urls_sync(urls)
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    if "--stateful-scrape" in sys.argv:
        raise SystemExit(_run_subprocess_entry())
