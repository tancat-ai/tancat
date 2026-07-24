# `src/aria_parser.py`

## High-Level Purpose

Parses Playwright's `page.aria_snapshot(boxes=True)` YAML output into standard element dicts for the scraping pipeline (B-032). Replaces the need for manual accessible_name enrichment — the ARIA tree provides computed accessible names, roles, placeholders, values, URLs, and bounding boxes directly from the browser's accessibility engine.

## Module Metadata

- **Lines:** 330
- **Key imports:** `re`, `typing`
- **Project imports:** None (self-contained)
- **Tests:** `tests/test_aria_parser.py` (33 tests)

## Public API

### `parse_aria_snapshot(yaml_text: str) -> list[dict[str, Any]]`

Main entry point. Parses the YAML output from `page.aria_snapshot(boxes=True)` into a flat list of element dicts in depth-first order. Each element dict matches the format produced by `PageScraper._extract_elements_from_html()` (BS4-based).

**Returns**: List of element dicts with fields: `selector`, `text`, `role`, `computed_role`, `accessible_name`, `href`, `placeholder`, `value`, `is_visible`, `_bbox`, `_parent`, `_has_children`.

## YAML Grammar Handled

| Pattern | ARIA Role | Example |
|---------|-----------|---------|
| `- heading "name" [level=N] [box=x,y,w,h]` | heading | Page/section titles |
| `- textbox "name" [box=x,y,w,h]:` | textbox | Input fields with optional children |
| `- combobox "name" [box=x,y,w,h]:` | combobox | Select dropdowns with option children |
| `- button "name" [box=x,y,w,h]` | button | Clickable buttons |
| `- radio "name" [box=x,y,w,h]` | radio | Radio buttons (accessible name from label) |
| `- checkbox "name" [box=x,y,w,h]` | checkbox | Checkboxes (accessible name from label) |
| `- link "name" [box=x,y,w,h]:` | link | Anchor elements with `/url:` child |
| `- group "name" [box=x,y,w,h]:` | group | Container elements with nested children |
| `- text: content` | text | Plain text nodes |
| `- paragraph [box=x,y,w,h]: text` | paragraph | Text blocks with content after colon |

### Child Properties

| Property | Target | Meaning |
|----------|--------|---------|
| `- /placeholder: value` | textbox | Input placeholder text |
| `- /url: href` | link | Link destination URL |
| `- text: value` | textbox/combobox | Current input value |
| `- /checked:` | checkbox/radio | Checked state flag |
| `- /selected:` | option | Selected state flag |

## Architecture Notes

- **Indentation-aware**: Tracks nesting depth (2 spaces per level) for parent-child relationships via `_parent` references.
- **Self-contained**: No external dependencies beyond stdlib `re`. Used by `PageScraper._extract_elements_from_aria()`.
- **Form control value handling**: `text:` children of textbox/combobox are applied as `value` on the parent, not as standalone elements.
- **Selector format**: Produces role-based selectors like `heading[name="Create Account"]` — compatible with `page.getByRole()`.
