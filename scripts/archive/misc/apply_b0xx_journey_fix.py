#!/usr/bin/env python3
"""Apply B-0XX enrichment changes to journey_scraper.py.

Reads clean file from git HEAD, applies:
1. Add AccessibilityEnricher import
2. Enrich "capture" action in _execute_journey_sync (Path C)
3. Add helper methods for visibility + a11y snapshot
4. Modify _scrape_current_page to accept context parameter (Path A)
5. Update callers of _scrape_current_page with context arg
6. Enrich elements in _discover_selector (Path B)

Usage: python scripts/apply_b0xx_journey_fix.py
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def apply_fix() -> None:
    src_file = PROJECT_ROOT / "src" / "journey_scraper.py"
    content = src_file.read_text(encoding="utf-8")

    # Guard: skip if already applied (idempotent)
    if "_capture_element_visibility_sync" in content and content.count("_capture_element_visibility_sync") >= 2:
        print("[SKIP] B-0XX enrichment already applied to journey_scraper.py")
        return

    # 1. Add AccessibilityEnricher import after sync_playwright line
    old_import = "from playwright.sync_api import sync_playwright\n"
    new_import = (
        "from playwright.sync_api import sync_playwright\n"
        "\n"
        "from src.accessibility_enricher import AccessibilityEnricher\n"
    )
    content = content.replace(old_import, new_import)

    # 2. Enrich "capture" action in _execute_journey_sync (Path C)
    old_capture = """                    elif step.action == "capture":
                        html = page.content()
                        elements = html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001
                        captured_pages[current_url] = elements"""

    new_capture = """                    elif step.action == "capture":
                        html = page.content()
                        elements = html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001
                        # B-0XX: Apply visibility + a11y enrichment for consistent scrape quality
                        try:
                            enriched = _capture_element_visibility_sync(page, elements)
                            a11y_snapshot = _capture_a11y_snapshot_sync(context, page)
                            if a11y_snapshot is not None:
                                enriched = AccessibilityEnricher.enrich(enriched, a11y_snapshot)  # type: ignore[arg-type]
                            captured_pages[current_url] = enriched
                        except Exception:
                            # Enrichment is additive — fall back to unenriched elements on failure
                            captured_pages[current_url] = elements"""

    content = content.replace(old_capture, new_capture)

    # 3. Add helper methods at module level (before JourneyScraper class)
    helper_methods = '''
# ────────────────────────────────────────────────────────────────
# B-0XX: Enrichment helpers for consistent scrape quality
# Reused across _execute_journey_sync, JourneyScraper._scrape_current_page,
# and JourneyScraper._discover_selector to match PageScraper enrichment pipeline.
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


'''
    # Insert helper methods before the JourneyScraper class definition
    content = content.replace(
        "class JourneyScraper:",
        helper_methods + "\nclass JourneyScraper:",
    )

    # 4. Modify _scrape_current_page to accept context parameter (Path A)
    old_scrape_method = '''    def _scrape_current_page(self, page: Any, url: str) -> list[dict[str, Any]]:
        """Scrape elements from the current page state."""
        html = page.content()
        return self._html_scraper._extract_elements_from_html(html, base_url=url)  # noqa: SLF001'''

    new_scrape_method = '''    def _scrape_current_page(
        self, page: Any, url: str, context: Any | None = None
    ) -> list[dict[str, Any]]:
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

        return elements'''

    content = content.replace(old_scrape_method, new_scrape_method)

    # 5. Update callers of _scrape_current_page in _scrape_journey_sync (Path A callers)
    old_starting_url_call = """                    elements = self._scrape_current_page(page, current_url)
                    output[current_url] = elements

                for step_index"""

    new_starting_url_call = """                    elements = self._scrape_current_page(page, current_url, context)  # B-0XX: pass context
                    output[current_url] = elements

                for step_index"""

    content = content.replace(old_starting_url_call, new_starting_url_call)

    old_scrape_action_call = """                            elif step.action == "scrape" and current_url:
                                elements = self._scrape_current_page(page, current_url)
                                output[current_url] = elements

                            # Auto-scrape after navigation if no explicit scrape step"""

    new_scrape_action_call = """                            elif step.action == "scrape" and current_url:
                                elements = self._scrape_current_page(  # B-0XX: pass context
                                    page, current_url, context
                                )
                                output[current_url] = elements

                            # Auto-scrape after navigation if no explicit scrape step"""

    content = content.replace(old_scrape_action_call, new_scrape_action_call)

    old_nav_auto_scrape_call = """                            # Auto-scrape after navigation if no explicit scrape step
                            if step.action == "navigate" and current_url:
                                elements = self._scrape_current_page(page, current_url)
                                output[current_url] = elements"""

    new_nav_auto_scrape_call = """                            # Auto-scrape after navigation if no explicit scrape step
                            if step.action == "navigate" and current_url:
                                elements = self._scrape_current_page(  # B-0XX: pass context
                                    page, current_url, context
                                )
                                output[current_url] = elements"""

    content = content.replace(old_nav_auto_scrape_call, new_nav_auto_scrape_call)

    # 6. Enrich in _discover_selector (Path B)
    old_discover = """        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001

        self._debug(f"Scraped {len(elements)} elements for discovery of '{description}'")"""

    new_discover = """        html = page.content()
        elements = self._html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001

        # B-0XX: Apply enrichment for better candidate quality in selector discovery
        try:
            elements = _capture_element_visibility_sync(page, elements)
        except Exception:
            pass  # Additive — continue with unenriched on failure

        self._debug(f"Scraped {len(elements)} elements for discovery of '{description}'")"""

    content = content.replace(old_discover, new_discover)

    src_file.write_text(content, encoding="utf-8")
    print("[OK] B-0XX enrichment applied to journey_scraper.py")


if __name__ == "__main__":
    apply_fix()
