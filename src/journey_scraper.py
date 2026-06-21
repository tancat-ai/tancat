"""Journey-aware scraper that follows user interactions step-by-step.

This module scrapes pages by following a user journey (navigate → interact → scrape),
similar to how Playwright's recorder works. It ensures that dynamic elements
(e.g., "Proceed To Checkout" button on a cart page) are visible before scraping.

Key difference from static scraping:
- Static: visits URLs directly, may miss elements that only appear after interaction
- Journey-aware: follows the user's interaction path, ensuring elements are present

Data models (JourneyStep, ScrapedStep, CredentialProfile, JourneyResult) have been
moved to ``src/journey_models.py``. The authenticated journey executor
(``execute_journey``) has been moved to ``src/journey_executor.py``.
Re-exports are provided below for backward compatibility.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from src.accessibility_enricher import AccessibilityEnricher
from src.form_detector import (
    ADD_TO_CART_SELECTORS,
    CONTINUE_SHOPPING_SELECTORS,
    PRODUCT_SELECTORS,
)

# ─── Backward-compat re-exports ────────────────────────────────
# Importers that used ``from src.journey_scraper import ...`` continue to work.
from src.journey_executor import execute_journey  # noqa: F401
from src.journey_models import (
    CredentialProfile,
    JourneyResult,
    JourneyStep,
    ScrapedStep,
    substitute_templates,
)
from src.locator_builder import build_robust_locator
from src.placeholder_resolver import PlaceholderResolver
from src.placeholder_scorers import PlaceholderScorer
from src.scraper import PageScraper

# Legacy alias — old test files import _substitute_templates
_substitute_templates = substitute_templates  # noqa: PLW1508

__all__ = [
    "CartSeedingScraper",
    "CredentialProfile",
    "JourneyResult",
    "JourneyScraper",
    "JourneyStep",
    "ScrapedStep",
    "execute_journey",
]

# ────────────────────────────────────────────────────────────────
# B-0XX: Enrichment helpers for consistent scrape quality
# Reused across JourneyScraper._scrape_current_page and
# JourneyScraper._discover_selector to match PageScraper enrichment pipeline.
# ────────────────────────────────────────────────────────────────


def _capture_element_visibility_sync(
    page: Any,
    elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check runtime visibility of each scraped element using Playwright is_visible()."""
    for elem in elements:
        selector = elem.get("selector")
        if not selector:
            continue
        try:
            loc = page.locator(selector).first
            elem["is_visible"] = loc.is_visible()
        except Exception:
            pass  # Keep default is_visible value on lookup failure
    return elements


def _capture_a11y_snapshot_sync(
    context: Any,
    page: Any,
) -> dict[str, Any] | None:
    """Capture accessibility snapshot via CDP. Returns None if unavailable."""
    try:
        cdp_session = context.new_cdp_session(page)
    except Exception:
        return None

    a11y_snapshot: dict[str, Any] = {"nodes": []}
    try:
        tree_response = cdp_session.send("Accessibility.getFullAXTree")
        a11y_snapshot["nodes"] = tree_response.get("nodes", []) if isinstance(tree_response, dict) else []
    except Exception:
        pass  # Return empty nodes list on CDP failure

    try:
        cdp_session.detach()
    except Exception:
        pass

    return a11y_snapshot


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
        # Stores URL → elements mapping after scraping completes.
        # Populated by _scrape_journey_via_subprocess and _scrape_journey_sync.
        self._captured_pages: dict[str, list[dict[str, Any]]] = {}
        # Context log for tracking locator failures and skipped steps.
        self._context_log: list[dict[str, Any]] = []

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
        cleaned = [s for s in steps if s and s.action in ("navigate", "click", "fill", "wait", "scrape", "capture")]
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
        import subprocess

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
        self._captured_pages = output
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
                    elements = self._scrape_current_page(page, current_url, context)  # B-0XX: pass context
                    output[current_url] = elements

                for step_index, step in enumerate(steps):
                    last_error: Exception | None = None
                    self._debug(f"Step {step_index + 1}/{len(steps)}: {step.action} '{step.description}'")

                    for attempt in range(1, self.max_retries + 1):
                        try:
                            if step.action == "navigate" and step.url:
                                current_url = self._navigate_to(page, step.url, step.timeout_ms)

                            elif step.action == "click":
                                # Dismiss transient overlays (ads, consent) before every click
                                # to prevent pointer-event interception from dynamically loaded ads.
                                self._dismiss_consent_overlays(page)

                                selector = step.selector
                                if not selector and step.description:
                                    selector = self._discover_selector(page, step.action, step.description)
                                    if selector is None:
                                        # Retry with relaxed criteria
                                        selector = self._discover_selector_relaxed(page, step.action, step.description)
                                        if selector is not None:
                                            self._context_log.append(
                                                {
                                                    "event": "locator_relaxed_fallback",
                                                    "step": step_index,
                                                    "action": step.action,
                                                    "description": step.description,
                                                    "selector": selector,
                                                }
                                            )
                                        else:
                                            self._context_log.append(
                                                {
                                                    "event": "step_skipped",
                                                    "step": step_index,
                                                    "reason": "locator_not_found_even_relaxed",
                                                    "action": step.action,
                                                    "description": step.description,
                                                    "page_url": page.url,
                                                }
                                            )
                                if selector:
                                    self._click_selector(page, selector, step.timeout_ms)

                            elif step.action == "fill":
                                selector = step.selector
                                if not selector and step.description:
                                    selector = self._discover_selector(page, step.action, step.description)
                                    if selector is None:
                                        # Retry with relaxed criteria
                                        selector = self._discover_selector_relaxed(page, step.action, step.description)
                                        if selector is not None:
                                            self._context_log.append(
                                                {
                                                    "event": "locator_relaxed_fallback",
                                                    "step": step_index,
                                                    "action": step.action,
                                                    "description": step.description,
                                                    "selector": selector,
                                                }
                                            )
                                        else:
                                            self._context_log.append(
                                                {
                                                    "event": "step_skipped",
                                                    "step": step_index,
                                                    "reason": "locator_not_found_even_relaxed",
                                                    "action": step.action,
                                                    "description": step.description,
                                                    "page_url": page.url,
                                                }
                                            )
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
                                elements = self._scrape_current_page(  # B-0XX: pass context
                                    page, current_url, context
                                )
                                output[current_url] = elements

                            elif step.action == "capture" and current_url:
                                # Transient capture — skip visibility enrichment so that
                                # popups/modals that auto-dismiss are not penalized.
                                html = page.content()
                                elements = self._html_scraper._extract_elements_from_html(html, base_url=current_url)  # noqa: SLF001
                                try:
                                    a11y_snapshot = _capture_a11y_snapshot_sync(context, page)
                                    if a11y_snapshot is not None:
                                        elements = AccessibilityEnricher.enrich(elements, a11y_snapshot)  # type: ignore[arg-type]
                                except Exception:
                                    pass
                                output[current_url] = elements

                            # Auto-scrape after navigation if no explicit scrape step
                            if step.action == "navigate" and current_url:
                                elements = self._scrape_current_page(  # B-0XX: pass context
                                    page, current_url, context
                                )
                                output[current_url] = elements

                            # Detect URL changes after click actions (clicks that cause navigation)
                            # and auto-scrape the new page so elements are available for resolution.
                            new_url = page.url
                            if step.action == "click" and new_url != current_url and current_url:
                                self._debug(f"Click caused navigation: {current_url} -> {new_url}")
                                elements = self._scrape_current_page(  # B-0XX: pass context
                                    page, new_url, context
                                )
                                output[new_url] = elements

                            current_url = new_url
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

        self._captured_pages = output
        return output

    def get_pages_visited(self) -> list[str]:
        """Return unique URLs visited during the journey.

        Extracts page URLs from the captured output dictionary keys.
        This is the authoritative list of pages discovered organically
        by the journey scraper, replacing the need for PAGES_NEEDED
        pre-declaration.
        """
        return (
            list(dict.fromkeys(url for url in self._captured_pages if url)) if hasattr(self, "_captured_pages") else []
        )

    # ─── Diagnostic methods (spec: journey_scraper_silent_failure) ───

    def get_skipped_steps(self) -> list[dict]:
        """Return steps that were skipped during the journey."""
        return [e for e in self._context_log if e.get("event") == "step_skipped"]

    def get_locator_warnings(self) -> list[dict]:
        """Return locator-not-found events from the context log."""
        return [e for e in self._context_log if e.get("event") == "locator_not_found"]

    @staticmethod
    def _list_available_elements(page: Any, limit: int = 10) -> list[dict]:
        """List clickable elements on the page for diagnostic purposes."""
        elements: list[dict] = []
        for el in page.query_selector_all("a, button, input, [role=button], [role=link]")[:limit]:
            elements.append(
                {
                    "tag": el.evaluate("el => el.tagName"),
                    "text": (el.evaluate("el => el.textContent?.trim()") or "")[:50],
                    "id": el.evaluate("el => el.id"),
                    "class": (el.evaluate("el => el.className?.split(' ')[0]") or ""),
                }
            )
        return elements

    def _discover_selector_relaxed(self, page: Any, action: str, description: str) -> str | None:
        """Find a selector using relaxed matching criteria.

        Used as a fallback when strict _discover_selector returns None.
        Relaxes: exact/contains match -> substring match, requires high confidence -> any match.
        """
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001

        norm_desc = re.sub(r"[^\w\s]", " ", description).lower().split()
        if not norm_desc:
            return None

        # Substring match: any element whose text contains *any* keyword from the description
        for element in elements:
            raw = (element.get("accessible_name") or element.get("aria_label") or element.get("text", "")).strip()
            norm_text = re.sub(r"[^\x00-\x7f]", "", raw).strip().lower()
            if len(norm_text) < 2:
                continue
            # Match if at least one keyword appears in the element text
            if any(kw in norm_text for kw in norm_desc if len(kw) >= 2):
                robust = build_robust_locator(element)
                if robust:
                    return robust
                sel = element.get("selector")
                if sel:
                    return sel

        return None

    def _discover_selector(self, page: Any, action: str, description: str) -> str | None:
        """Find the best selector for a description on the current live page.

        Uses PlaceholderScorer.compute_element_score() (same engine as
        PlaceholderOrchestrator) to rank candidates. Falls back to LLM-based
        SemanticCandidateRanker when no element passes scoring.

        B-015: Unified ranking pipeline — discovery and resolution share scoring logic.
        """
        # Ensure the page is stable and rendered
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001

        # B-0XX: Apply enrichment for better candidate quality in selector discovery
        try:
            elements = _capture_element_visibility_sync(page, elements)
        except Exception:
            pass  # Additive — continue with unenriched on failure

        self._debug(f"Scraped {len(elements)} elements for discovery of '{description}'")

        # Stage 1: Score all candidates with PlaceholderScorer (unified scoring)
        best_element: dict[str, Any] | None = None
        best_score: float = -1

        for element in elements:
            selector = element.get("selector", "")
            score = PlaceholderScorer.compute_element_score(
                action=action,
                description=description,
                element=element,
                selector=selector,
                match_threshold=0,  # Accept all in discovery phase; pick highest
            )
            if score is not None and score > best_score:
                best_score = score
                best_element = element

        if best_element is not None:
            robust = build_robust_locator(best_element)
            if robust or best_element.get("selector"):
                self._debug(
                    f"Selected '{robust or best_element.get('selector')}' (score={best_score}) for '{description}'"
                )
                return robust or best_element.get("selector")

        # Stage 2: LLM-based fallback via PlaceholderResolver.rank_candidates
        ranked = self._resolver.rank_candidates(action, description, elements)
        if not ranked:
            self._context_log.append(
                {
                    "event": "locator_not_found",
                    "action": action,
                    "description": description,
                    "page_url": page.url,
                    "best_candidate_score": 0,
                    "available_elements": self._list_available_elements(page),
                }
            )
            return None

        # Pick top candidate and build a robust locator
        _score, element = ranked[0]
        robust = build_robust_locator(element)
        if robust is None and not element.get("selector"):
            self._context_log.append(
                {
                    "event": "locator_not_found",
                    "action": action,
                    "description": description,
                    "page_url": page.url,
                    "best_candidate_score": _score,
                    "available_elements": self._list_available_elements(page),
                }
            )
            return None
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

    def _scrape_current_page(self, page: Any, url: str, context: Any | None = None) -> list[dict[str, Any]]:
        """Scrape elements from the current page state.

        Args:
            page: Live Playwright page object.
            url: Current page URL for base_url in extraction.
            context: Optional browser context for CDP a11y snapshot (B-0XX).
        """
        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=url)  # noqa: SLF001

        # B-0XX: Apply visibility + a11y enrichment for consistent scrape quality
        try:
            enriched = _capture_element_visibility_sync(page, elements)
            if context is not None:
                a11y_snapshot = _capture_a11y_snapshot_sync(context, page)
                if a11y_snapshot is not None:
                    enriched = AccessibilityEnricher.enrich(enriched, a11y_snapshot)  # type: ignore[arg-type]
            return enriched
        except Exception:
            # Enrichment is additive — fall back to unenriched elements on failure
            pass

        return elements

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
        2. Captures the confirmation popup state (for resolver to find)
        3. Then scrapes each target URL (cart, checkout, etc.)

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

        # Step 3b: CAPTURE confirmation popup state BEFORE dismissing it.
        # This allows the resolver to find elements like "Added confirmation popup"
        steps.append(
            JourneyStep(
                action="capture",
                description="capture confirmation popup state",
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


if __name__ == "__main__":
    if "--journey-scrape" in sys.argv:
        raise SystemExit(_run_subprocess_entry())
