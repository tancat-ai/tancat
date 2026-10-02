# `src/accessibility_enricher.py`

## High-Level Purpose

Enriches scraped DOM element records with computed accessibility names from the browser's accessibility tree (`page.accessibility.snapshot()`). Merges computed names (derived from ARIA relationships like `aria-labelledby`, `aria-describedby`, parent label context, SVG `<title>` children, and implicit roles) back into element records produced by `PageScraper` so that `PlaceholderResolver` has additional text signals for matching placeholders like `{{CLICK:View Cart}}` against elements whose accessible name differs from raw HTML attributes.

**Key Design Principle:** Enrichment is additive-only — it never removes or overwrites existing data.

## Module Metadata

- **Lines:** 411
- **`__test__ = False`** — excluded from pytest collection
- **Imports:** `logging`, `typing.Any`

## Class: `AccessibilityEnricher`

```python
class AccessibilityEnricher:
    """Merge computed accessible names from an a11y tree into scraped elements."""
```

### Class Constants

| Constant | Type | Description |
|----------|------|-------------|
| `INTERACTIVE_ROLES` | `set[str]` | Roles considered "interactive" for document-order matching (button, link, checkbox, textbox, combobox, etc.) |

### Static Methods

#### `_transform_cdp_ax_tree(cdp_nodes: list[dict[str, Any]]) -> dict[str, Any]`
Transforms CDP `Accessibility.getFullAXTree` result into the format expected by `enrich()`. Converts nested role/name wrappers to flat values, wires children via `childIds`, and returns a single root node.

#### `enrich(elements: list[dict[str, Any]], a11y_tree: dict[str, Any]) -> list[dict[str, Any]]`
Main entry point. Merges computed accessible names from a11y tree into scraped elements using three matching strategies (priority order):
1. **Role + name** — match element text+role against a11y node name+role
2. **href** — match link elements by href value in a11y properties
3. **Document-order** — fallback positional matching

Returns the same element list mutated in-place.

#### `_flatten_a11y_tree(node: dict[str, Any]) -> list[dict[str, Any]]`
Flattens the a11y tree into a document-order list of interactive nodes (nodes with meaningful name or interactive role).

#### `_build_role_name_index(nodes: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]`
Builds an index of `(role, name)` tuples to lists of a11y nodes for fast lookup.

#### `_build_href_index(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]`
Builds an index of href values to a11y nodes (extracted from `properties` array `url` entries).

#### `_match_by_role_and_name(element, role_name_index, used_indices) -> dict[str, Any] | None`
Strategy 1: match by element text against a11y node computed name, with role comparison to narrow false positives. Falls back to name-only match ignoring role.

#### `_match_by_href(element, href_index, used_indices) -> dict[str, Any] | None`
Strategy 3: match link elements by exact href, then partial path comparison.

#### `_match_by_document_order(element, a11y_nodes, used_indices) -> dict[str, Any] | None`
Strategy 2: fallback — find first unused a11y node whose name overlaps with element text or selector.

#### `_apply_enrichment(element: dict[str, Any], a11y_node: dict[str, Any]) -> None`
Applies computed fields from matched a11y node to scraped element:
- `accessible_name` added only if not present
- `computed_role` added unconditionally
- `aria_describedby` resolved from properties (describedby > labelledby > label)

## Dependencies
- `page.accessibility.snapshot()` output (Playwright)
- Element dicts from `PageScraper`

## How It Works (Internals)

Private `_`-helpers - the module's real logic (8 items). Grouped under the public function that calls them.

### `AccessibilityEnricher.enrich(elements: list[dict[str, Any]], a11y_tree: dict[str, Any]) -> list[dict[str, Any]]` - method of `AccessibilityEnricher`

- `_flatten_a11y_tree(node: dict[str, Any]) -> list[dict[str, Any]]` (method of `AccessibilityEnricher`): Flatten the a11y tree into a document-order list of interactive nodes. Returns only nodes that have a meaningful name or are interactive by role.
- `_build_role_name_index(nodes: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]` (method of `AccessibilityEnricher`): Build an index of (role, name) -> list of a11y nodes.
- `_build_href_index(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]` (method of `AccessibilityEnricher`): Build an index of href value -> list of a11y nodes. Hrefs appear in the 'properties' array of link nodes.
- `_match_by_role_and_name(element: dict[str, Any], role_name_index: dict[tuple[str, str], list[dict[str, Any]]], used_indices: set[int]) -> dict[str, Any] | None` (method of `AccessibilityEnricher`): Strategy 1: match scraped element to a11y node by role + accessible name. The element's visible text is compared against the a11y node's computed name. A role comparison narrows false positives.
- `_match_by_href(element: dict[str, Any], href_index: dict[str, list[dict[str, Any]]], used_indices: set[int]) -> dict[str, Any] | None` (method of `AccessibilityEnricher`): Strategy 3: match link elements by their href value.
- `_match_by_document_order(element: dict[str, Any], a11y_nodes: list[dict[str, Any]], used_indices: set[int]) -> dict[str, Any] | None` (method of `AccessibilityEnricher`): Strategy 2: match by document position (fallback). This is intentionally last because ARIA flow relationships can reorder the accessibility tree relative to DOM order. Role+name matching requires two signals to agree...
- `_apply_enrichment(element: dict[str, Any], a11y_node: dict[str, Any]) -> None` (method of `AccessibilityEnricher`): Apply computed fields from an a11y node to a scraped element. Rules: - accessible_name is added only if not already present (never overwrite). - computed_role is added unconditionally (a11y role may differ fro...

### Internal utilities

- `_transform_cdp_ax_tree(cdp_nodes: list[dict[str, Any]]) -> dict[str, Any]` (method of `AccessibilityEnricher`): Transform CDP Accessibility.getFullAXTree result into the format expected by enrich(). CDP returns a flat list of nodes with: - role: {"type": "...", "value": "button"} - name: {"type": "...", "value": "Click me"} - p...
