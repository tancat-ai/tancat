# FEATURE_SPEC_AI023_locator_repair.md
## AI-023 — Interactive Locator Repair Loop

**Status:** ✅ **COMPLETED** — All 4 sessions implemented, tested, and shipped
**Completed:** 2026-05-23
**Depends on:** Evidence sidecar (AI-018 complete), `src/pytest_output_parser.py` (complete)
**Blocks:** Nothing — standalone feature
**Priority:** High — directly addresses the most frustrating part of the current workflow

---

## Implementation Summary

All four sessions were completed in strict order per the design:

| Session | File | Tests | Status |
|---------|------|-------|--------|
| 1 — Failure Classifier | `src/failure_classifier.py` | `tests/test_failure_classifier.py` (15 tests) | ✅ Complete |
| 2 — Locator Patch | `src/locator_repair.py` | `tests/test_locator_repair.py` (12 tests) | ✅ Complete |
| 3 — UI Wiring | `src/ui_renderers.py` | Integrated tests | ✅ Complete |
| 4 — Browser Integration | `src/ui_renderers.py` (extension) | Integrated tests | ✅ Complete |

**Total:** 27 dedicated unit tests passing. Full test suite (803 tests) passes. CI/CD green.

### Key Implementation Details

**Session 1 — `src/failure_classifier.py`** (174 lines)
- `FailureCategory` enum: `LOCATOR_TIMEOUT`, `STRICT_VIOLATION`, `ASSERTION_FAILURE`, `NAVIGATION_ERROR`, `OTHER`
- `FailureDetail` dataclass with `category`, `raw_locator`, `failure_url`, `line_number`, `error_message`
- `classify_failure(error_message: str) -> FailureDetail` — pattern-matches error text
- `extract_locator(error_message: str) -> str | None` — parses Playwright timeout errors for locator strings

**Session 2 — `src/locator_repair.py`** (151 lines)
- `LocatorPatch` dataclass with `original_locator`, `repaired_locator`, `line_number`, `test_file`
- `apply_patch(patch: LocatorPatch) -> str` — replaces locator string, preserves action (`.click()`, etc.)
- `apply_patch_to_file(patch: LocatorPatch) -> LocatorPatch` — reads file, applies patch, writes back
- `LocatorNotFoundError` raised when original locator not found in file

**Sessions 3+4 — `src/ui_renderers.py`** (229 lines added)
- `RunResultsDisplay` class with failure classification and repair buttons
- Repair button rendered for `LOCATOR_TIMEOUT` and `STRICT_VIOLATION` failures
- Info notes for `ASSERTION_FAILURE` and `NAVIGATION_ERROR` (no repair offered)
- Three-panel repair flow: `waiting` → `browser_requested` → `patched`/`error`
- Browser session uses `playwright codegen` via subprocess
- Patch applied automatically after browser session captures locator
- "▶️ Run Generated Tests" button to verify fix

---

## Problem Statement

When a generated test fails because the tool could not find an element, the tester
currently sees a Playwright `TimeoutError` or strict mode violation and has to:

1. Open the page manually in a browser
2. Use DevTools to find the locator themselves
3. Edit the generated test file by hand
4. Re-run to verify the fix

This is exactly the work the tool is supposed to eliminate. The repair loop closes
that gap: when a failure is a locator problem (tool's fault, not the site's fault),
the tool offers to open the page, let the tester click the element, and patch the
test file automatically.

---

## Design Principle

**The tester must stay in control.**

The tool does not guess. It does not hallucinate a replacement locator. It opens a
real headed browser, navigates to exactly where the test got stuck, and waits for
the tester to click. The tester sees the actual page. They click the actual element.
The tool records what Playwright reports about that element and writes it back to
the test file.

---

## Scope Constraints

- **Only for locator failures, not assertion failures.**
- **Only in the Streamlit UI, not CI.**
- **One locator repair per invocation.**

---

## File Summary

| File | Session | State |
|------|---------|-------|
| `src/failure_classifier.py` | 1 | Created (174 lines) |
| `tests/test_failure_classifier.py` | 1 | Created (118 lines, 15 tests) |
| `src/locator_repair.py` | 2, 4 | Created (151 lines) |
| `tests/test_locator_repair.py` | 2 | Created (221 lines, 12 tests) |
| `src/ui_renderers.py` | 3, 4 | Modified (+229 lines) |

---

## What This Does Not Do

- **No automatic locator guessing.**
- **No batch repair.**
- **No repair in CI.**
- **No modification of evidence sidecars.**

---

## Related Features

- **AI-024 — Accessibility Tree Enrichment** (completed separately) reduces locator failure frequency independently

---

*Spec completed: 2026-05-23*
*Commit: 2735c13a on main*