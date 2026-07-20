# `src/cart_seeding_scraper.py`

## High-Level Purpose

`cart_seeding_scraper.py` provides a specialized journey scraper that ensures the cart has items before scraping cart/checkout pages. Extends `JourneyScraper` to follow a product-selection → add-to-cart → dismiss-modal journey, then navigates to target cart/checkout URLs for scraping.

Added **2026-07-20 (B-022):** Switched from hardcoded selectors to dynamic element discovery via `_discover_selector()`, making it site-agnostic. The cart seeder now works across different e-commerce sites without site-specific CSS selectors.

## Dependencies

- `JourneyScraper` from `src.journey_scraper` — base class for stateful journey scraping
- `JourneyStep` from `src.journey_models` — step definition for journey actions
- `PRODUCT_SELECTORS`, `ADD_TO_CART_SELECTORS`, `CONTINUE_SHOPPING_SELECTORS` from `src.form_detector` — kept for test compatibility, no longer used by `scrape_cart_pages()`

## Classes

### `CartSeedingScraper(JourneyScraper)`

Specialized journey scraper for cart-dependent pages.

**Class-level constants (test compatibility):**
- `PRODUCT_SELECTORS: list[str]`
- `ADD_TO_CART_SELECTORS: list[str]`
- `CONTINUE_SHOPPING_SELECTORS: list[str]`

#### `__init__(self, starting_url: str, products_url: str | None = None, **kwargs: Any) -> None`

Args:
- `starting_url`: Home page URL for session establishment.
- `products_url`: Optional products page URL. Defaults to `urljoin(home_url, "/products")`.

#### `scrape_cart_pages(self, cart_urls: list[str]) -> dict[str, list[dict[str, Any]]]`

Seeds the cart (add item → dismiss confirmation), then scrapes each target URL.

**B-022 change:** Uses dynamic element discovery — no hardcoded selectors. Steps:
1. Navigate to products page
2. Click on a product (dynamic discovery via `_discover_selector()`)
3. Click "Add to cart" (dynamic discovery)
4. Capture confirmation popup state
5. Dismiss confirmation modal (dynamic discovery)
6. Wait for modal animation
7. Navigate to and scrape each target cart/checkout URL

Returns `dict[str, list[dict[str, Any]]]` mapping URLs to scraped elements.

#### `_derive_products_url(home_url: str) -> str` (static)

Derives products page URL: `urljoin(home_url, "/products")`

#### `_ensure_full_url(url: str) -> str` (static)

Ensures URL is absolute. Relative URLs are handled by `JourneyScraper._navigate_to()`.
