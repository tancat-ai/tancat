# `scripts/archive/debug_scripts/replay_saucedemo_checkout.py` — Checkout Sequence Replay (one-off)

## Purpose
Replayed the saucedemo checkout test's placeholder sequence (login → add to cart → cart icon → checkout button → first/last/zip → continue) against the REAL scraped data, printing `current_url` + matched element per step.

## Key Findings (archived)
- Confirmed the resolution chain works when scoped to the right page (cart.html → `#checkout` → checkout-step-one → `#first-name`/`#last-name`)
- Exposed the navigation-intent gap: `cart icon` had no accessible name, so element matching failed and the page context never advanced past inventory — the fix was the navigation-intent GOTO fallback in `src/placeholder_orchestrator.py`

## Related
- `src/placeholder_orchestrator.py` — `_is_navigation_description` + nav fallback
