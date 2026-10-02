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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `CartSeedingScraper.__init__` (method of `CartSeedingScraper`): `CartSeedingScraper.__init__(starting_url: str, products_url: str | None = None, **kwargs) -> None` - Initialize the cart seeding scraper. Args: starting_url: The home page URL (used to establish session). products_url: Optional explicit products page URL. If not provided, derived from starting_url by appending "/prod...
- `CartSeedingScraper.scrape_cart_pages` (method of `CartSeedingScraper`): `CartSeedingScraper.scrape_cart_pages(cart_urls: list[str]) -> dict[str, list[dict[str, Any]]]` - Scrape cart/checkout pages with items already in the cart. Uses dynamic element discovery (no fixed selectors) so it works across different e-commerce sites without site-specific selectors. The journey scraper's _disc...


## How It Works (Internals)

Private `_`-helpers - the module's real logic (1 item). Grouped under the public function that calls them.

### `CartSeedingScraper.scrape_cart_pages(cart_urls: list[str]) -> dict[str, list[dict[str, Any]]]` - method of `CartSeedingScraper`

- `_ensure_full_url(url: str) -> str` (method of `CartSeedingScraper`): Ensure the URL is absolute. If the URL is relative, it will be made absolute during navigation by the JourneyScraper.
