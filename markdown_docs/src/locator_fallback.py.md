# `src/locator_fallback.py`

## High-Level Purpose

Provides higher-scoring locator alternatives when the primary locator fails at runtime. Part of the Tier 2: Locator Scoring + Controlled Fallback architecture. Builds candidate selectors from the current page DOM, scores them with `LocatorScorer`, and tries the top alternatives with full audit trail.

## Module Metadata

- **Lines:** 204
- **Imports:** `typing.Any`, `src.locator_scorer.LocatorScorer`

## Class: `LocatorFallback`

Controlled locator fallback with scoring and audit trail. When a primary locator fails, this class:
1. Builds candidate selectors from the current page DOM
2. Scores candidates using `LocatorScorer`
3. Tries the top 2 higher-scoring alternatives
4. Returns an audit trail with scores and confidence levels

### `build_candidates(primary_locator, el_metadata, page) -> list[dict]`

Build a list of locator candidates from the current page DOM. Uses JavaScript to extract candidate selectors (id, testid, name, aria-label, role, classes, text) for the same element or similar elements.

**Args:** `primary_locator` — Original selector that failed; `el_metadata` — Element metadata; `page` — Playwright Page.
**Returns:** List of candidate dicts with `selector` and `element` keys.

### `try_fallback(loc, primary_locator, label, el_metadata, primary_error, page, record_step, max_fallbacks=2, elapsed_ms=0) -> None`

Try higher-scoring locator alternatives when the primary locator fails. Builds candidates, scores them, and tries top `max_fallbacks` in score-descending order. Records full fallback chain with scores and confidence levels.

**Args:** `loc` — Playwright locator; `primary_locator` — Failed selector; `label` — Step label; `el_metadata` — Element metadata; `primary_error` — Exception; `page` — Playwright Page; `record_step` — Step recorder callable; `max_fallbacks` — Max candidates to try (default 2).
**Raises:** The primary error is re-raised after all fallbacks fail.

## Dependencies

`src.locator_scorer` (LocatorScorer)

## Depended On By

Runtime test execution (generated tests with fallback support)