# `src/url_utils.py`

## Purpose
Pure URL manipulation helpers extracted from TestOrchestrator. Validates domains, filters to allowed domains, extracts route concepts, and provides URL fallback guesses.

## Metadata
- **Lines:** ~140
- **Imports:** logging, re, urllib.parse (urljoin, urlparse)

## Functions
| Function | Description |
|----------|-------------|
| `is_stateful_cart_checkout_path(path)` | Site-agnostic predicate: True when a URL path is a cart/checkout page needing session state (matches `view_cart`, `cart`, `checkout`, `basket` tokens — covers automationexercise `/view_cart` and saucedemo `/cart.html`) |
| `normalize_url_path(url)` | Normalize LLM-generated URL path variations to real routes |
| `extract_seed_domain(seed_urls)` | Extract normalized domain strings from seed URLs |
| `filter_urls_to_allowed_domain(urls, allowed_domains)` | Keep only URLs matching allowed domains or subdomains |
| `extract_route_concepts(texts)` | Extract e-commerce concepts (home, products, cart, checkout) from text |
| `build_common_path_candidates(seed_urls, concepts)` | **Re-enabled 2026-08-03**: same-domain candidate URLs for story concepts (SPA sites expose no hrefs for journey discovery) — mirrors journey_scraper's route vocabulary |
| `heuristic_url_from_description(current_url, description)` | Best-effort URL guess from description keywords |

## Key Logic
- `is_stateful_cart_checkout_path` is the single source of truth for stateful/cart-seeding routing — used by `placeholder_orchestrator` and `ui_run_results` (no per-site path lists)
- `build_common_path_candidates` was a stub (URL guessing removed in June); re-enabled because SPA sites (saucedemo) have no hrefs for journey discovery — candidates are concept-driven and filtered to the seed domain to prevent cross-site hallucination
- Domain validation allows exact match or subdomain match
- Route concepts extracted via keyword presence: "product"/"shop" → products, "cart"/"basket" → cart, "checkout"/"payment" → checkout
- `heuristic_url_from_description` maps keywords to common paths: products→`/products`, cart→`/view_cart`, checkout→`/checkout`

## Related
- `src/placeholder_orchestrator.py`, `src/orchestrator.py` — stateful routing + URL candidates
- `src/ui/ui_run_results.py` — cart-seeding detection for the repair setup script
