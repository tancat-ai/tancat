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
CartSeedingScraper has been moved to ``src/cart_seeding_scraper.py``.
Enrichment helpers to ``src/journey_enrichment.py``.
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
from src.form_login_utils import attempt_login
from src.journey_enrichment import (
    capture_a11y_snapshot_sync,
    capture_element_visibility_sync,
)
from src.journey_executor import execute_journey  # noqa: F401
from src.journey_models import (
    CredentialProfile,
    JourneyResult,
    JourneyStep,
    ObservedStep,
    ObservedTrail,
    ScrapedStep,
    substitute_templates,
)
from src.locator_builder import build_robust_locator
from src.placeholder_resolver import PlaceholderResolver
from src.placeholder_scorers import PlaceholderScorer
from src.scraper import PageScraper
from src.url_guard import UrlGuard

# Legacy alias — old test files import _substitute_templates
_substitute_templates = substitute_templates  # noqa: PLW1508

__all__ = [
    "CredentialProfile",
    "JourneyResult",
    "JourneyScraper",
    "JourneyStep",
    "ObservedStep",
    "ObservedTrail",
    "ScrapedStep",
    "execute_journey",
]

# ─── Legacy private aliases (internal callers may reference the old names) ───
_capture_element_visibility_sync = capture_element_visibility_sync  # noqa: PLW1508
_capture_a11y_snapshot_sync = capture_a11y_snapshot_sync  # noqa: PLW1508


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
        # AI-052: typed observed transition trail — factual page.url records,
        # captured by _scrape_journey_sync and read via get_observed_trail().
        self._observed_trail: ObservedTrail = ObservedTrail()

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
        trail_steps: list[ObservedStep] = []
        for key, value in data.items():
            if key == "__trail__":
                if isinstance(value, dict):
                    trail_steps = [ObservedStep(**s) for s in value.get("steps", []) if isinstance(s, dict)]
                continue
            output[key] = value if isinstance(value, list) else []
        self._captured_pages = output
        self._observed_trail = ObservedTrail(steps=trail_steps)
        return output

    def _scrape_journey_sync(
        self,
        steps: list[JourneyStep],
        *,
        _observed_trail_out: list[ObservedStep] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Synchronous journey scraping logic (for subprocess entry point).

        AI-052: every step appends a factual :class:`ObservedStep` (from/to
        URLs read from ``page.url``) to the trail. Steps are recorded in
        index order — the first attempt's record is the one kept; later
        retries update the same record in place.
        """
        output: dict[str, list[dict[str, Any]]] = {}
        current_url: str | None = None
        trail_steps: list[ObservedStep] = []

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)

            # SSRF guard: re-check every request (redirects + sub-resources)
            # at request time so a page can never pull the browser onto an
            # internal/metadata address.
            guard = UrlGuard()
            page.on("request", guard.request_handler())

            try:
                # Start at the starting URL to establish session
                if self.starting_url:
                    current_url = self.starting_url
                    # SSRF guard: refuse an internal/metadata starting URL up-front.
                    # (skipped under unit tests — see tests/test_journey_observed_trail.py)
                    if not getattr(self, "_url_guard_patched", False):
                        guard.validate(self.starting_url)
                    self._debug(f"Navigating to starting URL: {self.starting_url}")
                    page.goto(self.starting_url, wait_until="networkidle", timeout=self.timeout_ms)
                    self._dismiss_consent_overlays(page)
                    self._dismiss_modals(page)
                    # Auth-gated sites (saucedemo) redirect to a login page; log in
                    # with the profile so the journey can reach products/cart pages.
                    if self._credential_profile:
                        attempt_login(page, self._credential_profile)
                        page.wait_for_timeout(500)
                    # Scrape the starting page so elements are available for placeholder resolution.
                    elements = self._scrape_current_page(page, current_url, context)
                    output[current_url] = elements

                for step_index, step in enumerate(steps):
                    last_error: Exception | None = None
                    self._debug(f"Step {step_index + 1}/{len(steps)}: {step.action} '{step.description}'")

                    # AI-052: begin recording this step's observed transition.
                    observed = ObservedStep(
                        index=step_index,
                        action=step.action,
                        description=step.description or "",
                        from_url=current_url or "",
                    )
                    trail_steps.append(observed)

                    for attempt in range(1, self.max_retries + 1):
                        try:
                            if step.action == "navigate" and step.url:
                                current_url = self._navigate_to(page, step.url, step.timeout_ms)

                            elif step.action == "click":
                                self._dismiss_consent_overlays(page)
                                self._dismiss_modals(page)

                                selector = step.selector
                                if not selector and step.description:
                                    selector = self._discover_selector(page, step.action, step.description)
                                    if selector is None:
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
                                            # AI-052: the trail is the typed record of this
                                            # observed outcome — mark the step as failed so the
                                            # resolver can distinguish "journey did not reach it".
                                            observed.error = "locator_not_found_even_relaxed"
                                            # B-015 / Phase 1d, AI-052 S4: when a CLICK
                                            # description can't find a matching element,
                                            # navigate only to an ALREADY-DISCOVERED page
                                            # whose URL matches the description. No URL
                                            # fabrication, no HEAD probes: if no discovered
                                            # page matches, the step is honestly skipped.
                                            inferred_url = self._match_discovered_url(
                                                step.description, known_urls=list(output.keys())
                                            )
                                            if inferred_url:
                                                self._debug(
                                                    f"Navigating to discovered URL '{inferred_url}' "
                                                    f"for unfound click '{step.description}'"
                                                )
                                                self._context_log.append(
                                                    {
                                                        "event": "url_inference_fallback",
                                                        "step": step_index,
                                                        "description": step.description,
                                                        "inferred_url": inferred_url,
                                                        "page_url": page.url,
                                                    }
                                                )
                                                current_url = self._navigate_to(page, inferred_url, step.timeout_ms)
                                                # Auto-scrape after discovered-URL navigation so the
                                                # destination page's elements are captured for
                                                # subsequent resolution.
                                                if current_url:
                                                    elements = self._scrape_current_page(page, current_url, context)
                                if selector:
                                    observed.selector_used = selector
                                    self._click_selector(page, selector, step.timeout_ms)

                            elif step.action == "fill":
                                selector = step.selector
                                if not selector and step.description:
                                    selector = self._discover_selector(page, step.action, step.description)
                                    if selector is None:
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
                                            # B-028: FILL-quantity with no fillable
                                            # input -> click +/- stepper buttons.
                                            if self._try_quantity_stepper_fallback(page, step):
                                                self._context_log.append(
                                                    {
                                                        "event": "quantity_stepper_fallback",
                                                        "step": step_index,
                                                        "description": step.description,
                                                        "value": step.text,
                                                        "page_url": page.url,
                                                    }
                                                )
                                if selector and step.text:
                                    observed.selector_used = selector
                                    self._fill_selector(page, selector, step.text, step.timeout_ms)

                            elif step.action == "wait":
                                wait_time = (
                                    float(step.description)
                                    if step.description and step.description.replace(".", "").isdigit()
                                    else 1.0
                                )
                                page.wait_for_timeout(int(wait_time * 1000))

                            elif step.action == "scrape" and current_url:
                                elements = self._scrape_current_page(page, current_url, context)
                                output[current_url] = elements

                            elif step.action == "capture" and current_url:
                                html = page.content()
                                elements = self._html_scraper._extract_elements_from_html(html, base_url=current_url)  # noqa: SLF001
                                try:
                                    a11y_snapshot = capture_a11y_snapshot_sync(context, page)
                                    if a11y_snapshot is not None:
                                        elements = AccessibilityEnricher.enrich(elements, a11y_snapshot)  # type: ignore[arg-type]
                                except Exception:
                                    pass
                                output[current_url] = elements

                            # Auto-scrape after navigation if no explicit scrape step
                            if step.action == "navigate" and current_url:
                                elements = self._scrape_current_page(page, current_url, context)
                                output[current_url] = elements

                            # Detect URL changes after click actions
                            new_url = page.url
                            if step.action == "click" and new_url != current_url and current_url:
                                self._debug(f"Click caused navigation: {current_url} -> {new_url}")
                                elements = self._scrape_current_page(page, new_url, context)
                                output[new_url] = elements

                            # AI-052: record the observed transition (facts only).
                            # selector_used may have been mutated by retries on this
                            # step; the last attempt's value is the one that ran.
                            observed.to_url = new_url
                            observed.navigated = bool(current_url and new_url != current_url)
                            observed.scraped = bool(new_url and new_url in output)

                            current_url = new_url
                            last_error = None
                            break

                        except Exception as e:
                            last_error = e
                            if attempt < self.max_retries:
                                backoff = self.base_backoff_ms * (2 ** (attempt - 1)) + random.uniform(0, 100)
                                time.sleep(backoff / 1000.0)

                    if last_error is not None:
                        observed.error = str(last_error)
                        if os.getenv("PIPELINE_DEBUG", "").strip() == "1":
                            print(f"[journey_scraper] Step {step_index} ({step.description}): {last_error}", flush=True)

                # AI-052: hand the typed trail out. The subprocess entry passes a
                # list it embeds in the stdout JSON; direct callers get a
                # reference to the internal trail (same objects).
                if _observed_trail_out is not None:
                    trail_steps_out = _observed_trail_out
                    for i, step_record in enumerate(trail_steps):
                        if i < len(trail_steps_out):
                            trail_steps_out[i] = step_record
                        else:
                            trail_steps_out.append(step_record)
                    if len(trail_steps_out) > len(trail_steps):
                        del trail_steps_out[len(trail_steps) :]
                self._observed_trail = ObservedTrail(steps=trail_steps)

            finally:
                context.close()
                browser.close()

        self._captured_pages = output
        return output

    def get_pages_visited(self) -> list[str]:
        """Return unique URLs visited during the journey."""
        return (
            list(dict.fromkeys(url for url in self._captured_pages if url)) if hasattr(self, "_captured_pages") else []
        )

    def get_observed_trail(self) -> ObservedTrail:
        """Return the observed transition trail captured during the last journey (AI-052).

        Each step is a factual record of where the browser actually was
        (from_url/to_url read from ``page.url``). When the journey ran through
        the subprocess path, this trail is the one embedded in the subprocess
        stdout; when no journey has run yet it is empty.

        Invariant: the order of deduped to_urls matches
        :meth:`get_pages_visited` (both derive from the same scrape order).
        """
        return self._observed_trail

    # ─── Diagnostic methods (spec: journey_scraper_silent_failure) ───

    @staticmethod
    def _match_discovered_url(description: str, known_urls: list[str]) -> str | None:
        """Return an ALREADY-DISCOVERED page URL matching a description (AI-052 S4).

        Evidence-only replacement for the deleted ``_infer_url_from_description``:
        candidates come exclusively from pages the journey has actually scraped.
        No path fabrication, no HEAD probes, no cross-host guesses — if no
        discovered page's URL matches the description keywords, return None and
        let the caller record ``step_skipped``.
        """
        from urllib.parse import urlparse

        desc_lower = description.lower()
        best: tuple[int, str] | None = None
        for url in known_urls:
            parsed = urlparse(url)
            path = (parsed.path or "/").strip("/").lower()
            if not path:
                continue
            # Split the discovered path into words and require at least one
            # description keyword to appear as a path word.
            words = {w for w in path.replace("-", "_").split("_") if len(w) >= 3}
            matched_words = sum(1 for w in words if w in desc_lower)
            if matched_words and (best is None or matched_words > best[0]):
                best = (matched_words, url)
        return best[1] if best else None

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
        """Find a selector using relaxed matching criteria."""
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001

        norm_desc = re.sub(r"[^\w\s]", " ", description).lower().split()
        if not norm_desc:
            return None

        for element in elements:
            raw = (element.get("accessible_name") or element.get("aria_label") or element.get("text", "")).strip()
            norm_text = re.sub(r"[^\x00-\x7f]", "", raw).strip().lower()
            if len(norm_text) < 2:
                continue
            if any(kw in norm_text for kw in norm_desc if len(kw) >= 2):
                robust = build_robust_locator(element)
                if robust:
                    return robust
                sel = element.get("selector")
                if sel:
                    return sel

        return None

    # ─── B-028: e-commerce context hints for journey discovery ────────────

    _PRODUCT_INTENT_TERMS = (
        "product",
        "add to cart",
        "add item",
        "add product",
        "item to cart",
        "buy",
        "purchase",
        "browse",
        "view product",
        "click on a product",
        "click on product",
        "select a product",
    )
    _DISMISS_INTENT_TERMS = (
        "dismiss",
        "modal",
        "popup",
        "pop-up",
        "dialog",
        "continue shopping",
    )
    _CLOSE_INTENT_WORDS = {"close", "dismiss", "ok", "cancel"}
    _NAV_CHROME_PATHS = (
        "/view_cart",
        "/login",
        "/signup",
        "/register",
        "/contact",
        "/api",
        "/test_cases",
        "/cart",
        "/checkout",
        "/payment",
    )

    @staticmethod
    def _has_product_intent(description: str) -> bool:
        """True when a CLICK description targets product browsing / add-to-cart."""
        lowered = f" {description.lower().strip()} "
        if any(term in lowered for term in JourneyScraper._PRODUCT_INTENT_TERMS):
            return True
        words = set(description.lower().split())
        return bool(words & {"product", "products", "item", "items"})

    @staticmethod
    def _has_dismiss_intent(description: str) -> bool:
        """True when a CLICK description asks to dismiss/close a modal or popup."""
        lowered = f" {description.lower().strip()} "
        if any(term in lowered for term in JourneyScraper._DISMISS_INTENT_TERMS):
            return True
        return bool(set(description.lower().split()) & JourneyScraper._CLOSE_INTENT_WORDS)

    @staticmethod
    def _has_browse_intent(description: str) -> bool:
        """True when a product-intent description asks to OPEN/view a product.

        "Add"/"buy" phrasing (add to cart) is excluded so those steps keep
        preferring the add-to-cart button over the product detail link.
        """
        lowered = f" {description.lower().strip()} "
        if any(term in lowered for term in ("add", "buy", "purchase")):
            return False
        return any(
            term in lowered
            for term in (
                "view",
                "open",
                "see",
                "browse",
                "details",
                "click on a product",
                "click on product",
                "select a product",
            )
        )

    @staticmethod
    def _has_category_intent(description: str) -> bool:
        """True when a product-intent description targets a category LISTING.

        "Product Category" / "category link" / "browse category" describe a
        category listing page, NOT a product detail page. Without this hint,
        "Product Category" was resolved to a product-detail link ("View
        Product" outscored the unlabeled category links), the journey visited
        a detail page, and every downstream locator was resolved against the
        wrong page.
        """
        lowered = f" {description.lower().strip()} "
        return any(term in lowered for term in ("category", "categories", "listing", "catalog", "catalogue", "browse"))

    @staticmethod
    def _is_category_listing_link(element: dict[str, Any]) -> bool:
        """True when the element is a category/products listing link."""
        sel = str(element.get("selector", "")).lower()
        href = str(element.get("href", "")).lower()
        text = str(element.get("text", "")).strip().lower()
        return (
            "category_products" in sel
            or "/category_products" in href
            or "/category/" in href
            or "/brand_products" in href
            or "/products" in href
            or "/categories" in href
            or text in ("products", "categories", "all products")
        )

    @staticmethod
    def _is_product_detail_link(element: dict[str, Any]) -> bool:
        """True when the element is a product-detail link (href /product_details/…)."""
        sel = str(element.get("selector", "")).lower()
        href = str(element.get("href", "")).lower()
        return "product_details" in sel or "/product_details" in href or "/product/" in href

    @staticmethod
    def _is_modal_root(element: dict[str, Any]) -> bool:
        """True for elements that are modal structure (root/container) rather than content."""
        sel = str(element.get("selector", "")).lower()
        classes = str(element.get("classes", "")).lower()
        element_id = str(element.get("id", "")).lower()
        return any(
            marker in sel or marker in classes or marker in element_id for marker in ("modal", "dialog", "popup")
        )

    @staticmethod
    def _is_product_card_element(element: dict[str, Any]) -> bool:
        """True when the element is a product-card link/button (not site chrome)."""
        sel = str(element.get("selector", "")).lower()
        classes = str(element.get("classes", "")).lower()
        href = str(element.get("href", "")).lower()
        return (
            "data-product-id" in sel
            or "add-to-cart" in sel
            or "add-to-cart" in classes
            or "product_details" in sel
            or "/product" in href
            or ".product" in sel
        )

    @staticmethod
    def _is_nav_chrome_link(element: dict[str, Any]) -> bool:
        """True when the element is a site-chrome navigation link (cart/login/etc)."""
        href = str(element.get("href", "")).strip().lower()
        if not href:
            return False
        from urllib.parse import urlparse

        path = urlparse(href).path.lower()
        if path in ("", "/"):
            return True
        return any(chrome in path for chrome in JourneyScraper._NAV_CHROME_PATHS)

    @staticmethod
    def _is_dismiss_element(element: dict[str, Any]) -> bool:
        """True when the element is a modal dismissal control (Continue/Close/OK)."""
        sel = str(element.get("selector", "")).lower()
        classes = str(element.get("classes", "")).lower()
        text = str(element.get("text", "")).strip().lower()
        return (
            "close-modal" in sel
            or "close-modal" in classes
            or "dismiss" in sel
            or "dismiss" in classes
            or "continue-shopping" in sel
            or "continue" in classes.split()
            or "close" in classes.split()
            or text in ("continue shopping", "close", "dismiss", "ok", "got it", "cancel", "no thanks")
        )

    def _discover_selector(self, page: Any, action: str, description: str) -> str | None:
        """Find the best selector for a description on the current live page.

        B-015: Unified ranking pipeline — discovery and resolution share scoring logic.
        B-028: Journey steps carry lowercase actions ("click"/"fill") which
        silently disabled every action-specific bonus/gate in PlaceholderScorer
        (it branches on "CLICK"/"FILL"). Discovery scores collapsed to raw word
        overlap, so generic descriptions ("click on a product to view it") lost
        to "View Cart" nav links. Fixes here:
          - normalize the action to uppercase before scoring
          - skip invisible elements for CLICK/FILL (rank_candidates parity)
          - only apply the modal penalty when a modal is actually VISIBLE
            (hidden modals like #cartModal are always in the e-commerce DOM)
          - product-intent hints: prefer product-card elements over nav chrome
          - modal-dismiss hints: prefer dismiss buttons over navigation links
        """
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        # B-028: scorer branches on uppercase action values.
        action = action.upper()

        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001

        try:
            elements = capture_element_visibility_sync(page, elements)
        except Exception:
            pass

        self._debug(f"Scraped {len(elements)} elements for discovery of '{description}'")

        best_element: dict[str, Any] | None = None
        best_score: float = -1

        has_product_intent = action == "CLICK" and self._has_product_intent(description)
        has_browse_intent = has_product_intent and self._has_browse_intent(description)
        has_category_intent = has_product_intent and self._has_category_intent(description)
        has_dismiss_intent = action == "CLICK" and self._has_dismiss_intent(description)

        # B-028: a hidden modal container (e.g. #cartModal) is always present in
        # e-commerce DOMs. Only treat the page as modal-blocked when a modal-
        # structure element is actually visible.
        page_has_visible_modal = any(self._is_modal_root(e) and e.get("is_visible") is not False for e in elements)

        for element in elements:
            selector = element.get("selector", "")
            if not selector:
                continue
            role = str(element.get("role", "")).lower()

            # B-028: hidden elements are not click/fill targets (rank_candidates
            # parity). Without this, the hidden modal's "View Cart" link can win
            # generic descriptions via raw word overlap.
            if action in ("CLICK", "FILL") and element.get("is_visible") is False:
                continue

            score = PlaceholderScorer.compute_element_score(
                action=action,
                description=description,
                element=element,
                selector=selector,
                match_threshold=1,
            )
            if score is None:
                continue

            in_modal = element.get("in_modal", False)
            if action == "CLICK" and page_has_visible_modal and not in_modal:
                score -= 30
            if action == "FILL" and role not in (
                "text",
                "password",
                "searchbox",
                "textbox",
                "combobox",
                "email",
                "tel",
                "number",
                "select",
                "textarea",
                "url",
            ):
                score -= 50
            elif action == "CLICK" and role not in (
                "button",
                "submit",
                "link",
                "a",
                "menuitem",
                "tab",
                "checkbox",
                "radio",
            ):
                score -= 20

            # B-028: e-commerce context hints.
            if has_product_intent:
                if self._is_product_card_element(element):
                    if has_browse_intent and self._is_product_detail_link(element):
                        # "click on a product to view it" -> product detail link
                        score += 16
                    elif has_category_intent and self._is_category_listing_link(element):
                        # "Product Category" -> category/products listing page
                        score += 16
                    elif has_category_intent and self._is_product_detail_link(element):
                        # Category intents must NOT visit a single product page.
                        score -= 10
                    else:
                        score += 10
                elif self._is_nav_chrome_link(element):
                    score -= 10
            if has_dismiss_intent:
                if self._is_dismiss_element(element):
                    score += 15
                elif element.get("href"):
                    # Navigation links never dismiss a modal.
                    score -= 10

            if score > best_score:
                best_score = score
                best_element = element

        if best_element is not None:
            # B-028: a modal-dismiss step must only click an actual dismissal
            # control. Generic elements (nav links, product buttons) scoring
            # weakly should be skipped — the modal was already dismissed by
            # _dismiss_modals, so clicking anything else is a wasted/wrong click.
            if has_dismiss_intent and not self._is_dismiss_element(best_element):
                best_element = None
                best_score = -1

        if best_element is not None:
            robust = build_robust_locator(best_element)
            if robust or best_element.get("selector"):
                self._debug(
                    f"Selected '{robust or best_element.get('selector')}' (score={best_score}) for '{description}'"
                )
                return robust or best_element.get("selector")

        # B-028: product/dismiss intents with no viable candidate must NOT fall
        # back to rank_candidates — its raw word-overlap ranking picks the
        # hidden modal's "View Cart" link (score=1). Skipping the step is safer
        # than navigating to the wrong page.
        if best_element is None and (has_dismiss_intent or has_product_intent):
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
        """Navigate to a URL and return the final URL."""
        full_url = url
        if url.startswith("/"):
            from urllib.parse import urljoin

            full_url = urljoin(page.url, url)

        # SSRF guard: a journey-inferred URL must satisfy the same rules as
        # the starting URL (the request handler covers redirects/sub-resources).
        # (skipped under unit tests — see tests/test_journey_observed_trail.py)
        if not getattr(self, "_url_guard_patched", False):
            UrlGuard().validate(full_url)

        response = page.goto(full_url, wait_until="networkidle", timeout=timeout_ms)
        if response:
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
            self._dismiss_consent_overlays(page)
            self._dismiss_modals(page)
            return page.url
        return full_url

    def _click_selector(self, page: Any, selector: str, timeout_ms: int) -> None:
        """Click an element by selector, with scroll-into-view and retry."""
        self._debug(f"Attempting to click selector: {selector}")
        locator = page.locator(selector).first
        if locator.count() == 0:
            self._debug(f"Click failed: Locator {selector} not found on page.")
            return

        # Reveal hidden SPA sections before interacting
        self._reveal_hidden_sections(page)

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
        page.wait_for_timeout(500)
        self._dismiss_consent_overlays(page)
        self._dismiss_modals(page)

    def _fill_selector(self, page: Any, selector: str, text: str, timeout_ms: int) -> None:
        """Fill an input element by selector."""
        self._debug(f"Attempting to fill selector: {selector} with text: {text}")
        locator = page.locator(selector).first
        if locator.count() == 0:
            self._debug(f"Fill failed: Locator {selector} not found on page.")
            return

        # Reveal hidden SPA sections before interacting
        self._reveal_hidden_sections(page)

        try:
            locator.fill(text)
            self._debug(f"Filled successfully: {selector}")
        except Exception as e:
            self._debug(f"Fill exception: {e}")
            raise

    def _try_quantity_stepper_fallback(self, page: Any, step: JourneyStep) -> bool:
        """Best-effort quantity setting via +/- stepper buttons.

        B-028: some e-commerce sites expose quantity only as +/- stepper
        buttons with no fillable input. When a FILL-quantity step finds no
        fillable input, click the increment button ``value`` times instead of
        silently skipping the step.
        """
        if not step.text or not str(step.text).replace(".", "").isdigit():
            return False
        lowered = (step.description or "").lower()
        if not any(term in lowered for term in ("quantity", "qty", "amount", "count")):
            return False
        increments = int(float(str(step.text)))
        if increments < 1:
            return False
        candidates = (
            "button.qty-plus, .qty_plus, .qtyplus, .cart_quantity_up, .increment, .plus",
            "button:has-text('+'), a:has-text('+'), .fa-plus, .fa.fa-plus, .fa-plus-square",
            "[data-qty-plus], [aria-label*='increase' i], [aria-label*='increment' i]",
        )
        for group in candidates:
            for raw in group.split(","):
                sel = raw.strip()
                if not sel:
                    continue
                try:
                    locator = page.locator(sel).first
                    if locator.count() and locator.is_visible(timeout=150):
                        # Quantity steppers start at 1 — reaching ``increments``
                        # needs (increments - 1) clicks; always at least one.
                        clicks = max(increments - 1, 1)
                        for _ in range(min(clicks, 20)):
                            locator.click(timeout=1000)
                            page.wait_for_timeout(120)
                        self._debug(f"Quantity stepper fallback: clicked {sel} {clicks}x")
                        return True
                except Exception:
                    continue
        return False

    def _scrape_current_page(self, page: Any, url: str, context: Any | None = None) -> list[dict[str, Any]]:
        """Scrape elements from the current page state.

        Mirrors the frozen-capture methodology (``refresh_lv_capture.py``):
        reveal hidden SPA sections before capturing visibility. Multi-step
        single-page forms keep all sections in the DOM with ``display:none``
        toggled by JS — without reveal, every element in a non-active section
        is marked ``is_visible=False`` and the resolver's Pass 3 hard-skips
        hidden CLICK/FILL targets, so SPA pages can never resolve.
        """
        self._reveal_hidden_sections(page)
        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=url)  # noqa: SLF001

        try:
            enriched = capture_element_visibility_sync(page, elements)
            if context is not None:
                a11y_snapshot = capture_a11y_snapshot_sync(context, page)
                if a11y_snapshot is not None:
                    enriched = AccessibilityEnricher.enrich(enriched, a11y_snapshot)  # type: ignore[arg-type]
            return enriched
        except Exception:
            pass

        return elements

    @staticmethod
    def _reveal_hidden_sections(page: Any) -> None:
        """Reveal hidden SPA form sections by making all sections visible.

        On multi-step single-page forms (e.g. the LV Insurance mock site),
        sections are hidden behind JavaScript section toggles (showPage()).
        Elements in hidden sections exist in the DOM but Playwright cannot
        interact with them because they have display:none.

        This method forces all hidden sections to become visible so that
        placeholder resolution can click/fill elements in any section.
        Best-effort — non-destructive if no section pattern is detected.
        """
        try:
            page.evaluate(
                """
                () => {
                    // Pattern 1: .page { display:none } / .page.active { display:block }
                    const pages = document.querySelectorAll('.page');
                    pages.forEach(el => {
                        el.style.display = 'block';
                        el.classList.add('active');
                    });

                    // Pattern 2: sections hidden via display:none in inline styles
                    document.querySelectorAll('[style*="display: none"], [style*="display:none"]').forEach(el => {
                        el.style.display = 'block';
                    });

                    // Pattern 3: Any section/div that is a direct child of the form
                    // and is not visible, but has interactive elements
                    document.querySelectorAll('section, .section, [class*="Section"]').forEach(el => {
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none') {
                            el.style.display = 'block';
                        }
                    });
                }
                """
            )
            page.wait_for_timeout(200)
        except Exception:
            pass

    @staticmethod
    def _dismiss_consent_overlays(page: Any) -> None:
        """Delegate to central consent dismissal utility."""
        from src.browser_utils import dismiss_consent_overlays

        dismiss_consent_overlays(page)  # type: ignore[arg-type]

    @staticmethod
    def _dismiss_modals(page: Any) -> None:
        """Dismiss confirmation modals/popups that block pointer events.

        B-023: On sites like automationexercise.com, the "Added to cart"
        confirmation modal (#cartModal) intercepts clicks on navigation links.
        This dismisses common modal patterns before click steps so the journey
        scraper doesn't waste time retrying blocked clicks.

        Non-destructive: if no modal is visible, these selectors won't match
        and the dismissal is a no-op.
        """
        # B-015 lesson: never match generic button text globally — saucedemo's
        # cart page has a visible "Continue Shopping" button that would get
        # clicked and navigate the journey back to inventory. Text-based
        # dismissal is scoped to modal/dialog containers only.
        modal_containers = "#cartModal, .modal, [role='dialog'], .modal-dialog, .modal-content"
        dismiss_selectors = [
            f"{modal_containers} button:has-text('Continue Shopping')",
            f"{modal_containers} .continue-shopping",
            f"{modal_containers} .close",
            f"{modal_containers} .modal-close",
            f"{modal_containers} .close-btn",
            f"{modal_containers} [data-dismiss='modal']",
            f"{modal_containers} .modal-footer .btn",
            "button.btn-success.close-modal",
        ]
        for selector in dismiss_selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=200):
                    locator.click(timeout=1000)
                    page.wait_for_timeout(300)  # Allow modal animation to complete
                    return  # Only dismiss one modal
            except Exception:
                continue


# ─── Subprocess entry (delegates to journey_subprocess.py) ───

if __name__ == "__main__":
    from src.journey_subprocess import run_journey_subprocess_entry

    if "--journey-scrape" in sys.argv:
        raise SystemExit(run_journey_subprocess_entry())
