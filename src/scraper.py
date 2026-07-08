"""Playwright-based scraper used by the intelligent pipeline to discover real selectors."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page, sync_playwright

from src.accessibility_enricher import AccessibilityEnricher
from src.element_enricher import ElementEnricher


@dataclass
class ScrapeResult:
    """Scraped page data, with optional visual capture metadata."""

    url: str
    elements: list[dict[str, Any]]
    title: str = ""
    html_snippet: str = ""
    error: str | None = None
    final_url: str | None = None
    a11y_snapshot: dict[str, Any] | None = None
    screenshot_bytes: bytes | None = None
    element_boxes: list[dict[str, Any]] | None = None


def _normalise_locator_bbox(bbox: Any) -> dict[str, float] | None:
    """Return a numeric bbox dict when Playwright reports a visible region."""
    if not bbox:
        return None

    width = float(bbox.get("width", 0) or 0)
    height = float(bbox.get("height", 0) or 0)
    if width <= 0 or height <= 0:
        return None

    return {
        "x": float(bbox.get("x", 0) or 0),
        "y": float(bbox.get("y", 0) or 0),
        "width": width,
        "height": height,
    }


def _selector_from_locator(locator: Any, index: int) -> str:
    """Build a best-effort selector for a live Playwright locator."""
    try:
        selector = locator.evaluate(
            """(node) => {
                const tag = node.tagName.toLowerCase();
                if (node.id) return `#${node.id}`;
                for (const attr of ["data-testid", "data-test", "data-qa"]) {
                    const value = node.getAttribute(attr);
                    if (value) return `[${attr}="${value}"]`;
                }
                const productId = node.getAttribute("data-product-id");
                if (productId) {
                    const classes = Array.from(node.classList || []).filter(Boolean).join(".");
                    return classes ? `${tag}.${classes}[data-product-id="${productId}"]` : `${tag}[data-product-id="${productId}"]`;
                }
                if (tag === "a") {
                    const href = node.getAttribute("href");
                    if (href && !href.startsWith("#") && !href.startsWith("javascript:")) {
                        try {
                            const parsed = new URL(href, window.location.href);
                            return `a[href="${parsed.pathname || href}"]`;
                        } catch {
                            return `a[href="${href}"]`;
                        }
                    }
                }
                const name = node.getAttribute("name");
                if (name) return `${tag}[name="${name}"]`;
                const classes = Array.from(node.classList || []).filter(Boolean).join(".");
                if (classes) return `.${classes}`;
                return tag;
            }"""
        )
        if selector:
            return str(selector)
    except Exception:
        pass
    return f"interactive[{index}]"


def capture_page_screenshot(
    page: Page,
    url: str,
    full_page: bool = True,
) -> tuple[bytes, list[dict[str, Any]]]:
    """Capture a page screenshot and bounding boxes for interactive elements."""
    screenshot_bytes = page.screenshot(full_page=full_page, type="png")
    interactive_locator = page.locator("button, a, input, select, [onclick], [role=button], [tabindex]")
    element_boxes: list[dict[str, Any]] = []

    try:
        count = interactive_locator.count()
    except Exception:
        return screenshot_bytes, element_boxes

    for index in range(count):
        try:
            locator = interactive_locator.nth(index)
            bbox = _normalise_locator_bbox(locator.bounding_box())
            if bbox is None:
                continue

            selector = _selector_from_locator(locator, index)
            is_visible = True
            try:
                is_visible = bool(locator.is_visible())
            except Exception:
                pass

            element_boxes.append(
                {
                    "selector": selector,
                    "bbox": bbox,
                    "element_index": index,
                    "is_visible": is_visible,
                    "url": url,
                }
            )
        except Exception:
            continue

    return screenshot_bytes, element_boxes


def scrape_with_enrichment(
    scrape_results: list[ScrapeResult],
    provider: str,
    model: str,
    timeout: int = 60,
) -> list[ScrapeResult]:
    """Apply vision enrichment to scrape results that include screenshot data."""
    from src.vision_enricher import VisionEnricher

    if not VisionEnricher.is_vision_capable(provider, model):
        return scrape_results

    enriched_results: list[ScrapeResult] = []
    for result in scrape_results:
        if result.screenshot_bytes and result.element_boxes:
            result.elements = PageScraper._attach_element_boxes(result.elements, result.element_boxes)
            result.elements = VisionEnricher.enrich_elements(
                elements=result.elements,
                screenshot_bytes=result.screenshot_bytes,
                provider=provider,
                model=model,
                timeout=timeout,
            )
        enriched_results.append(result)

    return enriched_results


class PageScraper:
    """Scrape pages using a real browser to ensure JavaScript rendering and correct redirects."""

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms
        self.last_scrape_results: dict[str, ScrapeResult] = {}

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
        screenshot_bytes = None
        screenshot_base64 = data.get("screenshot_base64")
        if isinstance(screenshot_base64, str) and screenshot_base64:
            try:
                screenshot_bytes = base64.b64decode(screenshot_base64)
            except ValueError:
                screenshot_bytes = None
        element_boxes = data.get("element_boxes") or []

        # Enrich elements with computed accessibility names (AI-024)
        elements = AccessibilityEnricher.enrich(elements, a11y_snapshot)
        elements = self._attach_element_boxes(elements, element_boxes)
        self.last_scrape_results[url] = ScrapeResult(
            url=url,
            elements=elements,
            title=str(data.get("title", "")),
            html_snippet=str(data.get("html_snippet", "")),
            error=error,
            final_url=final_url,
            a11y_snapshot=a11y_snapshot,
            screenshot_bytes=screenshot_bytes,
            element_boxes=element_boxes,
        )

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

                # Dismiss consent overlays before scraping — otherwise we capture
                # cookie banner elements instead of actual page content
                from src.browser_utils import dismiss_consent_overlays

                dismiss_consent_overlays(page)

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

    def _scrape_url_sync_result(self, url: str) -> ScrapeResult:
        """Synchronous scrape result including screenshot bytes and element boxes."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()

                response = page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                if not response:
                    browser.close()
                    return ScrapeResult(url=url, elements=[], error=f"No response from {url}", final_url=url)

                if response.status >= 400:
                    final_url = page.url
                    browser.close()
                    return ScrapeResult(url=url, elements=[], error=f"HTTP {response.status}", final_url=final_url)

                final_url = page.url

                # Dismiss consent overlays before scraping
                from src.browser_utils import dismiss_consent_overlays

                dismiss_consent_overlays(page)

                title = page.title()
                html_content = page.content()
                elements = self._extract_elements_from_html(html_content, base_url=final_url)
                elements = self._capture_element_visibility(page, elements)

                a11y_snapshot: dict[str, Any] = {}
                try:
                    cdp = context.new_cdp_session(page)
                    ax_result = cdp.send("Accessibility.getFullAXTree")
                    a11y_snapshot = AccessibilityEnricher._transform_cdp_ax_tree(ax_result.get("nodes", []))
                except Exception as e:
                    self._debug(f"CDP accessibility tree failed: {e} â€” skipping a11y enrichment")

                screenshot_bytes, element_boxes = capture_page_screenshot(page, final_url)
                elements = self._attach_element_boxes(elements, element_boxes)

                browser.close()
                return ScrapeResult(
                    url=url,
                    elements=elements,
                    title=title,
                    html_snippet=html_content[:2000],
                    error=None,
                    final_url=final_url,
                    a11y_snapshot=a11y_snapshot,
                    screenshot_bytes=screenshot_bytes,
                    element_boxes=element_boxes,
                )

        except Exception as e:
            return ScrapeResult(url=url, elements=[], error=str(e), final_url=url)

    @staticmethod
    def _attach_element_boxes(
        elements: list[dict[str, Any]],
        element_boxes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Attach matching bounding boxes to scraped elements by selector."""
        boxes_by_selector: dict[str, dict[str, Any]] = {
            str(box.get("selector", "")): box for box in element_boxes if box.get("selector")
        }
        for index, element in enumerate(elements):
            selector = str(element.get("selector", ""))
            matching_box = boxes_by_selector.get(selector)
            if matching_box:
                element["_bbox"] = matching_box.get("bbox")
                element["_element_box_index"] = matching_box.get("element_index")
            else:
                element["_element_box_index"] = index
        return elements

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

    @staticmethod
    def _get_direct_text(tag: Any) -> str:
        """Get only direct text content of a tag, not inherited from children.

        Used for B-019 display elements to avoid container divs inheriting
        all descendant text (e.g. <div class=login_container> containing
        form fields would get all their text via get_text()).
        """
        parts: list[str] = []
        for child in tag.children:
            if hasattr(child, "name") and child.name is None:
                # Text node (not a tag)
                parts.append(str(child))
        return " ".join(parts).strip()

    @staticmethod
    def _build_element_dict(
        tag: Any,
        base_url: str,
        labels: dict[str, str],
        id_to_text: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Build a scraped element dict from a BeautifulSoup tag.

        Shared between the interactive and display (B-019) extraction passes.
        """
        from urllib.parse import urlparse

        href = PageScraper._normalise_href(base_url, str(tag.get("href", "")))

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

        # Try to get text content from various sources
        text_content = tag.get_text(" ", strip=True)

        # B-019: For SVG elements, also check <title> and <desc> children
        if tag.name in ("svg", "title", "desc") and not text_content:
            title_child = tag.find("title")
            if title_child:
                text_content = title_child.get_text(" ", strip=True)
            if not text_content:
                desc_child = tag.find("desc")
                if desc_child:
                    text_content = desc_child.get_text(" ", strip=True)

        # B-019: Check label (from <label> tag with for attribute)
        tag_id = tag.get("id")
        if not text_content and tag_id and tag_id in labels:
            text_content = labels[str(tag_id)]

        # B-019: Resolve aria-labelledby and aria-describedby
        if not text_content and id_to_text is not None:
            aria_labelledby = tag.get("aria-labelledby")
            if aria_labelledby:
                # Split by spaces (aria-labelledby can reference multiple IDs)
                labelledby_ids = str(aria_labelledby).split()
                texts = []
                for ref_id in labelledby_ids:
                    if ref_id in id_to_text:
                        texts.append(id_to_text[ref_id])
                if texts:
                    text_content = " ".join(texts)

            # If still no text, try aria-describedby
            if not text_content:
                aria_describedby = tag.get("aria-describedby")
                if aria_describedby:
                    describedby_ids = str(aria_describedby).split()
                    texts = []
                    for ref_id in describedby_ids:
                        if ref_id in id_to_text:
                            texts.append(id_to_text[ref_id])
                    if texts:
                        text_content = " ".join(texts)

        return {
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
            "is_visible": True,
        }

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

        # B-019: Display elements — headings, text-bearing containers, data-test elements, and SVG.
        # Captured separately so ASSERT placeholders have non-interactive candidates.
        display_tags = [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "span",
            "div",
            "section",
            "main",
            "article",
            "svg",
            "title",
            "desc",
        ]

        labels: dict[str, str] = {}
        for label in soup.find_all("label"):
            for_id = label.get("for")
            if for_id:
                labels[str(for_id)] = label.get_text(" ", strip=True)

        # B-019: Resolve aria-labelledby and aria-describedby references
        # Create a map of element IDs to their text content
        id_to_text: dict[str, str] = {}
        for element in soup.find_all(id=True):
            elem_id = str(element.get("id", ""))
            if elem_id:
                # Try to get meaningful text from the element
                text = element.get_text(" ", strip=True)
                if not text:
                    # If element has no text, check for title/desc children (for SVG)
                    title_child = element.find("title")
                    if title_child:
                        text = title_child.get_text(" ", strip=True)
                    else:
                        desc_child = element.find("desc")
                        if desc_child:
                            text = desc_child.get_text(" ", strip=True)
                if text:
                    id_to_text[elem_id] = text

        for tag in soup.find_all(interactive_tags):
            elem_dict = self._build_element_dict(tag, base_url, labels, id_to_text)
            if elem_dict is not None:
                elements.append(elem_dict)

        # B-019: Second pass — capture display elements (headings, text containers, SVG).
        # These give ASSERT placeholders non-interactive candidates to match.
        # Skip elements already captured (by id + selector) to avoid duplicates.
        captured_ids: set[str] = set()
        for el in elements:
            eid = el.get("id", "")
            if eid:
                captured_ids.add(eid)

        for tag in soup.find_all(display_tags):
            # Skip if already captured as interactive (same id)
            tag_id = tag.get("id")
            if tag_id and tag_id in captured_ids:
                continue

            data_test = str(tag.get("data-test", "")).strip()

            # For <div> without data-test, use direct text only to avoid
            # container divs inheriting all descendant text.
            if tag.name == "div" and not data_test:
                direct_text = self._get_direct_text(tag)
                # Only keep divs that have meaningful direct text
                if len(direct_text) < 3:
                    continue
            else:
                # Headings, spans, SVG, title, desc — use full text (they're leaf elements)
                direct_text = tag.get_text(" ", strip=True)
                # For SVG, also check title/desc
                if not direct_text and tag.name in ("svg", "title", "desc"):
                    title_child = tag.find("title")
                    if title_child:
                        direct_text = title_child.get_text(" ", strip=True)
                    if not direct_text:
                        desc_child = tag.find("desc")
                        if desc_child:
                            direct_text = desc_child.get_text(" ", strip=True)

            # For all elements, use full text for the element dict
            # (needed for matching), but use direct text for filtering
            text_content = tag.get_text(" ", strip=True)
            if not text_content and tag.name in ("svg", "title", "desc"):
                title_child = tag.find("title")
                if title_child:
                    text_content = title_child.get_text(" ", strip=True)
                if not text_content:
                    desc_child = tag.find("desc")
                    if desc_child:
                        text_content = desc_child.get_text(" ", strip=True)

            if len(direct_text) < 3 and not data_test:
                continue

            # Skip text that's too long — likely a container, not a leaf element
            if len(text_content) > 300:
                continue

            elem_dict = self._build_element_dict(tag, base_url, labels, id_to_text)
            if elem_dict is not None:
                elements.append(elem_dict)

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
    scrape_result = scraper._scrape_url_sync_result(url)

    result = {
        "elements": scrape_result.elements,
        "a11y_snapshot": scrape_result.a11y_snapshot or {},
        "error": scrape_result.error,
        "final_url": scrape_result.final_url or url,
        "title": scrape_result.title,
        "html_snippet": scrape_result.html_snippet,
        "element_boxes": scrape_result.element_boxes or [],
        "screenshot_base64": base64.b64encode(scrape_result.screenshot_bytes).decode("ascii")
        if scrape_result.screenshot_bytes
        else "",
    }
    print(json.dumps(result))


if __name__ == "__main__":
    if "--scrape" in sys.argv:
        _subprocess_entrypoint()
