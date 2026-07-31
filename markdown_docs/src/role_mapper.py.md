# `src/role_mapper.py` — ARIA Role Mapping (B-016)

## Purpose
ARIA role mapping and display-role filtering for ASSERT resolution. Extracted from `placeholder_orchestrator.py`. Provides HTML-tag-to-ARIA-role mapping and utilities for identifying display (non-interactive) elements.

## Constants
- `DISPLAY_ROLES: frozenset[str]` — roles considered display-only (heading, paragraph, text, status, region, listitem, cell, generic)
- `_TAG_TO_ROLE: dict[str, str]` — HTML tag → default ARIA role mapping

## Functions
- `is_display_role(element: dict) -> bool` — check if element has a display role
- `normalise_element_text(text: str) -> str` — normalize text for comparison
- `get_effective_role(element: dict) -> str` — resolve computed_role vs raw role

## Related
- `src/placeholder_orchestrator.py` — consumer
- `src/intent_matcher.py` — intent-based element filtering
