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

## How It Works (Internals)

Private `_`-helpers — the module's real logic (3 items). Grouped under the public function that uses them:

### `scope_elements`
- `_extract_section_hint(description: str) -> str | None` (function) — Extract a section hint from a placeholder description.
- `_match_section_hint(hint: str, sections: list[Section]) -> str | None` (function) — Match a normalised hint against detected section names.

### Internal utilities
- `_normalise_name(name: str) -> str` (function) — Normalise a section name for comparison.
