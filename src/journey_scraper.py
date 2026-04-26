"""Journey-aware scraper that follows user interactions step-by-step.

This module scrapes pages by following a user journey (navigate → interact → scrape),
similar to how Playwright's recorder works. It ensures that dynamic elements
(e.g., "Proceed To Checkout" button on a cart page) are visible before scraping.

Key difference from static scraping:
- Static: visits URLs directly, may miss elements that only appear after interaction
- Journey-aware: follows the user's interaction path, ensuring elements are present
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from src.scraper import PageScraper


@dataclass
class JourneyStep:
    """A single action in the scraping journey.

    Attributes:
        action: The action type: "navigate", "click", "fill", "wait", "scrape".
        url: URL to navigate to (for "navigate" action).
        selector: Element selector to interact with (for "click"/"fill" actions).
        text: Text to fill into an input (for "fill" action).
        description: Human-readable description of this step.
        timeout_ms: Custom timeout for this step (default: 30000).
    """

    action: str
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    description: str = ""
    timeout_ms: int = 30_000


@dataclass
class ScrapedStep:
    """Result of scraping at a specific journey step.

    Attributes:
        url: The URL that was scraped.
        elements: The scraped elements at this URL.
        step_index: Which step in the journey this corresponds to.
        step_description: Human-readable description of the journey step.
    """

    url: str
    elements: list[dict[str, Any]]
    step_index: int
    step_description: str = ""


class JourneyScraper:
    """Scrape pages by following a user journey step-by-step.

    This scraper simulates a real user's interaction path:
    1. Navigate to a page
    2. Interact with elements (click, fill)
    3. Navigate to the next page
    4. Scrape elements at each stage

    This ensures that dynamic elements (e.g., cart items, checkout buttons)
    are present in the DOM before scraping.

    Example usage:
        scraper = JourneyScraper(starting_url="https://example.com")
        steps = [
            JourneyStep(action="navigate", url="https://example.com/products"),
            JourneyStep(action="click", selector="[data-product-id]:visible", description="select product"),
            JourneyStep(action="click", selector='button:has-text("Add to cart")', description="add to cart"),
            JourneyStep(action="navigate", url="https://example.com/view_cart"),
            JourneyStep(action="scrape"),  # Cart page now has checkout button
        ]
        results = await scraper.scrape_journey(steps)
    """

    def __init__(
        self,
        starting_url: str,
        *,
        timeout_ms: int = 30_000,
        max_retries: int = 2,
        base_backoff_ms: int = 1000,
        headless: bool = True,
    ) -> None:
        self.starting_url = starting_url.strip()
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.base_backoff_ms = base_backoff_ms
        self.headless = headless
        self._html_scraper = PageScraper(timeout_ms=timeout_ms)

    async def scrape_journey(
        self,
        steps: list[JourneyStep],
    ) -> dict[str, list[dict[str, Any]]]:
        """Follow the journey and return scraped elements per URL.

        Uses a subprocess to avoid Windows asyncio nested loop issues
        when running inside Streamlit's threaded context.

        Args:
            steps: The journey steps to follow.

        Returns:
            Dictionary mapping URL → list of scraped elements.
            Elements from later steps may overwrite earlier elements for the same URL.
        """
        cleaned = [s for s in steps if s and s.action in ("navigate", "click", "fill", "wait", "scrape")]
        if not cleaned:
            return {}

        return await asyncio.to_thread(self._scrape_journey_via_subprocess, cleaned)

    def _scrape_journey_via_subprocess(self, steps: list[JourneyStep]) -> dict[str, list[dict[str, Any]]]:
        """Run the sync Playwright journey in a clean subprocess (avoids Windows nested loop issues)."""
        # Serialize steps to JSON for subprocess
        steps_data = [
            {
                "action": s.action,
                "url": s.url,
                "selector": s.selector,
                "text": s.text,
                "description": s.description,
                "timeout_ms": s.timeout_ms,
            }
            for s in steps
        ]
        payload = {
            "starting_url": self.starting_url,
            "timeout_ms": self.timeout_ms,
            "max_retries": self.max_retries,
            "base_backoff_ms": self.base_backoff_ms,
            "headless": self.headless,
            "steps": steps_data,
        }
        subprocess_path = str(Path(__file__).resolve())
        completed = subprocess.run(
            [sys.executable, subprocess_path, "--journey-scrape"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            timeout=max(120, int(self.timeout_ms / 1000) * max(1, len(steps))),
        )
        if completed.returncode != 0:
            return {}

        try:
            data = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            return {}

        if not isinstance(data, dict):
            return {}

        output: dict[str, list[dict[str, Any]]] = {}
        for url, elements in data.items():
            output[url] = elements if isinstance(elements, list) else []
        return output

    def _scrape_journey_sync(self, steps: list[JourneyStep]) -> dict[str, list[dict[str, Any]]]:
        """Synchronous journey scraping logic (for subprocess entry point)."""
        output: dict[str, list[dict[str, Any]]] = {}
        current_url: str | None = None

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)

            try:
                # Start at the starting URL to establish session
                if self.starting_url:
                    current_url = self.starting_url
                    page.goto(self.starting_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    self._dismiss_consent_overlays(page)

                for step_index, step in enumerate(steps):
                    last_error: Exception | None = None

                    for attempt in range(1, self.max_retries + 1):
                        try:
                            if step.action == "navigate" and step.url:
                                current_url = self._navigate_to(page, step.url, step.timeout_ms)

                            elif step.action == "click" and step.selector:
                                self._click_selector(page, step.selector, step.timeout_ms)

                            elif step.action == "fill" and step.selector and step.text:
                                self._fill_selector(page, step.selector, step.text, step.timeout_ms)

                            elif step.action == "wait":
                                wait_time = (
                                    float(step.description)
                                    if step.description and step.description.replace(".", "").isdigit()
                                    else 1.0
                                )
                                page.wait_for_timeout(int(wait_time * 1000))

                            elif step.action == "scrape" and current_url:
                                elements = self._scrape_current_page(page, current_url)
                                output[current_url] = elements

                            # Auto-scrape after navigation if no explicit scrape step
                            if step.action == "navigate" and current_url:
                                elements = self._scrape_current_page(page, current_url)
                                output[current_url] = elements

                            last_error = None
                            break

                        except Exception as e:
                            last_error = e
                            if attempt < self.max_retries:
                                backoff = self.base_backoff_ms * (2 ** (attempt - 1)) + random.uniform(0, 100)
                                time.sleep(backoff / 1000.0)

                    if last_error is not None:
                        if os.getenv("PIPELINE_DEBUG", "").strip() == "1":
                            print(f"[journey_scraper] Step {step_index} ({step.description}): {last_error}", flush=True)

            finally:
                context.close()
                browser.close()

        return output

    def _navigate_to(self, page: Any, url: str, timeout_ms: int) -> str:
        """Navigate to a URL and return the final URL.

        Handles relative URLs by joining with the current origin.
        """
        full_url = url
        if url.startswith("/"):
            # Relative URL — join with current origin
            from urllib.parse import urljoin

            full_url = urljoin(page.url, url)

        response = page.goto(full_url, wait_until="networkidle", timeout=timeout_ms)
        if response:
            page.wait_for_timeout(1000)  # Extra wait for stable DOM
            self._dismiss_consent_overlays(page)
            return page.url
        return full_url

    def _click_selector(self, page: Any, selector: str, timeout_ms: int) -> None:
        """Click an element by selector, with scroll-into-view and retry."""
        locator = page.locator(selector).first
        if locator.count() == 0:
            return

        try:
            locator.scroll_into_view_if_needed(timeout=min(2000, timeout_ms))
        except Exception:
            pass

        locator.click(timeout=min(5000, timeout_ms))
        page.wait_for_timeout(500)  # Brief wait for page transition

    def _fill_selector(self, page: Any, selector: str, text: str, timeout_ms: int) -> None:
        """Fill an input element by selector."""
        locator = page.locator(selector).first
        if locator.count() == 0:
            return
        locator.fill(text)

    def _scrape_current_page(self, page: Any, url: str) -> list[dict[str, Any]]:
        """Scrape elements from the current page state."""
        html = page.content()
        return self._html_scraper._extract_elements_from_html(html, base_url=url)  # noqa: SLF001

    @staticmethod
    def _dismiss_consent_overlays(page: Any) -> None:
        """Dismiss common consent/cookie overlay banners."""
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
            ".cc-banner button",
            ".cookie-banner button",
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


class CartSeedingScraper(JourneyScraper):
    """Journey scraper specialized for cart-dependent pages.

    This scraper follows a specific journey to ensure the cart has items
    before scraping cart/checkout pages:
    1. Navigate to products page
    2. Select a product
    3. Add to cart
    4. Dismiss confirmation modal
    5. Navigate to cart page (now has checkout button)

    This is a convenience wrapper around JourneyScraper for the common
    "scrape cart with items" use case.
    """

    # Selectors for finding a product to add to cart
    PRODUCT_SELECTORS = [
        "[data-product-id]:visible",
        'a:has-text("Shop Now")',
        'a:has-text("View Product")',
        'a[href*="product_detail"]',
        'a[href*="product"]',
        ".product-card a",
        "div[class*='product'] a",
    ]

    # Selectors for the "Add to Cart" button on the product page
    ADD_TO_CART_SELECTORS = [
        'button:has-text("Add to cart")',
        'a:has-text("Add to cart")',
        'input[type="submit"][value*="cart"]',
        ".add-to-cart",
        'button:has-text("Buy")',
    ]

    # Selectors for the "Continue Shopping" modal button
    CONTINUE_SHOPPING_SELECTORS = [
        'button:has-text("Continue Shopping")',
        'button:has-text("Close")',
        'button[aria-label="Close"]',
        ".close-modal",
        ".modal-footer button",
        'a:has-text("Continue Shopping")',
    ]

    def __init__(
        self,
        starting_url: str,
        products_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the cart seeding scraper.

        Args:
            starting_url: The home page URL (used to establish session).
            products_url: Optional explicit products page URL. If not provided,
                         derived from starting_url by appending "/products".
            **kwargs: Additional arguments passed to JourneyScraper.
        """
        super().__init__(starting_url, **kwargs)
        self.products_url = products_url or self._derive_products_url(starting_url)

    @staticmethod
    def _derive_products_url(home_url: str) -> str:
        """Derive the products page URL from the home page URL.

        Example: https://automationexercise.com/ → https://automationexercise.com/products
        """
        from urllib.parse import urljoin

        return urljoin(home_url, "/products")

    async def scrape_cart_pages(
        self,
        cart_urls: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Scrape cart/checkout pages with items already in the cart.

        This method:
        1. Seeds the cart by adding an item (via the products page)
        2. Then scrapes each target URL (cart, checkout, etc.)

        Args:
            cart_urls: URLs to scrape (e.g., [/view_cart, /checkout]).

        Returns:
            Dictionary mapping URL → list of scraped elements.
        """
        steps: list[JourneyStep] = []

        # Step 1: Navigate to products page
        steps.append(
            JourneyStep(
                action="navigate",
                url=self.products_url,
                description="navigate to products page",
            )
        )

        # Step 2: Click on a product
        steps.append(
            JourneyStep(
                action="click",
                selector=self.PRODUCT_SELECTORS[0],  # Use first matching selector
                description="select a product",
            )
        )

        # Step 3: Click "Add to cart"
        steps.append(
            JourneyStep(
                action="click",
                selector=self.ADD_TO_CART_SELECTORS[0],
                description="add product to cart",
            )
        )

        # Step 4: Dismiss confirmation modal
        steps.append(
            JourneyStep(
                action="click",
                selector=self.CONTINUE_SHOPPING_SELECTORS[0],
                description="dismiss confirmation modal",
            )
        )

        # Step 5: Wait for modal to disappear
        steps.append(
            JourneyStep(
                action="wait",
                description="1.0",
            )
        )

        # Step 6+: Navigate to and scrape each target URL
        for cart_url in cart_urls:
            full_url = self._ensure_full_url(cart_url)
            steps.append(
                JourneyStep(
                    action="navigate",
                    url=full_url,
                    description=f"navigate to {full_url}",
                )
            )

        return await self.scrape_journey(steps)

    @staticmethod
    def _ensure_full_url(url: str) -> str:
        """Ensure the URL is absolute.

        If the URL is relative, it will be made absolute during navigation
        by the JourneyScraper.
        """
        if url.startswith(("http://", "https://")):
            return url
        return url  # Relative URLs are handled by _navigate_to


def _run_subprocess_entry() -> int:
    """Entry point for the subprocess-backed journey scrape."""
    payload = json.loads(sys.stdin.read() or "{}")
    if not isinstance(payload, dict):
        print("{}")
        return 1

    starting_url = str(payload.get("starting_url", "")).strip()
    timeout_ms = int(payload.get("timeout_ms", 30_000))
    max_retries = int(payload.get("max_retries", 2))
    base_backoff_ms = int(payload.get("base_backoff_ms", 1000))
    headless = payload.get("headless", True)
    steps_data = payload.get("steps", [])

    # Reconstruct JourneyStep objects from JSON
    steps: list[JourneyStep] = []
    for s in steps_data:
        if not isinstance(s, dict):
            continue
        steps.append(
            JourneyStep(
                action=str(s.get("action", "")),
                url=str(s["url"]) if s.get("url") else None,
                selector=str(s["selector"]) if s.get("selector") else None,
                text=str(s["text"]) if s.get("text") else None,
                description=str(s.get("description", "")),
                timeout_ms=int(s.get("timeout_ms", 30_000)),
            )
        )

    scraper = JourneyScraper(
        starting_url=starting_url,
        timeout_ms=timeout_ms,
        max_retries=max_retries,
        base_backoff_ms=base_backoff_ms,
        headless=bool(headless),
    )
    output = scraper._scrape_journey_sync(steps)
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    if "--journey-scrape" in sys.argv:
        raise SystemExit(_run_subprocess_entry())
