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