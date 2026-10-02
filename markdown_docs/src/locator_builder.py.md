# `src/locator_builder.py`

## High-Level Purpose

Builds robust Playwright locators from scraped element metadata. Transforms brittle CSS selectors into stable, specific locators by prioritizing ID > href > data-attrs > class > text > aria-label patterns. Used during placeholder resolution to produce reliable selectors.

## Module Metadata

- **Lines:** 182
- **Imports:** `re`

## Functions

### `build_robust_locator(element: dict) -> str | None`

Build a robust Playwright locator from scraped element metadata. Prefers stable, specific selectors over text-based locators.

**Priority order** (most specific first):
1. ID-based (e.g. `#buy`)
2. href-based for links (e.g. `a[href="/view_cart"]`)
3. Data attribute with specific value (e.g. `[data-product-id="1"]`)
4. Class-based without brittle framework prefixes (e.g. `.cart_description`)
5. Tag + :has-text (e.g. `a:has-text("Add to cart")`)
6. Role + :has-text (e.g. `button:has-text("Submit")`)
7. Aria-label based (e.g. `[aria-label="Submit"]`)
8. `None` — falls back to raw selector

Strips common UI framework class prefixes (`btn-`, `fa-`, `fas`, `far`, `bi-`, `mdi-`, `icon-`, `css-`) that add no semantic value.

**Args:** `element` — Dict with keys: `tag`, `text`, `role`, `selector`, `id`, `aria_label`, `classes`, `href`.
**Returns:** Robust locator string, or `None` if nothing stable can be built.

### `build_selector_relaxed(description: str, page_elements: list[dict]) -> str | None`

Build a selector with relaxed matching criteria. Used as fallback when strict selector build fails. Tokenizes the description and scores elements by token overlap across text, attributes, and role. Uses 0.2 confidence threshold (vs 0.3 strict).

**Args:** `description` — Human-readable target description; `page_elements` — Element metadata from scraper.
**Returns:** Relaxed locator string, or `None` if no element meets threshold.

### `_css_escape_id(value: str) -> str`

Escape a value for safe use as a CSS ID selector.

### `_token_overlap(description_tokens: set[str], element_tokens: set[str]) -> float`

Compute Jaccard-like overlap between two token sets. Returns a value in [0, 1].

## Dependencies

None (stdlib only).

## Depended On By

`placeholder_resolver.py`, `placeholder_orchestrator.py`

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `build_dot_classes` (function): `build_dot_classes(classes: str) -> str` - Build a dot-class selector (.a.b.c) with every class CSS-escaped.


## How It Works (Internals)

Private `_`-helpers - the module's real logic (2 items). Grouped under the public function that calls them.

### `build_dot_classes(classes: str) -> str` - function

- `_css_escape_class_token(token: str) -> str` (function): Escape a single CSS class name for use inside a class selector. Tailwind-style variant classes (hover:text-amber-200, sm:text-3xl) and fractional utilities (py-3.5, w-1/2) contain characters with speci...

### `build_selector_relaxed(description: str, page_elements: list[dict]) -> str | None` - function

- `_token_overlap(description_tokens: set[str], element_tokens: set[str]) -> float` (function): Compute Jaccard-like overlap between two token sets. Returns a value in [0, 1] representing how many description tokens are covered by the element tokens.
