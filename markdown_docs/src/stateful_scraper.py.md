---
purpose: >
  State-aware DOM scraper used as fallback in placeholder_orchestrator.py.
  Tracks form state, visible elements, and DOM mutations across interactions.
lines: ~350
created: "2026-05-30"
---

# `src/stateful_scraper.py`

## High-Level Purpose

Fallback scraper that maintains DOM state awareness across page interactions. Tracks which forms are visible, which elements changed after actions, and provides context-rich element data for placeholder resolution.

## Key Features

- **Form state tracking:** Records form field values before/after interactions
- **Visibility detection:** Only considers visible elements for candidate matching
- **DOM mutation awareness:** Detects elements added/removed after user actions
- **Context preservation:** Carries page URL, title, and visible text for LLM reasoning

## Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `scrape_page(url)` | `ScrapeResult` | Navigate and scrape with state awareness |
| `record_interaction(action, selector)` | `dict` | Record DOM state after click/fill |
| `get_visible_elements()` | `list[dict]` | Only visible, interactable elements |

## Dependencies

- `src.scraper.PageScraper` — base scraping
- `src.state_tracker.StateTracker` — state persistence

## Depended On By

- `src/placeholder_orchestrator.py` — fallback when journey_scraper unavailable

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `StatefulPageScraper` (class)

Scrape pages using a Playwright browser context with a cart session.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### Internal utilities
- `_run_subprocess_entry() -> int` (function) — Entry point for the subprocess-backed stateful scrape.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `StatefulPageScraper.__init__` (method of `StatefulPageScraper`): `StatefulPageScraper.__init__(starting_url: str, *, timeout_ms: int = 30000, max_retries: int = 2, base_backoff_ms: int = 1000, credential_profile: CredentialProfile | None = None) -> None`
- `StatefulPageScraper.scrape_url` (method of `StatefulPageScraper`): `StatefulPageScraper.scrape_url(url: str) -> list[dict[str, Any]]` - Async wrapper around the subprocess-backed scrape implementation.
- `StatefulPageScraper.scrape_urls` (method of `StatefulPageScraper`): `StatefulPageScraper.scrape_urls(urls: list[str]) -> dict[str, list[dict[str, Any]]]` - Scrape multiple URLs in a single Playwright session.


### Additional helpers (docs refresh 2026-10-02)

Private helpers with real logic not listed above.

- `_scrape_urls_via_subprocess(urls: list[str]) -> dict[str, list[dict[str, Any]]]` (method of `StatefulPageScraper`): Run the sync Playwright workflow in a clean subprocess main thread.
- `_scrape_urls_sync(urls: list[str]) -> dict[str, list[dict[str, Any]]]` (method of `StatefulPageScraper`): Sync implementation for multi-URL session scrape with retry/backoff support.
- `_capture_a11y_snapshot(context: Any, page: Any) -> dict[str, Any]` (method of `StatefulPageScraper`): Capture accessibility snapshot via CDP. Returns an empty dict if CDP is unavailable or returns no nodes, matching the PageScraper fallback behaviour.
- `_seed_cart_session(page: Any) -> None` (method of `StatefulPageScraper`): Navigate, login if needed, then try to add one item to cart (best effort).
- `_dismiss_consent_overlays(page: Any) -> None` (method of `StatefulPageScraper`): Delegate to central consent dismissal utility.
