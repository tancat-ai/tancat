"""Playwright-based scraper used by the intelligent pipeline to discover real selectors."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from src.accessibility_enricher import AccessibilityEnricher
from src.element_enricher import ElementEnricher


class PageScraper:
    """Scrape pages using a real browser to ensure JavaScript rendering and correct redirects."""

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms

    def _debug(self, message: str) -> None:
        """Print debug message if logging is enabled."""
        if os.getenv("PIPELINE_DEBUG", "").strip() == "1":
            print(f"[scraper] {message}", flush=True, file=sys.stderr)

    async def scrape_url(self, url: str) -> tuple[list[dict[str, Any]], str | None, str]:
        """Scrape a single URL using a headless browser.

        Returns:
        A tuple of (elements_list, error_message_or_none, final_url).
        """
        return self._scrape_url_via_subprocess(url)

    def _scrape_url_via_subprocess(self, url: str) -> tuple[list[dict[str, Any]], str | None, str]:
        """Run the sync Playwright scrape in a clean subprocess (avoids Windows nested loop issues)."""
        self._debug(f"Starting browser scrape for {url}...")

        payload = {
            "url": url,
            "timeout_ms": self.timeout_ms,
        }
        subprocess_path = str(Path(__file__).resolve())
        try:
            completed = subprocess.run(
                [sys.executable, subprocess_path, "--scrape"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                check=False,
                timeout=max(60, int(self.timeout_ms / 1000) + 30),
            )
        except subprocess.TimeoutExpired:
            self._debug(f"Subprocess timed out scraping {url}")
            return [], f"Timeout scraping {url}", url

        # Always surface subprocess stderr for debugging
        if completed.stderr:
            print(completed.stderr, flush=True, file=sys.stderr)

        if completed.returncode != 0:
            self._debug(f"Subprocess error scraping {url}: {completed.stderr}")
            return [], completed.stderr or f"Subprocess failed for {url}", url

        try:
            data = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            return [], "Invalid JSON from subprocess", url

        elements = data.get("elements", [])
        a11y_snapshot = data.get("a11y_snapshot") or {}
        error = data.get("error")
        final_url = data.get("final_url", url)

        # Enrich elements with computed accessibility names (AI-024)
        elements = AccessibilityEnricher.enrich(elements, a11y_snapshot)

        return elements, error, final_url

    def _scrape_url_sync(self, url: str) -> tuple[list[dict[str, Any]], dict[str, Any], str | None, str]:
        """Synchronous scraping logic, called directly in the subprocess entry point.

        Returns:
            A tuple of (elements_list, a11y_snapshot_dict, error_message_or_none, final_url).
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                # Use a real user-agent to avoid being blocked
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()

                # Navigate and wait for the network to be idle (ensures JS rendering)
                response = page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                if not response:
                    return [], {}, f"No response from {url}", url

                if response.status >= 400:
                    return [], {}, f"HTTP {response.status}", page.url

                final_url = page.url
                html_content = page.content()
                elements = self._extract_elements_from_html(html_content, base_url=final_url)

                # Capture visibility for each element using Playwright runtime checks
                elements = self._capture_element_visibility(page, elements)

                # Capture accessibility snapshot via CDP before browser closes (AI-024)
                # page.accessibility.snapshot() is NOT available in Python Playwright bindings.
                # Use Chrome DevTools Protocol instead.
                a11y_snapshot: dict[str, Any] = {}
                try:
                    cdp = context.new_cdp_session(page)
                    ax_result = cdp.send("Accessibility.getFullAXTree")
                    a11y_snapshot = AccessibilityEnricher._transform_cdp_ax_tree(ax_result.get("nodes", []))
                    # CDP session is cleaned up when browser context closes
                    if a11y_snapshot:
                        self._debug(f"CDP accessibility tree captured: {len(ax_result.get('nodes', []))} nodes")
                    else:
                        self._debug("CDP accessibility tree returned no nodes")
                except Exception as e:
                    self._debug(f"CDP accessibility tree failed: {e} — skipping a11y enrichment")

                browser.close()
                return elements, a11y_snapshot, None, final_url

        except Exception as e:
            return [], {}, str(e), url

    def _capture_element_visibility(
        self,
        page: Any,
        elements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Check runtime visibility of each scraped element using Playwright is_visible().

        This adds an 'is_visible' boolean field to each element dict. Elements that are
        hidden (e.g., behind sliders, in collapsed menus, or display:none) will have
        is_visible=False, allowing the placeholder resolver to prefer visible candidates.

        Note: This runs in the subprocess after networkidle, so JS-rendered state is captured.
        """
        for element in elements:
            selector = str(element.get("selector", "")).strip()
            if not selector:
                element["is_visible"] = True  # No selector — assume visible (safe default)
                continue
            try:
                loc = page.locator(selector).first
                element["is_visible"] = loc.is_visible()
            except Exception:
                # If visibility check fails (e.g., invalid selector), default to True
                # rather than blocking the pipeline. The resolver's scoring still applies.
                element["is_visible"] = True
        return elements

    @staticmethod
    def _normalise_href(base_url: str, href: str) -> str:
        """Return an absolute href when the value looks navigable."""
        cleaned_href = href.strip()
        if not cleaned_href or cleaned_href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return ""
        return urljoin(base_url, cleaned_href)

    @staticmethod
    def _join_classes(tag: Any) -> str:
        """Return CSS class names as a single space-delimited string."""
        class_value = tag.get_attribute("class")
        return class_value.strip() if class_value else ""

    def _build_selector(self, tag: Any, href: str) -> str:
        """Return the best available CSS selector for a tag.

        Priority order:
        1. id (most specific)
        2. data-testid/data-test/data-qa (test-oriented attributes)
        3. data-product-id etc. with tag+class context
        4. href for links
        5. name attribute
        6. class names
        7. tag name (least specific)
        """
        # 1. ID is the most specific single-attribute selector
        tag_id = tag.get_attribute("id")
        if tag_id:
            return f"#{tag_id}"

        # 2. Test-oriented data attributes (standalone, these are meant to be unique)
        for attribute in ("data-testid", "data-test", "data-qa"):
            val = tag.get_attribute(attribute)
            if val:
                return f'[{attribute}="{val}"]'

        # 3. Other data attributes — combine with tag name + classes for specificity
        for attribute in ("data-product-id",):
            val = tag.get_attribute(attribute)
            if val:
                tag_name = tag.evaluate("node => node.tagName").lower()
                classes = self._join_classes(tag)
                if classes:
                    class_part = "." + ".".join(part for part in classes.split() if part)
                    return f'{tag_name}{class_part}[{attribute}="{val}"]'
                return f'{tag_name}[{attribute}="{val}"]'

        # 4. href for links (before generic name check)
        tag_name = tag.evaluate("node => node.tagName").lower()
        if tag_name == "a" and href:
            href_path = urlparse(href).path or href
            return f'a[href="{href_path}"]'

        # 5. Name attribute
        name_attr = tag.get_attribute("name")
        if name_attr:
            return f'{tag_name}[name="{name_attr}"]'

        # 6. Class names
        classes = self._join_classes(tag)
        if classes:
            return "." + ".".join(part for part in classes.split() if part)

        # 7. Tag name (least specific fallback)
        return tag_name

    @staticmethod
    def _remove_consent_overlays(html: str) -> str:
        """Remove common consent/cookie overlay elements from HTML before extraction.

        This prevents consent frameworks (IAB GVL, cookie banners, etc.) from
        polluting the element list with hundreds of vendor/consent UI elements
        that drown out real page content.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Patterns that match consent overlay containers
        consent_selectors = [
            # IAB Global Vendor List overlays
            '[id^="fc-preference"]',
            # Common consent modal patterns (more specific to avoid false positives)
            'div[id*="consent"][role="dialog"]',
            'div[id*="cookie"][role="dialog"]',
            'div[class*="consent"][role="dialog"]',
            'div[class*="cookie"][role="dialog"]',
            'section[class*="consent"]',
            'section[class*="cookie"]',
            # Specific framework classes
            ".cc-window",
            ".cc-banner",
            ".cc-modal",
            # Generic overlay dismiss (only if they have a role or look like a banner)
            "div[aria-label*='Consent']",
            "div[aria-label*='cookie']",
        ]

        for selector in consent_selectors:
            for element in soup.select(selector):
                element.decompose()

        # Also remove script/style elements that are part of consent modals
        for script in soup.find_all("script"):
            text = script.get_text("", strip=True)
            if "fc-preference" in text or "consent" in text.lower():
                script.decompose()

        return str(soup)

    def _extract_elements_from_html(self, html: str, base_url: str = "") -> list[dict[str, Any]]:
        """Extract elements from rendered HTML, removing consent overlays first.

        Consent overlays (IAB GVL, cookie banners) are stripped before element
        extraction so they don't pollute the selector list.
        """
        from bs4 import BeautifulSoup

        # Remove consent overlays before extracting elements
        clean_html = self._remove_consent_overlays(html)
        soup = BeautifulSoup(clean_html, "html.parser")
        elements: list[dict[str, Any]] = []
        interactive_tags = ["button", "a", "input", "select", "textarea"]

        labels: dict[str, str] = {}
        for label in soup.find_all("label"):
            for_id = label.get("for")
            if for_id:
                labels[str(for_id)] = label.get_text(" ", strip=True)

        for tag in soup.find_all(interactive_tags):
            href = self._normalise_href(base_url, str(tag.get("href", "")))

            # Map BS4 object back to conceptual selector — same priority as _build_selector
            selector = ""

            # 1. ID (most specific)
            if tag.get("id"):
                selector = f"#{tag.get('id')}"

            # 2. Test-oriented data attributes (standalone)
            if not selector:
                for attribute in ("data-testid", "data-test", "data-qa"):
                    val = tag.get(attribute)
                    if val:
                        selector = f'[{attribute}="{val}"]'
                        break

            # 3. Other data attributes with tag+class context
            if not selector:
                for attribute in ("data-product-id",):
                    val = tag.get(attribute)
                    if val:
                        class_list = tag.get("class")
                        classes = " ".join(class_list) if isinstance(class_list, list) else str(class_list or "")
                        tag_name = tag.name
                        if classes:
                            class_part = "." + ".".join(part for part in classes.split() if part)
                            selector = f'{tag_name}{class_part}[{attribute}="{val}"]'
                        else:
                            selector = f'{tag_name}[{attribute}="{val}"]'
                        break

            # 4. href for links
            if not selector and tag.name == "a" and href:
                href_path = urlparse(href).path or href
                selector = f'a[href="{href_path}"]'

            # 5. Name attribute
            if not selector and tag.get("name"):
                selector = f'{tag.name}[name="{tag.get("name")}"]'

            # 6. Class names
            if not selector:
                class_list = tag.get("class")
                classes = " ".join(class_list) if isinstance(class_list, list) else str(class_list or "")
                if classes:
                    selector = "." + ".".join(part for part in classes.split() if part)

            # 7. Tag name fallback
            if not selector:
                selector = tag.name

            text_content = tag.get_text(" ", strip=True)
            tag_id = tag.get("id")
            if not text_content and tag_id and tag_id in labels:
                text_content = labels[str(tag_id)]

            elements.append(
                {
                    "selector": selector,
                    "text": text_content,
                    "role": str(tag.get("role", tag.get("type", tag.name))),
                    "href": href,
                    "title": str(tag.get("title", "")).strip(),
                    "aria_label": str(tag.get("aria-label", "")).strip(),
                    "data_test": str(tag.get("data-test", "")).strip(),
                    "name": str(tag.get("name", "")).strip(),
                    "id": str(tag.get("id", "")).strip(),
                    "classes": " ".join(_class_attr) if isinstance(_class_attr := tag.get("class"), list) else "",
                    "value": str(tag.get("value", "")).strip(),
                    "placeholder": str(tag.get("placeholder", "")).strip(),
                    # Session 2: Visibility flag — set to True at extraction time;
                    # _capture_element_visibility() overwrites this with the live DOM
                    # check result (True/False) before returning.
                    "is_visible": True,
                }
            )

        # Enrich elements with visual and contextual metadata
        elements = ElementEnricher.enrich_batch(elements)

        return elements

    async def scrape_all(self, urls: list[str]) -> dict[str, tuple[list[dict[str, Any]], str | None, str]]:
        """Scrape multiple URLs using the Playwright browser."""
        results: dict[str, tuple[list[dict[str, Any]], str | None, str]] = {}
        for url in urls:
            results[url] = self._scrape_url_via_subprocess(url)
        return results


def _subprocess_entrypoint() -> None:
    """Entry point when this module is run as a subprocess with --scrape flag.

    Reads a JSON payload from stdin, runs the sync Playwright scrape, and
    writes a JSON result to stdout. This isolates Playwright from any existing
    asyncio event loop (e.g. Streamlit's), avoiding Windows NotImplementedError.
    """
    payload = json.loads(sys.stdin.read())
    url = payload["url"]
    timeout_ms = payload.get("timeout_ms", 30000)

    scraper = PageScraper(timeout_ms=timeout_ms)
    elements, a11y_snapshot, error, final_url = scraper._scrape_url_sync(url)

    result = {
        "elements": elements,
        "a11y_snapshot": a11y_snapshot,
        "error": error,
        "final_url": final_url,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    if "--scrape" in sys.argv:
        _subprocess_entrypoint()
