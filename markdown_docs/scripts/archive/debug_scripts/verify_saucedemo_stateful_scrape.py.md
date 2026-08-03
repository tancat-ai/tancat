# `scripts/archive/debug_scripts/verify_saucedemo_stateful_scrape.py` — Stateful Scrape Validation (one-off)

## Purpose
Validated `StatefulPageScraper` + cart seeding against saucedemo's SPA routing (2026-08-03). Confirmed that with demo credentials the stateful scraper (which ignores response status and seeds the cart first) extracts real cart/checkout elements — `cart.html` has the Checkout button, step-one has Continue, step-two has Finish. Without credentials it captures the "Epic sadface" login wall.

Supports `--no-creds` to simulate the production path (no credential profile).

## Related
- `src/stateful_scraper.py` — `_seed_cart_session`
- `src/journey_models.py` — `CredentialProfile`
