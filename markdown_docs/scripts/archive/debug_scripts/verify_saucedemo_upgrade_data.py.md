# `scripts/archive/debug_scripts/verify_saucedemo_upgrade_data.py` — Upgrade Data Dump (one-off)

## Purpose
Replicated the orchestrator's scrape + `_upgrade_stateful_pages` phase for saucedemo and dumped per-URL element counts + checkout-relevant elements (2026-08-03).

## Key Findings (archived)
- Post-upgrade data is correct: `cart.html` 34 elements (Checkout ✓), `checkout-step-one.html` 29 (Continue ✓); dead candidate URLs (`/basket`, `/view_cart`, …) are 2-element shells
- Proved the resolution problem was keyword/navigation URL selection (dead shells winning), not scrape data — grounding the dead-page filter + redirect-duplicate filter

## Related
- `src/placeholder_orchestrator.py` — `_drop_dead_pages`, `_drop_redirect_duplicates`
