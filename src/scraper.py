"""Playwright-based scraper used by the intelligent pipeline to discover real selectors."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from src.element_enricher import ElementEnricher


class PageScraper:
    """Scrape pages using a real browser to ensure JavaScript rendering and correct redirects."""

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms

    def _debug(self, message: str) -> None:
        """Print debug message if logging is enabled."""
        if os.getenv("PIPELINE_DEBUG", "").strip() == "1":
            print(f"[scraper] {message}", flush=True)

    async def scrape_url(self, url: str) -> tuple[list[dict[str, Any]], str | None, str]:
        """Scrape a single URL using a headless browser.

        Returns:
        A tuple of (elements_list, error_message_or_none, final_url).
        """
        import asyncio

        return await asyncio.to_thread(self._scrape_url_sync, url)

    def _scrape_url_sync(self, url: str) -> tuple[list[dict[str, Any]], str | None, str]:
        """Synchronous scraping logic, run via asyncio.to_thread."""
        self._debug(f"Starting browser scrape for {url}...")

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
                    return [], f"No response from {url}", url

                if response.status >= 400:
                    return [], f"HTTP {response.status}", page.url

                final_url = page.url
                html_content = page.content()
                elements = self._extract_elements_from_html(html_content, base_url=final_url)

                browser.close()
                self._debug(f"Successfully scraped {len(elements)} elements from {final_url}")
                return elements, None, final_url

        except Exception as e:
            self._debug(f"Error scraping {url}: {e}")
            return [], str(e), url

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
            '[id*="consent"]',
            '[id*="cookie"]',
            '[class*="consent"]',
            '[class*="cookie"]',
            '[class*="cc-"]',
            # Common consent modal patterns
            '[role="dialog"][id*="consent"]',
            '[role="dialog"][id*="cookie"]',
            '[role="dialog"][class*="consent"]',
            '[role="dialog"][class*="cookie"]',
            # Generic overlay dismiss
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
                    "name": str(tag.get("name", "")).strip(),
                    "id": str(tag.get("id", "")).strip(),
                    "classes": " ".join(_class_attr) if isinstance(_class_attr := tag.get("class"), list) else "",
                    "value": str(tag.get("value", "")).strip(),
                    "placeholder": str(tag.get("placeholder", "")).strip(),
                }
            )

        # Enrich elements with visual and contextual metadata
        elements = ElementEnricher.enrich_batch(elements)

        return elements

    async def scrape_all(self, urls: list[str]) -> dict[str, tuple[list[dict[str, Any]], str | None, str]]:
        """Scrape multiple URLs using the Playwright browser."""
        # Use asyncio.to_thread since Playwright sync API is being used
        import asyncio

        results: dict[str, tuple[list[dict[str, Any]], str | None, str]] = {}
        for url in urls:
            results[url] = await asyncio.to_thread(self._scrape_url_sync, url)
        return results
