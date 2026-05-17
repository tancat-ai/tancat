"""Playwright session-backed scraper for stateful pages (e.g., cart/checkout).

This module intentionally launches Playwright inside a dedicated subprocess on
Windows. Streamlit often runs app code in a background thread where Playwright's
browser-launch subprocesses can fail with `NotImplementedError`.
"""

from __future__ import annotations

import asyncio
import json
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from src.accessibility_enricher import AccessibilityEnricher
from src.form_login_utils import attempt_login
from src.journey_scraper import CredentialProfile
from src.scraper import PageScraper


class StatefulPageScraper:
    """Scrape pages using a Playwright browser context with a cart session.

    Supports retry/backoff for transient failures via max_retries and base_backoff_ms parameters.
    """

    def __init__(
        self,
        starting_url: str,
        *,
        timeout_ms: int = 30_000,
        max_retries: int = 2,
        base_backoff_ms: int = 1000,
        credential_profile: CredentialProfile | None = None,
    ) -> None:
        self.starting_url = starting_url.strip()
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.base_backoff_ms = base_backoff_ms
        self._credential_profile = credential_profile
        self._html_scraper = PageScraper(timeout_ms=30000)

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
        from dataclasses import asdict

        payload: dict[str, Any] = {
            "starting_url": self.starting_url,
            "timeout_ms": self.timeout_ms,
            "urls": urls,
        }
        if self._credential_profile is not None:
            payload["credential_profile"] = asdict(self._credential_profile)
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
        """Sync implementation for multi-URL session scrape with retry/backoff support."""
        output: dict[str, list[dict[str, Any]]] = {}

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)

            try:
                self._seed_cart_session(page)
                for url in urls:
                    last_error: Exception | None = None

                    for attempt in range(1, self.max_retries + 1):
                        try:
                            # Wait for network idle to ensure dynamic content (cart items) is loaded
                            page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                            # Extra wait for stable DOM
                            page.wait_for_timeout(1000)
                            html = page.content()
                            result = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001

                            # B-0XX: Capture runtime visibility using Playwright is_visible()
                            result = self._html_scraper._capture_element_visibility(page, result)

                            # B-0XX: CDP accessibility snapshot and enrichment
                            a11y_snapshot = self._capture_a11y_snapshot(context, page)
                            if a11y_snapshot:
                                result = AccessibilityEnricher.enrich(result, a11y_snapshot)

                            output[url] = result
                            last_error = None
                            break
                        except Exception as e:
                            last_error = e
                            if attempt < self.max_retries:
                                backoff = self.base_backoff_ms * (2 ** (attempt - 1)) + random.uniform(0, 100)
                                time.sleep(backoff / 1000.0)

                    # If all retries exhausted and we still have an error, record empty result
                    if last_error is not None and url not in output:
                        output[url] = []
            finally:
                context.close()
                browser.close()

        return output

    @staticmethod
    def _capture_a11y_snapshot(
        context: Any,
        page: Any,
    ) -> dict[str, Any]:
        """Capture accessibility snapshot via CDP.

        Returns an empty dict if CDP is unavailable or returns no nodes,
        matching the PageScraper fallback behaviour.
        """
        a11y_snapshot: dict[str, Any] = {}
        try:
            cdp = context.new_cdp_session(page)
            ax_result = cdp.send("Accessibility.getFullAXTree")
            a11y_snapshot = AccessibilityEnricher._transform_cdp_ax_tree(ax_result.get("nodes", []))
            # CDP session is cleaned up when browser context closes
        except Exception:
            # Graceful fallback — enrichment is additive, missing it doesn't break the pipeline.
            pass
        return a11y_snapshot

    def _seed_cart_session(self, page: Any) -> None:
        """Navigate, login if needed, then try to add one item to cart (best effort)."""
        if not self.starting_url:
            return

        page.goto(self.starting_url, wait_until="domcontentloaded")
        self._dismiss_consent_overlays(page)

        # Detect and handle login forms — many demo sites (saucedemo, etc.) require
        # authentication before showing product/inventory pages.
        attempt_login(page, self._credential_profile)

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
        """Delegate to central consent dismissal utility."""
        from src.browser_utils import dismiss_consent_overlays

        dismiss_consent_overlays(page)  # type: ignore[arg-type]


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

    # Reconstruct credential profile if provided
    credential_profile: CredentialProfile | None = None
    cred_data = payload.get("credential_profile")
    if isinstance(cred_data, dict):
        credential_profile = CredentialProfile(
            label=str(cred_data.get("label", "")),
            username=str(cred_data.get("username", "")),
            password=str(cred_data.get("password", "")),
        )

    scraper = StatefulPageScraper(
        starting_url=starting_url,
        timeout_ms=timeout_ms,
        credential_profile=credential_profile,
    )
    output = scraper._scrape_urls_sync(urls)
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    if "--stateful-scrape" in sys.argv:
        raise SystemExit(_run_subprocess_entry())
