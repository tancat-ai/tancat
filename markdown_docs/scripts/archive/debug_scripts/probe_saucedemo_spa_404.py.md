# `scripts/archive/debug_scripts/probe_saucedemo_spa_404.py` — SPA Soft-404 Probe (one-off)

## Purpose
Measured saucedemo's SPA-on-GitHub-Pages soft-404 behavior (2026-08-03, the saucedemo checkout investigation). Answered: what status `page.goto()` reports for `.html` paths, whether the SPA bootstraps after networkidle, and whether waiting changes the rendered state.

## Key Findings (archived)
- `/inventory.html` etc. → `goto` status 404, but the SPA boots (title "Swag Labs") and the URL is rewritten — the returned `Response` still reports 404
- `/?/inventory.html` → status 200, same final state
- Grounded the `PageScraper._is_soft_404` recovery fix in `src/scraper.py`

## Related
- `src/scraper.py` — soft-404 recovery
- Archived alongside `replay_saucedemo_checkout.py`, `verify_saucedemo_stateful_scrape.py`, `verify_saucedemo_upgrade_data.py`
