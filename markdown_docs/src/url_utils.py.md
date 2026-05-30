# `src/url_utils.py`

## Purpose
Pure URL manipulation helpers extracted from TestOrchestrator. Validates domains, filters to allowed domains, extracts route concepts, and provides URL fallback guesses.

## Metadata
- **Lines:** 87
- **Imports:** logging, urllib.parse (urljoin, urlparse)

## Functions
| Function | Description |
|----------|-------------|
| `extract_seed_domain(seed_urls)` | Extract normalized domain strings from seed URLs |
| `filter_urls_to_allowed_domain(urls, allowed_domains)` | Keep only URLs matching allowed domains or subdomains |
| `extract_route_concepts(texts)` | Extract e-commerce concepts (home, products, cart, checkout) from text |
| `build_common_path_candidates(seed_urls, concepts)` | Stub — returns empty list (journey scraper replaces guessing) |
| `heuristic_url_from_description(current_url, description)` | Best-effort URL guess from description keywords |

## Key Logic
- Domain validation allows exact match or subdomain match
- Route concepts extracted via keyword presence: "product"/"shop" → products, "cart"/"basket" → cart, "checkout"/"payment" → checkout
- `build_common_path_candidates` is deprecated — journey scraper replaces URL guessing
- `heuristic_url_from_description` maps keywords to common paths: products→`/products`, cart→`/view_cart`, checkout→`/checkout`