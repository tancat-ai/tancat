# `src/failure_reporter.py`

## Purpose
Generates self-diagnosing failure evidence for failed Playwright test steps. Captures diagnostic context (page state, available elements, suggested alternatives) without auto-recovering — tests still fail, but with actionable debug info.

## Metadata
- **Lines:** 468
- **Imports:** logging, typing.Any, playwright.sync_api.Page, src.locator_scorer.LocatorScorer

## Class
| Class | Description |
|-------|-------------|
| `FailureReporter` | Captures runtime diagnostics when a test step fails |

## Methods
| Method | Description |
|--------|-------------|
| `diagnose_failure(page, locator, step_type, error)` | Returns dict with url, title, available_elements, suggested_locators, page_snapshot, error_summary |
| `_categorize_elements(page, step_type, max_elements=20)` | Captures interactive elements via accessibility snapshot or JS fallback |
| `_flatten_accessibility_tree(node, max_count)` | Recursively flattens accessibility tree to flat list |
| `_suggest_locators(page, original_locator, step_type)` | Uses LocatorScorer to score and rank alternative locators |
| `_extract_raw_candidates(page)` | Extracts locator candidates from DOM via JS evaluation |
| `_capture_snapshot(page)` | Lightweight accessibility snapshot as text |
| `generate_failure_note(diagnosis)` | Human-readable failure note grouping elements by role |

## Key Logic
- Two-strategy element capture: accessibility snapshot first, then JS DOM query fallback
- Candidates scored by LocatorScorer with confidence levels (high/medium-high/medium)
- Failure note groups elements by role for readability
- Limited to top 15 suggestions and 20 elements to avoid bloating evidence

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `DIAGNOSIS_BUDGET_SECONDS` (constant): `DIAGNOSIS_BUDGET_SECONDS = 8.0`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (7 items). Grouped under the public function that calls them.

### `FailureReporter.diagnose_failure(page: Page, locator: str | None, step_type: str, error: str) -> dict[str, Any]` - method of `FailureReporter`

- `_categorize_elements(page: Page, step_type: str, max_elements: int = 20) -> list[dict[str, str]]` (method of `FailureReporter`): Capture all interactive elements on the page, categorized. Returns a list of dicts with selector_hint, text, role, and category. Limited to max_elements to avoid bloating the evidence file.
- `_suggest_locators(page: Page, original_locator: str | None, step_type: str) -> list[dict[str, str]]` (method of `FailureReporter`): Suggest alternative locators based on the page state. Uses LocatorScorer to score candidates and return them with consistent confidence levels. Returns a list of dicts with locator, type, score, confidence, and fragil...
- `_capture_snapshot(page: Page) -> str | None` (method of `FailureReporter`): Capture a lightweight accessibility snapshot of the current page. Returns a markdown-like string summarizing the page structure, or None if snapshot capture fails.

### Internal utilities

- `_flatten_accessibility_tree(node: dict, max_count: int) -> list[dict[str, str]]` (method of `FailureReporter`): Recursively flatten an accessibility tree into a flat list of nodes.
- `_make_key(node: dict) -> str` (method of `FailureReporter`): Create a unique key for an accessibility node.
- `_extract_raw_candidates(page: Page) -> list[dict[str, Any]]` (method of `FailureReporter`): Extract raw locator candidates from the current page DOM. Returns a list of dicts with 'selector' and optional 'element' keys.
- `_snapshot_to_text(node: dict, max_lines: int = 50, depth: int = 0) -> str` (method of `FailureReporter`): Convert an accessibility node tree to a text summary.
