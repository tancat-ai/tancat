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
