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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from src.form_detector import (
    ADD_TO_CART_SELECTORS,
    CONTINUE_SHOPPING_SELECTORS,
    PRODUCT_SELECTORS,
)
from src.journey_auth_detector import (
    detect_auth_redirect,
    detect_captcha,
    detect_mfa,
    detect_sso,
)
from src.placeholder_resolver import PlaceholderResolver
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


@dataclass
class CredentialProfile:
    """User-defined credentials for authenticated journey scraping.

    Stored in session state only — never persisted to disk.
    """

    label: str
    username: str
    password: str


@dataclass
class JourneyResult:
    """Result of executing a journey through authenticated pages."""

    success: bool
    captured_pages: dict[str, list[dict[str, Any]]]  # url -> elements
    failed_steps: list[str]  # human-readable descriptions
    error_message: str | None = None  # top-level error (SSO, MFA, CAPTCHA)
    redirected_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary (JSON-friendly)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JourneyResult:
        """Deserialize from a plain dictionary."""
        return cls(
            success=bool(data.get("success", False)),
            captured_pages=data.get("captured_pages", {}),
            failed_steps=data.get("failed_steps", []),
            error_message=data.get("error_message"),
            redirected_urls=data.get("redirected_urls", []),
        )


def _substitute_templates(text: str, credential_profile: CredentialProfile | None) -> str:
    """Replace {{username}} and {{password}} placeholders with credential values."""
    if credential_profile is None:
        return text
    result = text.replace("{{username}}", credential_profile.username)
    result = result.replace("{{password}}", credential_profile.password)
    return result


# ───────────────────────────────────────────────────────────────
# _execute_journey_sync  (runs inside a subprocess)
# ───────────────────────────────────────────────────────────────


def _execute_journey_sync(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
    """Execute journey steps in a single Playwright browser session.

    Checks for auth redirects, SSO, MFA, and CAPTCHA — returns explicit errors.
    """
    captured_pages: dict[str, list[dict[str, Any]]] = {}
    failed_steps: list[str] = []
    redirected_urls: list[str] = []
    error_message: str | None = None

    # Determine base domain for SSO detection
    base_domain: str = ""
    if starting_url:
        base_domain = urlparse(starting_url).netloc

    scraper = JourneyScraper(
        starting_url=starting_url or "",
        timeout_ms=timeout_ms,
        headless=True,
    )
    html_scraper = PageScraper(timeout_ms=timeout_ms)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            # Navigate to starting URL if provided
            if starting_url:
                page.goto(starting_url, wait_until="networkidle", timeout=timeout_ms)
                JourneyScraper._dismiss_consent_overlays(page)
                base_domain = urlparse(page.url).netloc

            current_url: str = page.url

            for step_index, step in enumerate(journey_steps):
                if error_message:
                    # Journey stopped by detection — record remaining as failed
                    failed_steps.append(f"Step {step_index + 1} ({step.action}): journey stopped — {error_message}")
                    continue

                step_description = step.description or f"{step.action} step"

                try:
                    if step.action == "goto" or step.action == "navigate":
                        target_url = step.url or ""
                        if not target_url:
                            failed_steps.append(f"Step {step_index + 1}: goto/navigate without url")
                            continue

                        page.goto(target_url, wait_until="networkidle", timeout=step.timeout_ms)
                        JourneyScraper._dismiss_consent_overlays(page)

                        current_url = page.url

                        # Update base_domain from first navigation
                        if not base_domain:
                            base_domain = urlparse(current_url).netloc

                        # Auth redirect detection
                        page_title = page.title()
                        h1_text = ""
                        try:
                            h1_el = page.locator("h1").first
                            if h1_el.count() > 0:
                                h1_text = h1_el.inner_text()
                        except Exception:
                            pass

                        if detect_auth_redirect(current_url, target_url, page_title, h1_text):
                            failed_steps.append(
                                f"Step {step_index + 1}: Page redirected to login — add a login step before this page"
                            )
                            if current_url not in redirected_urls:
                                redirected_urls.append(current_url)

                        # SSO detection
                        if base_domain and detect_sso(base_domain, current_url):
                            error_message = (
                                "SSO/OAuth redirect detected — automated login not supported for this provider"
                            )
                            failed_steps.append(f"Step {step_index + 1}: {error_message}")

                        # CAPTCHA detection
                        html = page.content()
                        if detect_captcha(html):
                            error_message = "CAPTCHA detected — automated login not supported"
                            failed_steps.append(f"Step {step_index + 1}: {error_message}")

                        # MFA detection
                        if detect_mfa(html):
                            error_message = "MFA prompt detected — automated login not supported"
                            failed_steps.append(f"Step {step_index + 1}: {error_message}")

                    elif step.action == "click":
                        selector = step.selector
                        text = step.text
                        if not selector and text:
                            # Try text-based click
                            try:
                                page.get_by_text(text, exact=False).first.click(timeout=step.timeout_ms)
                            except Exception:
                                failed_steps.append(f"Step {step_index + 1}: Could not click text '{text}'")
                            continue
                        if not selector:
                            failed_steps.append(f"Step {step_index + 1}: click without selector or text")
                            continue
                        try:
                            scraper._click_selector(page, selector, step.timeout_ms)
                        except Exception as e:
                            failed_steps.append(f"Step {step_index + 1}: click '{selector}' failed — {e}")

                    elif step.action == "fill":
                        selector = step.selector
                        if not selector:
                            failed_steps.append(f"Step {step_index + 1}: fill without selector")
                            continue
                        fill_text = step.text or ""
                        fill_text = _substitute_templates(fill_text, credential_profile)
                        try:
                            scraper._fill_selector(page, selector, fill_text, step.timeout_ms)
                        except Exception as e:
                            failed_steps.append(f"Step {step_index + 1}: fill '{selector}' failed — {e}")

                    elif step.action == "submit":
                        # Submit — click submit button
                        submit_selectors = [
                            "input[type='submit']",
                            "button[type='submit']",
                            "button:has-text('Submit')",
                            "button:has-text('submit')",
                        ]
                        clicked = False
                        for sel in submit_selectors:
                            try:
                                loc = page.locator(sel).first
                                if loc.count() > 0:
                                    loc.click(timeout=step.timeout_ms)
                                    clicked = True
                                    break
                            except Exception:
                                continue
                        if not clicked:
                            failed_steps.append(f"Step {step_index + 1}: submit — no submit button found")

                    elif step.action == "capture":
                        html = page.content()
                        elements = html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001
                        captured_pages[current_url] = elements

                    elif step.action == "wait":
                        wait_desc = step.description or "1.0"
                        try:
                            wait_seconds = float(wait_desc)
                        except ValueError:
                            wait_seconds = 1.0
                        page.wait_for_timeout(int(wait_seconds * 1000))
                        # Also wait for selector if provided
                        if step.selector:
                            try:
                                page.wait_for_selector(step.selector, timeout=step.timeout_ms)
                            except Exception:
                                pass

                except Exception as e:
                    failed_steps.append(f"Step {step_index + 1} ({step_description}): {e}")

                current_url = page.url

        finally:
            context.close()
            browser.close()

    success = error_message is None and not failed_steps
    return JourneyResult(
        success=success,
        captured_pages=captured_pages,
        failed_steps=failed_steps,
        error_message=error_message,
        redirected_urls=redirected_urls,
    )


# ───────────────────────────────────────────────────────────────
# execute_journey  (public API — subprocess pattern)
# ───────────────────────────────────────────────────────────────


def execute_journey(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
    """Execute a journey in a subprocess (avoids ProactorEventLoop on Windows).

    Serialises steps to JSON, spawns subprocess, deserialises JourneyResult.
    """
    # Serialize inputs
    steps_data = [asdict(s) for s in journey_steps]
    credential_data = asdict(credential_profile) if credential_profile else None

    payload = {
        "journey_steps": steps_data,
        "credential_profile": credential_data,
        "timeout_ms": timeout_ms,
        "starting_url": starting_url,
    }

    subprocess_path = str(Path(__file__).resolve())
    completed = subprocess.run(
        [sys.executable, subprocess_path, "--execute-journey"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=max(120, timeout_ms // 1000 * max(1, len(journey_steps))),
    )

    if completed.stderr:
        print(completed.stderr, flush=True, file=sys.stderr)

    if completed.returncode != 0:
        return JourneyResult(
            success=False,
            captured_pages={},
            failed_steps=["Subprocess failed to execute journey"],
            error_message=completed.stderr.strip() if completed.stderr else "Subprocess error",
        )

    try:
        data = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return JourneyResult(
            success=False,
            captured_pages={},
            failed_steps=["Failed to parse subprocess output"],
            error_message="Invalid JSON from subprocess",
        )

    if not isinstance(data, dict):
        return JourneyResult(
            success=False,
            captured_pages={},
            failed_steps=["Subprocess returned unexpected output"],
        )

    return JourneyResult.from_dict(data)


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
        credential_profile: CredentialProfile | None = None,
    ) -> None:
        self.starting_url = starting_url.strip()
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.base_backoff_ms = base_backoff_ms
        self.headless = headless
        self._credential_profile = credential_profile
        self._html_scraper = PageScraper(timeout_ms=timeout_ms)
        self._resolver = PlaceholderResolver()

    def _debug(self, message: str) -> None:
        """Print debug message to stderr if logging is enabled."""
        if os.getenv("PIPELINE_DEBUG", "").strip() == "1":
            print(f"[journey_discovery] {message}", flush=True, file=sys.stderr)

    async def scrape_journey(
        self,
        steps: list[JourneyStep],
        *,
        credential_profile: CredentialProfile | None = None,
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

        # Use the credential_profile passed at call-site, or fall back to instance-level
        effective_profile = credential_profile or self._credential_profile
        return await asyncio.to_thread(self._scrape_journey_via_subprocess, cleaned, effective_profile)

    def _scrape_journey_via_subprocess(
        self,
        steps: list[JourneyStep],
        credential_profile: CredentialProfile | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
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
            "credential_profile": asdict(credential_profile) if credential_profile else None,
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

        # Surface subprocess stderr for real-time debugging
        if completed.stderr:
            print(completed.stderr, flush=True, file=sys.stderr)

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
                    self._debug(f"Navigating to starting URL: {self.starting_url}")
                    page.goto(self.starting_url, wait_until="networkidle", timeout=self.timeout_ms)
                    self._dismiss_consent_overlays(page)
                    # Scrape the starting page so elements are available for placeholder resolution.
                    # Without this, pages like login forms are never captured since auto-scrape
                    # only triggers after explicit navigate steps (line 244), not initial load.
                    elements = self._scrape_current_page(page, current_url)
                    output[current_url] = elements

                for step_index, step in enumerate(steps):
                    last_error: Exception | None = None
                    self._debug(f"Step {step_index + 1}/{len(steps)}: {step.action} '{step.description}'")

                    for attempt in range(1, self.max_retries + 1):
                        try:
                            if step.action == "navigate" and step.url:
                                current_url = self._navigate_to(page, step.url, step.timeout_ms)

                            elif step.action == "click":
                                selector = step.selector
                                if not selector and step.description:
                                    selector = self._discover_selector(page, step.action, step.description)
                                if selector:
                                    self._click_selector(page, selector, step.timeout_ms)

                            elif step.action == "fill":
                                selector = step.selector
                                if not selector and step.description:
                                    selector = self._discover_selector(page, step.action, step.description)
                                if selector and step.text:
                                    self._fill_selector(page, selector, step.text, step.timeout_ms)

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

                            current_url = page.url
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

    def _discover_selector(self, page: Any, action: str, description: str) -> str | None:
        """Find the best selector for a description on the current live page."""
        # Ensure the page is stable and rendered
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001

        self._debug(f"Scraped {len(elements)} elements for discovery of '{description}'")

        # We don't have LLM context here, so we use rank_candidates directly
        ranked = self._resolver.rank_candidates(action, description, elements)
        if not ranked:
            return None

        # Pick top candidate and build a robust locator
        _score, element = ranked[0]
        robust = self._resolver._build_robust_locator(element)  # noqa: SLF001
        return robust or element.get("selector")

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
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1000)  # Extra wait for stable DOM
            self._dismiss_consent_overlays(page)
            return page.url
        return full_url

    def _click_selector(self, page: Any, selector: str, timeout_ms: int) -> None:
        """Click an element by selector, with scroll-into-view and retry."""
        self._debug(f"Attempting to click selector: {selector}")
        locator = page.locator(selector).first
        if locator.count() == 0:
            self._debug(f"Click failed: Locator {selector} not found on page.")
            return

        try:
            locator.scroll_into_view_if_needed(timeout=min(2000, timeout_ms))
        except Exception as e:
            self._debug(f"Scroll into view failed: {e}")

        try:
            locator.click(timeout=min(5000, timeout_ms))
            self._debug(f"Clicked successfully: {selector}")
        except Exception as e:
            self._debug(f"Click exception: {e}")
            raise
        page.wait_for_timeout(500)  # Brief wait for page transition

    def _fill_selector(self, page: Any, selector: str, text: str, timeout_ms: int) -> None:
        """Fill an input element by selector."""
        self._debug(f"Attempting to fill selector: {selector} with text: {text}")
        locator = page.locator(selector).first
        if locator.count() == 0:
            self._debug(f"Fill failed: Locator {selector} not found on page.")
            return
        try:
            locator.fill(text)
            self._debug(f"Filled successfully: {selector}")
        except Exception as e:
            self._debug(f"Fill exception: {e}")
            raise

    def _scrape_current_page(self, page: Any, url: str) -> list[dict[str, Any]]:
        """Scrape elements from the current page state."""
        html = page.content()
        return self._html_scraper._extract_elements_from_html(html, base_url=url)  # noqa: SLF001

    @staticmethod
    def _dismiss_consent_overlays(page: Any) -> None:
        """Delegate to central consent dismissal utility."""
        from src.browser_utils import dismiss_consent_overlays

        dismiss_consent_overlays(page)  # type: ignore[arg-type]


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

    # Class-level selector constants (re-exported from form_detector for compatibility)
    PRODUCT_SELECTORS: list[str] = PRODUCT_SELECTORS
    ADD_TO_CART_SELECTORS: list[str] = ADD_TO_CART_SELECTORS
    CONTINUE_SHOPPING_SELECTORS: list[str] = CONTINUE_SHOPPING_SELECTORS

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
                selector=PRODUCT_SELECTORS[0],  # Use first matching selector
                description="select a product",
            )
        )

        # Step 3: Click "Add to cart"
        steps.append(
            JourneyStep(
                action="click",
                selector=ADD_TO_CART_SELECTORS[0],
                description="add product to cart",
            )
        )

        # Step 4: Dismiss confirmation modal
        steps.append(
            JourneyStep(
                action="click",
                selector=CONTINUE_SHOPPING_SELECTORS[0],
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


def _run_execute_journey_entry() -> int:
    """Entry point for the subprocess-backed execute_journey."""
    payload = json.loads(sys.stdin.read() or "{}")
    if not isinstance(payload, dict):
        print(
            json.dumps(
                JourneyResult(
                    success=False,
                    captured_pages={},
                    failed_steps=["Invalid payload"],
                    error_message="Invalid JSON payload",
                ).to_dict()
            )
        )
        return 1

    # Reconstruct journey steps
    steps_data = payload.get("journey_steps", [])
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

    # Reconstruct credential profile
    credential_data = payload.get("credential_profile")
    credential_profile: CredentialProfile | None = None
    if credential_data and isinstance(credential_data, dict):
        credential_profile = CredentialProfile(
            label=str(credential_data.get("label", "")),
            username=str(credential_data.get("username", "")),
            password=str(credential_data.get("password", "")),
        )

    timeout_ms = int(payload.get("timeout_ms", 30_000))
    starting_url = payload.get("starting_url")

    result = _execute_journey_sync(
        journey_steps=steps,
        credential_profile=credential_profile,
        timeout_ms=timeout_ms,
        starting_url=starting_url,
    )
    print(json.dumps(result.to_dict()))
    return 0


if __name__ == "__main__":
    if "--journey-scrape" in sys.argv:
        raise SystemExit(_run_subprocess_entry())
    if "--execute-journey" in sys.argv:
        raise SystemExit(_run_execute_journey_entry())
