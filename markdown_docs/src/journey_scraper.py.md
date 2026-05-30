---
purpose: >
  Journey-aware stateful scraper that navigates multi-page flows, tracking DOM state
  changes after user interactions. Discovers pages organically by following navigation links.
lines: ~500
created: "2026-05-30"
---

# `src/journey_scraper.py`

## High-Level Purpose

Extends `PageScraper` with journey awareness: navigates pages in sequence, tracks state changes (cart count, form values), and discovers URLs organically from GOTO placeholders instead of requiring a PAGES_NEEDED list.

## Key Features

- **Organic page discovery:** Extracts GOTO placeholders from skeleton, matches descriptions to scraped links, navigates to discovered pages
- **State tracking:** Uses `StateTracker` to record DOM state after each navigation (cart badges, form values, visible elements)
- **Form detection:** Uses `FormDetector` to identify form fields and their relationships
- **Selector propagation:** Carries working selectors across pages for consistent element matching

## Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `scrape_journey(start_url, goto_descriptions)` | `dict[str, list[dict]]` | Scrape all pages, returning elements per URL |
| `_navigate_and_scrape(url)` | `ScrapeResult` | Navigate to URL, wait for networkidle, scrape |
| `_discover_selector(description, current_elements)` | `str \| None` | Find best selector for a GOTO description |
| `_discover_urls_from_skeleton(skeleton_code)` | `list[tuple[str, str]]` | Extract (url, description) pairs from GOTO placeholders |

## Discovery Strategies

1. Link text match — `a` elements whose text matches GOTO description
2. ARIA label match — elements with `aria-label` matching description
3. Data-attribute match — `data-testid`, `data-test`, `data-qa`
4. Fallback: first navigable link on page

## Dependencies

- `src.scraper.PageScraper` — core scraping
- `src.state_tracker.StateTracker` — DOM state tracking
- `src.form_detector.FormDetector` — form field detection

## Depended On By

- `src/orchestrator.py` — calls for journey-aware scraping
- `src/placeholder_orchestrator.py` — page-context scraping