# `src/url_resolver.py`

## Purpose
Resolves page keywords to actually discovered URLs from journey scraping. Bridges LLM-generated page keywords (e.g., "cart", "checkout") with real URLs.

## Metadata
- **Lines:** 221
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
| `UrlResolver._match_keyword_to_url(kw_lower, scraped_urls)` | Static: match single keyword using 4-tier strategy |
| `resolve_keywords_to_urls(keywords, scraped_urls, seed_url, concepts)` | Convenience: creates and populates UrlResolver |

## Matching Strategy (priority order)
1. Exact path match: "cart" → `/cart`
2. Direct path segment match: "cart" → `/shop/cart`
3. Normalized substring: "checkout overview" → `/checkout-overview`
4. Prefix match: "product" → `/products` (shortest path wins)

## Fallback
When no scraped URLs available, uses `build_common_path_candidates` from `src.url_utils` to generate common e-commerce paths.