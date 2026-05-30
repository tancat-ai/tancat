# `src/url_inference.py`

## Purpose
URL transition inference for journey-aware placeholder resolution. Infers next page URL after navigation clicks.

## Metadata
- **Lines:** 108
- **Imports:** logging, urllib.parse.urljoin

## Functions
| Function | Description |
|----------|-------------|
| `infer_next_page_url(action, description, matched_element, scraped_data, current_url)` | Main entry: infers next page after a resolved step |
| `_infer_click_transition_url(description, matched_element, scraped_data, current_url)` | Infers common transitions (login→inventory, checkout→step-two, etc.) |
| `_find_discovered_url(scraped_data, preferred_terms)` | Returns best scraped URL matching preferred terms |

## Key Logic
- CLICK with href → returns href (resolved against current_url if relative)
- CLICK without href → uses keyword matching on description/selector/id to infer transitions
- Add to cart clicks → returns None (stays on same page)
- Navigation clicks (cart, checkout, home) → falls back to PlaceholderResolver.resolve_url

## Dependencies
- `src.placeholder_resolver` (conditional import for resolve_url fallback)