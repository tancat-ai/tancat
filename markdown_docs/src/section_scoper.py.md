# `src/section_scoper.py` — Section Scoper

## Purpose
Scopes element extraction to specific page sections. Helps the scraper focus on relevant content areas and avoid noise from headers, footers, and navigation.

## Related
- `src/scraper.py` — `PageScraper` consumer


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 3 items):

### `detect_sections(elements: list[dict[str, Any]]) -> list[Section]` (function)

Detect page sections from heading elements.

### `scope_elements(description: str, all_elements: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]` (function)

Filter elements to the section referenced in a placeholder description.

### `build_element_to_section_map(elements: list[dict[str, Any]]) -> dict[int, str]` (function)

Build a mapping from element index to section name.
