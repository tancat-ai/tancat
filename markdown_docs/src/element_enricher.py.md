# `src/element_enricher.py`

## High-Level Purpose
Enriches scraped DOM elements with visual and contextual metadata (icon detection, bounding box hints, parent context) to improve placeholder matching when descriptions are vague.

## Module Metadata
- **Lines:** 337
- **Imports:** `__future__`, `typing`, `bs4.BeautifulSoup` (lazy)

## Classes

### `ElementEnricher` (classmethod-only utility)
| Method | Description |
|--------|-------------|
| `enrich_element(element, html_snippet, parent_classes)` | Returns enriched element dict with `is_icon`, `icon_classes`, `icon_unicode`, `is_decorative`, `is_hover_reveal`, `parent_text`, `aria_icon_label`, `visual_description` |
| `enrich_batch(elements, html_snippets)` | Batch version; maps index → html_snippet |
| `get_hover_reveal_selectors(elements)` | Extracts selectors for hover-reveal elements |
| `_detect_icon(element)` | Detects icon from class names (Font Awesome, Material, custom) |
| `_extract_parent_text(html_snippet)` | Uses BeautifulSoup to extract surrounding text |
| `_build_visual_description(element)` | Generates human-readable visual summary |

## Key Design Decisions
- Classmethod-only — no instance state needed
- Lazy import of BeautifulSoup to avoid hard dependency
- Enriches at scrape-time to avoid runtime overhead

## Dependencies
- `bs4` (lazy import)
- No project-internal dependencies