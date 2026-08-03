# `src/role_mapper.py` — ARIA Role Mapping (B-016)

## Purpose
ARIA role mapping and display-role filtering for ASSERT resolution. Extracted from `placeholder_orchestrator.py`. Provides HTML-tag-to-ARIA-role mapping and utilities for identifying display (non-interactive) elements.

## Constants
- `DISPLAY_ROLES: frozenset[str]` — roles considered display-only (heading, paragraph, text, status, region, listitem, cell, generic)
- `_TAG_TO_ROLE: dict[str, str]` — HTML tag → default ARIA role mapping

## Functions
- `is_display_role(element: dict) -> bool` — check if element has a display role
- `normalise_element_text(element: dict) -> str` — extract/normalize element text for Pass 1 matching
- `get_effective_role(element: dict) -> str` — resolve computed_role vs raw role

## Key Logic
- `normalise_element_text` priority: `accessible_name → aria_label → text → placeholder` (2026-08-03: placeholder added as last resort — many form fields, e.g. saucedemo checkout / lv_insurance, have no label or accessible name, only a placeholder like "Last Name")
- Strips non-ASCII characters (icon fonts), lowercases, strips whitespace

## Related
- `src/placeholder_orchestrator.py` — consumer
- `src/intent_matcher.py` — intent-based element filtering
- `src/element_matcher.py` — Pass 1 text matching uses `normalise_element_text`
