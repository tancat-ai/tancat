"""Playwright-based scraper used by the intelligent pipeline to discover real selectors."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright


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
        """Return the best available CSS selector for a tag."""
        # Use simple attribute value retrieval for Playwright locators
        for attribute in ("data-testid", "data-test", "data-qa", "data-product-id"):
            val = tag.get_attribute(attribute)
            if val:
                return f'[{attribute}="{val}"]'

        tag_id = tag.get_attribute("id")
        if tag_id:
            return f"#{tag_id}"

        tag_name = tag.evaluate("node => node.tagName").lower()
        name_attr = tag.get_attribute("name")
        if name_attr:
            return f'{tag_name}[name="{name_attr}"]'

        if tag_name == "a" and href:
            href_path = urlparse(href).path or href
            return f'a[href="{href_path}"]'

        classes = self._join_classes(tag)
        if classes:
            return "." + ".".join(part for part in classes.split() if part)

        return tag_name

    def _extract_elements_from_html(self, html: str, base_url: str = "") -> list[dict[str, Any]]:
        """Fallback to BeautifulSoup for fast element extraction from the rendered HTML."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        elements: list[dict[str, Any]] = []
        interactive_tags = ["button", "a", "input", "select", "textarea"]

        labels: dict[str, str] = {}
        for label in soup.find_all("label"):
            for_id = label.get("for")
            if for_id:
                labels[str(for_id)] = label.get_text(" ", strip=True)

        for tag in soup.find_all(interactive_tags):
            href = self._normalise_href(base_url, str(tag.get("href", "")))

            # Map BS4 object back to conceptual selector - we reuse the logic
            # but adapted for BS4 since we already have the rendered HTML content
            selector = ""
            for attribute in ("data-testid", "data-test", "data-qa", "data-product-id"):
                val = tag.get(attribute)
                if val:
                    selector = f'[{attribute}="{val}"]'
                    break

            if not selector:
                if tag.get("id"):
                    selector = f"#{tag.get('id')}"
                elif tag.get("name"):
                    selector = f'{tag.name}[name="{tag.get("name")}"]'
                elif tag.name == "a" and href:
                    href_path = urlparse(href).path or href
                    selector = f'a[href="{href_path}"]'
                else:
                    class_list = tag.get("class")
                    classes = " ".join(class_list) if isinstance(class_list, list) else str(class_list or "")
                    if classes:
                        selector = "." + ".".join(part for part in classes.split() if part)
                    else:
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

        return elements

    async def scrape_all(self, urls: list[str]) -> dict[str, tuple[list[dict[str, Any]], str | None, str]]:
        """Scrape multiple URLs using the Playwright browser."""
        # Use asyncio.to_thread since Playwright sync API is being used
        import asyncio

        results: dict[str, tuple[list[dict[str, Any]], str | None, str]] = {}
        for url in urls:
            results[url] = await asyncio.to_thread(self._scrape_url_sync, url)
        return results
