# `src/aria_parser.py` — ARIA Snapshot Parser (AI-032)

## Purpose
Converts Playwright's `page.aria_snapshot(boxes=True)` YAML output into the same element dict format used by the rest of the pipeline. Handles all ARIA roles with computed accessible names, placeholders, values, URLs, and bounding boxes.

## Key Features
- Parses YAML into structured element dicts
- Handles: heading, textbox, combobox, button, radio, checkbox, link, group, and more
- Computes accessible names from ARIA attributes
- Extracts bounding boxes for visual enrichment
- 33 unit tests

## Related
- `src/scraper.py` — three-layer hybrid scraper (BS4 + CDP + ARIA snapshot)
- `src/accessibility_enricher.py` — CDP `getFullAXTree` enrichment


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `parse_aria_snapshot(yaml_text: str) -> list[dict[str, Any]]` (function)

Parse Playwright's aria_snapshot() YAML into element dicts.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (7 items). Grouped under the public function that uses them:

### `parse_aria_snapshot`
- `_apply_child_property(stripped: str, parent: dict[str, Any] | None) -> None` (function) — Apply a child property line to its parent element.
- `_build_element(role: str, ar_role: str, name: str, text: str, attrs: dict[str, str] | None, has_children: bool) -> dict[str, Any]` (function) — Build an element dict in the standard scraper format.
- `_is_child_property(stripped: str) -> bool` (function) — Check if line is a child property (/placeholder:, /url:, /checked:, /selected:).
- `_line_indent(line: str) -> int` (function) — Return the indentation level (2 spaces = 1 level).
- `_parse_aria_line(stripped: str) -> dict[str, Any] | None` (function) — Parse a single ARIA YAML line into an element dict.

### Internal utilities
- `_build_selector(role: str, name: str, attrs: dict[str, str]) -> str` (function) — Build a best-effort CSS selector from ARIA role and name.
- `_parse_box(box_str: str) -> dict[str, float] | None` (function) — Parse '[box=x,y,w,h]' style bounding box.
