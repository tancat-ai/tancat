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

## How It Works (Internals)

Private `_`-helpers - the module's real logic (9 items). Grouped under the public function that calls them.

### `ElementEnricher.enrich_element(element: dict[str, Any], html_snippet: str = '', parent_classes: list[str] | None = None) -> dict[str, Any]` - method of `ElementEnricher`

- `_detect_is_icon(element: dict[str, Any]) -> bool` (method of `ElementEnricher`): Detect whether an element is a pure icon (no meaningful text content).
- `_detect_icon_classes(element: dict[str, Any]) -> str` (method of `ElementEnricher`): Extract icon font class names from element CSS classes.
- `_detect_icon_unicode(element: dict[str, Any]) -> str` (method of `ElementEnricher`): Extract unicode icon characters from element text content.
- `_detect_decorative(element: dict[str, Any]) -> bool` (method of `ElementEnricher`): Detect whether an element is purely decorative (should be ignored).
- `_detect_hover_reveal(element: dict[str, Any], html_snippet: str = '') -> bool` (method of `ElementEnricher`): Detect whether an element is likely hidden inside a hover-reveal overlay. This identifies elements that are commonly hidden via CSS (display:none, visibility:hidden, opacity:0) and only become visible when the parent...
- `_extract_parent_text(html_snippet: str) -> str` (method of `ElementEnricher`): Extract visible text from parent elements in the HTML snippet.
- `_extract_aria_icon_label(element: dict[str, Any]) -> str` (method of `ElementEnricher`): Extract aria-label, title, or alt text for icon-only elements.
- `_generate_visual_description(element: dict[str, Any]) -> str` (method of `ElementEnricher`): Generate a human-readable visual description of the element. This is used in LLM prompts to help the model understand what the element looks like, enabling better placeholder descriptions.

### Internal utilities

- `_is_unicode_icon_text(text: str) -> bool` (method of `ElementEnricher`): Check if text consists entirely of unicode icon characters.
