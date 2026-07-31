# `src/cart_seeding_scraper.py` — Cart-Seeding Scraper (B-022)

## Purpose
Ensures the cart has items before scraping cart/checkout pages. Extracted from `journey_scraper.py`. Extends `JourneyScraper` for the "seed cart then scrape" workflow.

## Class: `CartSeedingScraper(JourneyScraper)`
- Uses dynamic element discovery via `_discover_selector()` instead of hardcoded selectors
- Product URL detection: scrapes category/product URLs from existing data
- Prefers cart-seeded data over static scrapes for `/view_cart` and `/checkout` pages

## Related
- `src/journey_scraper.py` — parent class
- `src/orchestrator.py` — `_upgrade_stateful_pages()` integration
