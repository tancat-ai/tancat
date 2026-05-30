# skeleton_validator.py

## Purpose
Validates skeleton output for forbidden patterns (CSS selectors, XPath, etc.). Ensures LLM-generated test skeletons use ONLY placeholder syntax (`{{CLICK:description}}`, `{{FILL:description}}`, etc.) and contain no real locators. Real locators are resolved in Phase 2 by the placeholder resolver.

## Location
`src/skeleton_validator.py`

## Dependencies
- `re` (standard library)
- `dataclasses` (standard library)

## Public API

### `SkeletonValidationResult` (dataclass)
Result of validating a skeleton for forbidden patterns.
- `is_valid: bool` — Whether the skeleton passes validation
- `violations: list[str]` — List of violation descriptions found
- `suggestion: str` — Human-readable suggestion for fixing violations

### `SkeletonValidator.validate(skeleton_code: str) -> SkeletonValidationResult`
Validate skeleton code for forbidden locator patterns. Scans each line for CSS class selectors, CSS ID selectors, CSS attribute selectors, XPath expressions, CSS descendant combinators, `page.locator()` with real selectors, and `get_by_role/get_by_text/get_by_label` with literal arguments. Skips comment lines, import lines, placeholder lines, and URL contexts (avoids false positives on `https://`).

## Design Notes
- URL-aware: `://` contexts are excluded from XPath pattern matching to avoid flagging `https://` URLs
- Deduplicates violations while preserving order
- Returns actionable suggestion text when violations are found
- Enforces the two-phase skeleton-first pipeline: Phase 1 = placeholders only, Phase 2 = real selectors

## Related Files
- `src/skeleton_parser.py` — sibling module that parses skeleton structure
- `src/test_generator.py` — uses validator before accepting skeleton output
- `src/placeholder_resolver.py` — Phase 2 resolver that substitutes real selectors