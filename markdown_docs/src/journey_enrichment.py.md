# `src/journey_enrichment.py` — Journey Enrichment Helpers

## Purpose
DOM enrichment helpers for journey scraping. Extracted from `journey_scraper.py`. Reused by both `JourneyScraper` and `journey_executor` to ensure consistent enrichment pipeline (visibility checks + accessibility snapshot via CDP).

## Functions
- `capture_element_visibility_sync(page, elements: list[dict]) -> list[dict]` — annotate elements with `is_visible` via Playwright's `locator().is_visible()`
- `capture_a11y_snapshot_sync(context, page) -> str | None` — capture CDP accessibility tree snapshot

## Related
- `src/journey_scraper.py` — primary consumer
- `src/journey_executor.py` — secondary consumer
- `src/accessibility_enricher.py` — A11y tree enrichment
