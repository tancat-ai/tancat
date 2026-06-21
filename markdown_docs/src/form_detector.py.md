# `src/form_detector.py`

## High-Level Purpose

`form_detector.py` provides lightweight utilities for recognizing form-related elements and useful commerce actions from scraped page element metadata. It does not interact with Playwright or the browser directly. Instead, it consumes dictionaries produced elsewhere by a scraper and converts or ranks that metadata using deterministic heuristics.

The module focuses on three related tasks:

- Defining reusable selector priority lists for product, add-to-cart, and continue-shopping actions.
- Normalizing discovered form fields into a typed `FormField` dataclass.
- Offering stateless helper methods for input classification, submit-button detection, form grouping, and selector discovery.

## Module-Level Constants

### `PRODUCT_SELECTORS: list[str]`

Priority list of CSS-style selectors that may identify product links or product containers. The entries cover product-detail URL patterns, common product item classes, title links, and `data-product-id` attributes.

### `ADD_TO_CART_SELECTORS: list[str]`

Priority list of selectors that may identify add-to-cart or submit controls. The list mixes Playwright text selectors, button/input submit selectors, CSS classes, data attributes, and add-to-cart URL patterns.

This list is actively used by `FormDetector.identify_submit_button()`.

### `CONTINUE_SHOPPING_SELECTORS: list[str]`

Priority list of selectors that may identify continue-shopping or modal-close actions. It includes text selectors, modal-related classes, data-action attributes, and generic close-button classes.

This constant is defined for reuse but is not referenced by the functions in this module.

## Data Structures

### `@dataclass class FormField`

Represents a normalized form field discovered from scraped element metadata.

Signature:

```python
FormField(
    tag: str,
    field_type: str,
    selector: str,
    name: str,
    placeholder: str,
)
```

Fields:

- `tag: str` - Lowercase HTML tag name, expected to be `input`, `select`, or `textarea`.
- `field_type: str` - Canonical field category returned by `FormDetector.classify_input()`.
- `selector: str` - Primary selector for locating the field.
- `name: str` - Element `name` attribute, or an empty string if unavailable.
- `placeholder: str` - Element placeholder text, or an empty string if unavailable.

Return behavior:

- The dataclass generates the standard initializer, representation, comparison, and field storage methods.
- All fields are required and have no defaults.

## Classes

### `class FormDetector`

Stateless namespace for form and selector detection helpers. All methods are `@staticmethod`, so callers do not need to instantiate the class.

Expected input shape:

- Methods consume `list[dict[str, Any]]` or `dict[str, Any]` records.
- Common element keys include `selector`, `css_selectors`, `text`, `name`, `tag_name`, `input_type`, `placeholder`, `has_id`, and `has_name`.
- Missing optional values are generally handled with defaults, although values are expected to be string-like where string methods are called.

## Function and Method Signatures

### `FormDetector.classify_input(raw_type: str, element: dict[str, Any]) -> str`

Maps an HTML input `type` attribute to a canonical field category.

Parameters:

- `raw_type: str` - Raw input type value, such as `"email"`, `"password"`, or `"checkbox"`.
- `element: dict[str, Any]` - Scraped element metadata. Present for interface consistency and possible future use, but not used by the current implementation.

Returns:

- `str` - Canonical category.

Known mappings:

- `"email"` -> `"email"`
- `"password"` -> `"password"`
- `"tel"` -> `"phone"`
- `"number"` -> `"number"`
- `"date"` -> `"date"`
- `"checkbox"` -> `"checkbox"`
- `"radio"` -> `"radio"`
- `"file"` -> `"file"`
- `"hidden"` -> `"hidden"`
- `"submit"` -> `"submit"`
- `"button"` -> `"button"`
- `"reset"` -> `"reset"`
- Any unknown type -> `"text"`

Architectural notes:

- Uses a local dictionary lookup for deterministic normalization.
- Lowercases `raw_type` before lookup.
- Assumes `raw_type` behaves like a string.

### `FormDetector.identify_submit_button(elements: list[dict[str, Any]]) -> str | None`

Finds the best submit-like button selector from scraped element metadata.

Parameters:

- `elements: list[dict[str, Any]]` - Scraped element records.

Returns:

- `str | None` - The chosen element selector, or `None` if no submit-like candidate is found.

Selection behavior:

1. Iterates through `ADD_TO_CART_SELECTORS` in priority order.
2. For each selector, scans all elements.
3. Returns an element's `selector` when either:
   - `el["selector"]` exactly matches the prioritized selector.
   - The prioritized selector appears in `el["css_selectors"]`.
4. If no priority selector matches, falls back to text matching.
5. The fallback returns the first selector whose lowercase text contains one of:
   - `"submit"`
   - `"add"`
   - `"buy"`
   - `"checkout"`
   - `"proceed"`

Architectural notes:

- Encodes a two-stage heuristic: selector registry first, semantic text fallback second.
- Selector order in `ADD_TO_CART_SELECTORS` controls precedence.
- Depends on scraper records containing `selector`, optionally `css_selectors`, and optionally `text`.

### `FormDetector.detect_forms(elements: list[dict[str, Any]]) -> list[list[FormField]]`

Groups scraped field-like elements into simple form structures.

Parameters:

- `elements: list[dict[str, Any]]` - Scraped element records.

Returns:

- `list[list[FormField]]` - A list of detected forms, where each form is represented as a list of `FormField` values.
- Returns `[]` when no field-like elements are found.
- Returns `[form_fields]` when at least one field is found.

Detection behavior:

1. Iterates through every element.
2. Reads `tag_name`, lowercases it, and keeps only:
   - `input`
   - `select`
   - `textarea`
3. Reads `input_type`, defaulting to `"text"`.
4. Calls `FormDetector.classify_input()` to normalize the field type.
5. Builds a `FormField` with normalized and defaulted metadata:
   - `selector` defaults to `""`
   - `name` defaults to `""`
   - `placeholder` defaults to `""`
6. Groups all discovered fields into one form.

Architectural notes:

- Uses a deliberately simple grouping heuristic.
- Does not infer separate form boundaries.
- Treats consecutive or discovered field-like elements as a single form structure.

### `FormDetector.discover_selector(elements: list[dict[str, Any]], description: str) -> str | None`

Finds the best selector for a described element using a score-based heuristic.

Parameters:

- `elements: list[dict[str, Any]]` - Scraped element records.
- `description: str` - Human-readable description of the desired element.

Returns:

- `str | None` - Best matching selector if a positive-scoring candidate exists, otherwise `None`.

Scoring behavior:

- Starts each element at score `0`.
- Adds `10` if the lowercase description appears in the element text.
- Adds `8` if the lowercase description appears in the element name.
- Adds `5` if `has_id` is truthy.
- Adds `3` if `has_name` is truthy.
- Tracks the highest-scoring element and returns its selector only when the best score is greater than `0`.

Tie behavior:

- Ties keep the earlier best candidate because the method only replaces the winner when `score > best_score`.

Architectural notes:

- Combines semantic matching with selector-stability hints.
- Prefers elements with IDs or names when textual evidence is similar.
- Assumes text and name metadata are string-like after defaulting missing values to empty strings.

## Key Architectural Patterns

### Stateless Helper Class

`FormDetector` is used as a static utility namespace. There is no instance state, dependency injection, cache, or configuration object.

### Dictionary-Based Scraper Contract

The module expects upstream scraping code to provide element dictionaries with predictable keys. It keeps this contract flexible by using `dict[str, Any]`, while selectively defaulting missing fields.

### Heuristic-First Detection

The implementation favors transparent, deterministic heuristics:

- Ordered selector lists for known commerce controls.
- Keyword fallback for submit-button discovery.
- Tag filtering for form detection.
- Point scoring for free-text selector discovery.

### Normalized Field Model

`FormField` converts loose scraped dictionaries into a small typed structure. This creates a clearer downstream representation without requiring the detector to understand full DOM hierarchy.

### Conservative Form Grouping

`detect_forms()` intentionally avoids complex DOM reconstruction. It gathers all detected fields into a single form group and returns no forms when no field elements are present.

## Important Assumptions and Edge Cases

- `raw_type` in `classify_input()` is expected to be a string. Non-string values would not support `.lower()`.
- `detect_forms()` treats missing `tag_name` as an empty string and skips that element.
- `identify_submit_button()` may return any value stored under `selector`; the type hint expects this to be `str | None`.
- `discover_selector()` can match broad descriptions because it uses substring checks rather than tokenized or semantic matching.
- Empty or overly generic descriptions may produce weak matches because empty strings are substrings of all strings in Python.
- The selector constants are reusable module-level configuration, but only `ADD_TO_CART_SELECTORS` is used by current module logic.
