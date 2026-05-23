# Implementation Plan: Enhanced Failure Diagnostics & Placeholder Resolution

**Created:** 2026-04-29
**Status:** Parts A & B Complete — Part C (integration testing) Pending
**Priority:** High — generated tests fail due to wrong locators; users have no debug visibility

---

## Problem Statement

Generated tests fail because:
1. **Placeholder resolution picks wrong locators** — e.g., `#subscribe` resolved for "Continue Shopping" button (actually a newsletter checkbox)
2. **Fragile product-specific selectors** — e.g., `data-product-id="38"` specific to scraped product
3. **No debug feedback** — reports only show `status: failed` with minimal error text. Rich diagnostic data captured in evidence JSON files is never surfaced to the user.

---

## Architecture Context

```
User Story → LLM Skeleton (placeholders) → Placeholder Resolution → Generated Test → pytest Run → Reports
                                              ↑                                       ↑
                                    SCRAPING + MATCHING                     EVIDENCE JSON
                                                                              (rich diagnostics exist but unused)
```

Key files involved:
- `src/placeholder_resolver.py` — resolves `{{ACTION:description}}` to CSS selectors
- `src/placeholder_orchestrator.py` — orchestrates per-page resolution
- `src/evidence_tracker.py` — captures diagnostics at runtime (failure_note, diagnosis, screenshots)
- `src/report_builder.py` — builds report dicts from coverage + run results
- `src/report_formatters.py` — renders reports (local, Jira, HTML)
- `cli/main.py` — CLI menu and session flow

---

## Part A: Enhanced Reports with Failure Diagnostics

**Goal:** Surface the rich diagnostic data already captured in evidence JSON files into reports and a new CLI debug view.

### A1: Evidence Loader Module ✅ DONE

- [x] **Create `src/evidence_loader.py`**
  - [x] Function: `load_evidence_for_package(package_dir: str) -> dict[str, dict]`
  - [x] Function: `get_failure_diagnostics(evidence: dict) -> dict[str, Any]`
  - [x] Function: `get_screenshot_paths(evidence: dict) -> list[str]`
  - [x] Function: `match_evidence_to_test(test_name, evidence_map) -> dict | None`
  - [x] Full type hints on all functions
  - [x] Create `tests/test_evidence_loader.py` — 14 tests, all passing

### A2: Enrich Report Dicts with Evidence Data ✅ DONE

- [x] **Modify `src/report_builder.py`**
  - [x] Import `load_evidence_for_package` from `src.evidence_loader`
  - [x] Add optional `package_dir: str = ""` parameter to `build_report_dicts()`
  - [x] After matching run results, load evidence JSON for each test
  - [x] Merge into each report row: `failure_note`, `diagnosis`, `suggested_locators`, `available_elements`, `screenshot_paths`, `page_url`, `page_title`

- [x] **Modify `src/pipeline_report_service.py`**
  - [x] Pass `package_dir` through to `build_report_dicts()` call

### A3: Render Failure Diagnostics in Reports ✅ DONE

- [x] **Modify `src/report_formatters.py` — `generate_local_report()`**
  - [x] For failed tests, add "Failure Diagnostics" section with page URL, title, failure note, suggested alternatives, available elements summary, screenshot paths
  - [x] Truncate long failure notes to 600 chars

- [x] **Modify `src/report_formatters.py` — `generate_jira_report()`**
  - [x] Same diagnostics section, formatted for Jira markdown
  - [x] Use Jira thumbnail syntax for screenshots

- [x] **Modify `src/report_formatters.py` — `generate_html_report()`**
  - [x] Red-bordered "Failure Diagnostics" section for failed tests
  - [x] Embed failure screenshots as base64
  - [x] Show suggested locators as `<code>` snippets
  - [x] Available elements summarized by role counts

### A4: New CLI Menu Option — "View Failure Diagnostics" ✅ DONE

- [x] **Modify `cli/main.py`**
  - [x] Add menu item: "View Failure Diagnostics" (appears after running tests)
  - [x] New function: `view_failure_diagnostics(session: Session)`
  - [x] Displays: test name, condition ref, duration, page URL/title, failure steps with error summaries, suggested alternatives, available elements summary
  - [x] Color-coded: red for failures, yellow for warnings, green for all-passed
  - [x] Wired into main menu routing

---

## Part B: Placeholder Resolution Improvements ✅ DONE

**Goal:** Reduce wrong locator matches by adding text-content validation and confidence thresholds.

### B1: Text-Content Validation in Placeholder Resolution ✅ DONE

- [x] **Modify `src/placeholder_resolver.py`**
  - [x] In `find_best_element()`, verify element's visible text matches action description
  - [x] New function: `text_matches_description(element_text: str, action_description: str) -> bool`
    - [x] Case-insensitive containment check
    - [x] Normalize whitespace
    - [x] Allow partial matches (word-level overlap)
  - [x] If text doesn't match, skip to next candidate or mark as unresolved
  - [x] Add logging for skipped candidates with reason
  - [x] Full type hints

- [x] Create `tests/test_placeholder_resolver_text_validation.py` — 9 text validation tests

### B2: Confidence Threshold for Resolution ✅ DONE

- [x] **Modify `src/placeholder_resolver.py`**
  - [x] Added configurable `min_confidence` parameter to `__init__`
  - [x] After scoring candidates, if confidence < threshold, mark as unresolved
  - [x] Logging for skipped candidates below threshold
  - [x] Configurable via `PLACEHOLDER_MIN_CONFIDENCE` env var (default: 0.3)

- [x] **Modify `src/locator_scorer.py`**
  - [x] Added `_text_matches_description()` static method
  - [x] Added `action_description` parameter to `score_locator()`
  - [x] Text-match bonus: +10 points if element text matches action description

- [x] Updated `tests/test_placeholder_resolver.py` — 4 confidence threshold tests

### B3: Page-Context Validation ✅ DONE

- [x] **Modify `src/placeholder_orchestrator.py`**
  - [x] New method: `_verify_page_context()` — checks if resolved locator exists on current page
  - [x] Logs warning with source page vs current page on cross-page mismatch
  - [x] Integrated into `_resolve_placeholder_for_page()` flow

---

## Part C: Integration Testing ✅ DONE

- [x] **Run end-to-end validation**
  - [x] Run `ruff check` — all checks passed
  - [x] Run `mypy` — success: no issues found
  - [x] Run `pytest -v` — 100 tests passing in 2.11s

- [x] **Update documentation**
  - [x] Update `AGENTS.md` §4 Project Structure with new modules
  - [x] Update `AGENTS.md` §11 Enhanced Failure Diagnostics summary
  - [x] Update session tracking table

---

## Session Tracking

| Session | Date | Completed | Notes |
|---------|------|-----------|-------|
| 1 | 2026-04-29 | Plan created | Document created, ready for implementation |
| 2 | 2026-04-29 | Part A complete | All 4 sub-tasks done. 42 tests passing. ruff + mypy clean. |
| 3 | 2026-04-29 | Parts A & B complete | 100 tests passing. ruff + mypy clean. Text validation, confidence threshold, page-context validation all in place. |
| 4 | 2026-04-29 | Part C complete | Documentation updated. AGENTS.md §4 and §11 reflect new modules. All success criteria met. |

---

## Dependencies & Constraints

- **Protected files:** `src/test_generator.py`, `src/llm_client.py`, `.github/workflows/ci.yml` — do not modify
- **Protected directory:** `src/llm_providers/` — do not modify
- **Package manager:** Use `uv add` / `uv sync`, never `pip install`
- **Test format:** pytest sync only, no async
- **Type hints:** Required on all new functions
- **Quality gate:** `ruff` → `mypy` → `pytest` before any commit

---

## Success Criteria

1. **Reports show actionable failure info** — a user reading `report_local.md` can understand why a test failed without running it again
2. **CLI debug view works** — "View Failure Diagnostics" shows per-failure context in the terminal
3. **Fewer wrong locator matches** — text-content validation prevents `#subscribe` being matched for "Continue Shopping"
4. **All tests pass** — `ruff`, `mypy`, and `pytest -v` all green
5. **No regressions** — existing evidence tracking, report generation, and placeholder resolution still work

---

*Last updated: 2026-04-29*