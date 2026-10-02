# `src/url_resolver.py`

## Purpose
Resolves page keywords to actually discovered URLs from journey scraping. Bridges LLM-generated page keywords (e.g., "cart", "checkout") with real URLs.

## Metadata
- **Lines:** ~280
- **Imports:** logging, urllib.parse.urlparse, src.url_utils

## Classes
| Class | Description |
|-------|-------------|
| `UrlResolver` | Builds keyword→URL mapping from journey scraping results |

## Functions
| Function | Description |
|----------|-------------|
| `UrlResolver.build_mapping(keywords, scraped_urls, seed_url, concepts)` | Match keywords to discovered URLs |
| `UrlResolver.resolve(keyword)` | Resolve a keyword to an actual URL |
| `UrlResolver.get_seed_url()` | Return seed URL as fallback |
| `UrlResolver.get_all_mappings()` | Return copy of all keyword→URL mappings |
| `UrlResolver._match_keyword_to_url(kw_lower, scraped_urls)` | Static: match single keyword using multi-tier strategy |
| `resolve_keywords_to_urls(keywords, scraped_urls, seed_url, concepts)` | Convenience: creates and populates UrlResolver |

## Matching Strategy (priority order)
1. Exact path match: "cart" → `/cart`
2. Direct path segment match: "cart" → `/shop/cart`
3. Normalized substring: "checkout overview" → `/checkout-overview`
4. Prefix match: "product" → `/products` (shortest path wins)
5. **Semantic alias match (2026-08-03):** sites name routes differently from the story vocabulary — "products" matches `/inventory.html` (saucedemo), "cart" matches `/basket`, "login" matches `/signin`. Generic alias groups, no per-site lists.

## Fallback
When no scraped URLs available, uses `build_common_path_candidates` from `src.url_utils` to generate same-domain e-commerce path candidates.


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `normalize_url(url: str) -> str` (function)

Return a canonical URL — root http(s) URLs get a trailing slash.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `UrlResolver.__init__` (method of `UrlResolver`): `UrlResolver.__init__() -> None`
- `UrlResolver.build_mapping` (method of `UrlResolver`): `UrlResolver.build_mapping(keywords: list[str], scraped_urls: list[str], seed_url: str, concepts: list[str] | None = None) -> None` - Match keywords to discovered URLs using heuristic matching. Args: keywords: Page keywords from PAGES_NEEDED (e.g., ["cart", "checkout"]). scraped_urls: URLs actually visited by the journey scraper. seed_url: The user-...
- `UrlResolver.resolve` (method of `UrlResolver`): `UrlResolver.resolve(keyword: str) -> str | None` - Resolve a keyword to an actual URL. Args: keyword: A page keyword (e.g., "cart", "checkout", "home"). Returns: The resolved URL, or None if the keyword cannot be matched.
- `UrlResolver.get_seed_url` (method of `UrlResolver`): `UrlResolver.get_seed_url() -> str | None` - Return the seed URL as fallback. Returns: The seed URL mapped to "home", or None if not set.
- `UrlResolver.get_all_mappings` (method of `UrlResolver`): `UrlResolver.get_all_mappings() -> dict[str, str]` - Return a copy of all keyword->URL mappings. Returns: A dictionary mapping keywords to URLs.


## How It Works (Internals)

Private `_`-helpers - the module's real logic (1 item). Grouped under the public function that calls them.

### `UrlResolver.build_mapping(keywords: list[str], scraped_urls: list[str], seed_url: str, concepts: list[str] | None = None) -> None` - method of `UrlResolver`

- `_match_keyword_to_url(kw_lower: str, scraped_urls: list[str]) -> str | None` (method of `UrlResolver`): Match a single keyword to the best scraped URL. Strategy (in priority order): 1. Exact path match: keyword "cart" matches /cart (single-segment path) 2. Direct path segment match: keyword "cart" matches /shop/cart 3....
