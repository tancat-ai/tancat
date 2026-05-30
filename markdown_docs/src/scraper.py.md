# `src/scraper.py`

## High-Level Purpose

Playwright-based DOM scraper that discovers real element selectors from live web pages. Uses a headless Chromium browser to render JavaScript, extract interactive elements, capture accessibility trees via CDP, and record screenshots with bounding boxes. Runs scraping in a subprocess to avoid asyncio event loop conflicts on Windows.

## Module Metadata

- **Lines:** 657
- **Key imports:** `base64`, `json`, `os`, `subprocess`, `sys`, `dataclasses.dataclass`, `pathlib.Path`, `typing`, `urllib.parse`, `playwright.sync_api`
- **Project imports:** `src.accessibility_enricher.AccessibilityEnricher`, `src.element_enricher.ElementEnricher`, `src.vision_enricher.VisionEnricher`

## Dataclass: `ScrapeResult`

Fields: `url`, `elements`, `title`, `html_snippet`, `error`, `final_url`, `a11y_snapshot`, `screenshot_bytes`, `element_boxes`

## Class: `PageScraper`

### `__init__(timeout_ms=30000)`
- Configures timeout, stores last scrape results

### `scrape_url(url) -> tuple[list[dict], str|None, str]`
- **Public async API** — delegates to `_scrape_url_via_subprocess()`
- Returns: (elements_list, error_message, final_url)

### `_scrape_url_via_subprocess(url)` 
- Runs sync Playwright scrape in a clean subprocess to avoid Windows nested event loop issues
- Parses JSON output from subprocess, enriches elements with accessibility data and bounding boxes

### `_scrape_url_sync(url)` 
- Core sync scraping logic executed in subprocess
- Launches headless Chromium, navigates with `networkidle` wait, extracts elements, captures CDP accessibility tree

### `_scrape_url_sync_result(url) -> ScrapeResult`
- Full scrape result including screenshot bytes and element bounding boxes

### `_extract_elements_from_html(html, base_url) -> list[dict]`
- Uses BeautifulSoup to parse HTML after removing consent overlays
- Extracts interactive elements: `button`, `a`, `input`, `select`, `textarea`
- Builds CSS selectors with priority: id > data-testid > data-test > data-qa > data-product-id > href > name > classes > tag

### `_build_selector(tag, href) -> str`
- Builds best CSS selector for a live Playwright tag using same priority as above

### `_capture_element_visibility(page, elements) -> list[dict]`
- Adds `is_visible` boolean to each element using Playwright `is_visible()` at runtime

### `_remove_consent_overlays(html) -> str`
- Strips cookie/consent banner elements (IAB GVL, cc-banner, etc.) before extraction to prevent element pollution

### `scrape_all(urls) -> dict[str, tuple[...]]`
- Scrapes multiple URLs sequentially

## Standalone Functions

### `capture_page_screenshot(page, url, full_page=True) -> tuple[bytes, list[dict]]`
- Captures page screenshot plus bounding boxes for all interactive elements

### `scrape_with_enrichment(scrape_results, provider, model, timeout) -> list[ScrapeResult]`
- Applies vision enrichment from VisionEnricher to results that include screenshot data

### `_subprocess_entrypoint()`
- Entry point when module is run as `python scraper.py --scrape`
- Reads JSON payload from stdin, runs scrape, writes JSON result to stdout

## Key Design Decisions

- **Subprocess isolation:** Playwright runs in a separate process to avoid asyncio conflicts with Streamlit/Jupyter event loops
- **Consent overlay removal:** Cookie banners are stripped before element extraction to prevent hundreds of irrelevant elements
- **CDP accessibility tree:** Uses Chrome DevTools Protocol `Accessibility.getFullAXTree` since `page.accessibility.snapshot()` is unavailable in Python Playwright
- **Vision enrichment:** Screenshots and element boxes enable vision-capable LLMs to enrich element metadata

## Dependencies

- `playwright.sync_api` — browser automation
- `bs4.BeautifulSoup` — HTML parsing
- `src.accessibility_enricher` — merges CDP accessibility data into elements
- `src.element_enricher` — adds visual/contextual metadata
- `src.vision_enricher` — optional vision-based enrichment

## Depended On By

- `src/journey_scraper.py` — uses PageScraper for initial page scrapes
- `src/placeholder_orchestrator.py` — fallback scraper
- `src/orchestrator.py` — calls via JourneyScraper