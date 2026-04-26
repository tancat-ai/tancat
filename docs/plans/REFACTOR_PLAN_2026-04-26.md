# Refactor Plan — Tier 2/3 Integration + File Restructuring

**Created:** 2026-04-26  
**Status:** In Progress  
**Reference:** This document is the single source of truth for the refactor.

---

## Part 0: Completed Steps

| # | Action | Files Changed | Status | Notes |
|---|--------|---------------|--------|-------|
| 1 | Deduplicate `RunTestLike` | `src/coverage_utils.py`, `src/run_utils.py` | ✅ Complete | Kept `RunTestLike` in `run_utils.py`, removed from `coverage_utils.py`, updated imports |
| 2 | Rename CLI file | `cli/test_orchestrator.py` → `cli/test_case_orchestrator.py` | ✅ Complete | Renamed file, updated all imports in `cli/main.py`, updated test file |
| 3 | Split evidence_report | `src/evidence_report.py`, `src/heatmap_utils.py` | ✅ Complete | Removed circular import by duplicating `_normalise_url` in `heatmap_utils.py`, making it self-contained |
| 4 | Extract locator fallback | `src/evidence_tracker.py`, `src/locator_fallback.py` | ✅ Complete | ruff + mypy clean, 455/456 tests pass |
| 5 | Extract placeholder_orchestrator | `src/orchestrator.py`, `src/placeholder_orchestrator.py` | ✅ Complete | Created new module with extracted placeholder resolution methods. Wiring into orchestrator.py complete via delegation properties. Added backwards-compatible `_resolve_placeholder_for_page()` delegation for existing test consumers. Updated `tests/test_orchestrator_dynamic_scrape.py` and `tests/test_stateful_scrape_switch.py` to use correct module paths. ruff + mypy clean, 456/456 full suite pass. |
| 6 | Fix pre-existing bug | `src/evidence_report.py` | ✅ Complete | Fixed `_clean_evidence_label()` — `action.title` → `action.title()` (missing method call parentheses caused `"Click: view cart link"` to output `"<built-in method title of str object at 0x...>: view cart link"`). All 456 tests now pass. |

---

## Part 1: Tier 2 & 3 Status

| Tier | Status | Notes |
|------|--------|-------|
| **Tier 1: Self-Diagnosing Failure Evidence** | ✅ Complete | `FailureReporter` captures URL, screenshot, locator candidates, failure note |
| **Tier 2: Locator Scoring + Controlled Fallback** | ✅ Complete | `LocatorScorer` + `_try_locator_fallback()` in `EvidenceTracker` with confidence scores and audit trail |
| **Tier 3: Suite Heatmap — Per-URL** | ✅ Complete | `generate_suite_heatmap()` in `evidence_report.py` with per-URL aggregation |

---

## Part 2: File Size Assessment

| File | Lines | Concern Level |
|------|-------|---------------|
| `src/evidence_report.py` | 1,217 | **HIGH** — multiple concerns mixed |
| `src/orchestrator.py` | 961 | **HIGH** — too many responsibilities |
| `src/code_postprocessor.py` | 853 | **MEDIUM** — well-structured but long |
| `src/evidence_tracker.py` | 639 | **MEDIUM** — fallback logic mixed with core tracking |

---

## Part 3: Naming Conflicts

| Name | Locations | Severity | Action |
|------|-----------|----------|--------|
| `RunTestLike` | `src/coverage_utils.py` + `src/run_utils.py` | **HIGH** — duplicate | Deduplicate, keep one, import elsewhere |
| `AnalysisMode` | `cli/config.py` + `src/config.py` | **MEDIUM** — check if identical | Verify, consolidate if same |
| `PipelineRunService` | `src/pipeline_run_service.py` | **LOW** — name clash with `TestOrchestrator` | Accept (different responsibility) |
| `test_orchestrator.py` (file) | `cli/` | **LOW** — shadows class name | Rename to `test_case_orchestrator.py` |

---

## Part 4: Proposed File Splits

### Split 1: `src/evidence_report.py` → 2 files

**`src/evidence_report.py`** (~550 lines) — keep:
- `generate_annotated_screenshot()`
- `generate_annotated_journey()`
- `list_evidence_from_package()`, `list_evidence_from_packages()`, `list_evidence_from_test_dir()`
- `_safe_read_json()`, `_normalise_url()`, `_clean_evidence_label()`, `_prepare_steps_for_display()`
- `EvidenceFile`, `TestPackageEvidence` classes

**`src/heatmap_utils.py`** (~650 lines, expanded) — add:
- `generate_suite_heatmap()` + `_extract_step_points_by_url()` (from evidence_report.py)
- Existing: `build_story_confidence()`, `build_confidence_heatmap()`
- Rationale: `heatmap_utils.py` already exists with AI-022 story confidence heatmap — Tier 3 per-URL heatmap belongs here

### Split 2: `src/evidence_tracker.py` → 2 files

**`src/evidence_tracker.py`** (~450 lines) — keep:
- `EvidenceTracker` core methods: `navigate()`, `fill()`, `click()`, `assert_visible()`, `write()`
- `_dismiss_consent_overlays()`, `_get_element_metadata()`, `_record_step()`
- `_try_hover_and_click()`

**`src/locator_fallback.py`** (~200 lines, new) — extract:
- `_try_locator_fallback()` → `LocatorFallback.try_fallback()`
- `_build_locator_candidates()` → `LocatorFallback.build_candidates()`
- Depends on `LocatorScorer`

### Split 3: `src/orchestrator.py` → 2-3 files

**`src/orchestrator.py`** (~400 lines) — keep:
- `TestOrchestrator` top-level `run_pipeline()` entry point
- `_build_generation_conditions()`, `_combine_condition_fragments()`
- `PipelineRunResult` dataclass

**`src/placeholder_orchestrator.py`** (~250 lines, new) — extract:
- `_replace_placeholders_sequentially()`
- `_resolve_placeholder_for_page()`
- `_find_best_element_for_current_page()`
- `_build_scoped_pages()`, `_select_fallback_page_url()`, `_infer_next_page_url()`
- `_find_journey_for_line()`, `_insert_consolidated_skips()`

**`src/page_object_orchestrator.py`** (~150 lines, new) — extract:
- `_build_page_object_artifacts()`
- `_upgrade_stateful_pages()`
- `_build_scraped_page_records()`

### No Split: `src/code_postprocessor.py`
- Functions are mostly standalone pure transforms
- Keep as-is or optionally package into `src/code_postprocessor/` directory later

---

## Part 5: Execution Order (one per session)

| # | Action | Files Changed | Test Impact |
|---|--------|---------------|-------------|
| 1 | Deduplicate `RunTestLike` | `src/coverage_utils.py` (remove, import) | `tests/test_coverage_utils.py` |
| 2 | Rename CLI file | `cli/test_orchestrator.py` → `cli/test_case_orchestrator.py` | `tests/test_cli_test_orchestrator.py` |
| 3 | Split evidence_report | `src/evidence_report.py` + `src/heatmap_utils.py` | `tests/test_evidence_report.py`, `tests/test_heatmap_utils.py` |
| 4 | Extract locator fallback | `src/evidence_tracker.py` + `src/locator_fallback.py` | `tests/test_evidence_tracker.py`, `tests/test_locator_fallback.py` |
| 5 | Split orchestrator | `src/orchestrator.py` + 2 new files | `tests/test_orchestrator.py` |

Each step: ruff → mypy → pytest → verify no behavior change.

---

## Part 6: Import Map (after all splits)

```
# src/coverage_utils.py
from src.run_utils import RunTestLike  # ← was duplicate

# src/evidence_tracker.py
from src.locator_fallback import LocatorFallback  # ← new import

# src/orchestrator.py
from src.placeholder_orchestrator import PlaceholderOrchestrator  # ← new
from src.page_object_orchestrator import PageObjectOrchestrator  # ← new

# cli/main.py (if it imports TestCaseOrchestrator)
from cli.test_case_orchestrator import TestCaseOrchestrator  # ← renamed file
```

---

## Part 7: Gotchas to Watch For

1. **`RunTestLike` protocol** — both copies are identical (`Protocol` with `nodeid`, `outcome` fields). Keep the one in `run_utils.py` (more semantically correct location), remove from `coverage_utils.py`.

2. **`_try_hover_and_click`** in `EvidenceTracker` calls `_try_locator_fallback` — after split, `_try_hover_and_click` stays in `EvidenceTracker` but `_try_locator_fallback` moves to `LocatorFallback`. Need to update the call.

3. **`_build_locator_candidates`** references `LocatorScorer.score_candidates()` — the new `LocatorFallback` module will import from `LocatorScorer`.

4. **Orchestrator's `_strip_imports_and_pages_needed`** — this is a pure utility used only by orchestrator, keep it there.

5. **`PipelineRunResult`** — imported by `streamlit_app.py` and various test files. Keep in `src/orchestrator.py` (it's the canonical location).

6. **`AnalysisMode`** in `cli/config.py` — the CLI orchestrator imports from `cli.config`. The src orchestrator imports from `src.config`. These are DIFFERENT enums (CLI has `AnalysisMode` with FAST/BUILD/FULL; src has `AnalysisMode` with SAME_PAGE/CROSS_PAGE). No conflict — they serve different modules.

7. **Heatmap JS/CSS** — `generate_suite_heatmap()` embeds inline JS for D3 visualization. This stays with the function when moved to `heatmap_utils.py`.

---

*Last updated: 2026-04-26*