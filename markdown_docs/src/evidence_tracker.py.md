# `src/evidence_tracker.py`

## High-Level Purpose

Runtime evidence tracker — records each test step (navigate, click, fill, assert) with screenshots, element metadata, timing, and failure diagnostics. Writes per-test sidecar JSON files for evidence-based reporting.

## Module Metadata

- **Lines:** 426
- **Imports:** `re`, `time`, `pathlib.Path`, `typing.Any`, `playwright.sync_api.Page`, `src.evidence_serializer`, `src.failure_reporter`, `src.hover_click_utils`, `src.locator_fallback`

## Class: `EvidenceTracker`

### `__init__(page, test_name, condition_ref="unknown", story_ref="unknown", evidence_root=None, test_package_dir=None)`
- `test_package_dir` takes precedence over `evidence_root` for evidence directory
- Evidence written to `<test_package_dir>/evidence/`
- Sidecar: `{test_name}.evidence.json`
- Loads previous run history and step data for incremental run counts

### `_clean_label(label) -> str`
Converts `{{ACTION:description}}` tokens to human-readable `"Action: description"`.

### `_dismiss_consent_overlays()` / `_dismiss_ad_overlays()`
Delegates to `src.browser_utils.dismiss_consent_overlays`.

### `_load_previous_history() -> dict` / `_load_previous_steps() -> list`
Loads run history and step data from sidecar JSON for incremental counters.

### `_get_element_metadata(locator) -> dict`
Captures tag, id, data-testid, bounding box, and viewport percentages for an element. Uses full-document size for coordinates.

### `_record_step(step_type, label, locator, value, take_screenshot, error, matched_text, fallback_used, fallback_chain, elapsed_ms)`
Core recording method. Builds step dict with:
- Incremental `step_run_count` from previous runs
- Full-page screenshot when requested
- Element metadata (bbox, tag, attributes)
- Failure diagnosis via `FailureReporter.diagnose_failure()` on error
- Status: `"passed"`, `"partial_pass"` (when fallback used), `"failed"`

### `navigate(url, label="")` — Navigate + dismiss overlays + screenshot
### `fill(locator, value, label="")` — Fill form field
### `click(locator, label="")` — Click with layered fallback:
1. Scroll into view + direct click (`.first` to avoid strict-mode)
2. On visibility/timeout error: dismiss ads → hover-reveal → locator scoring fallback
3. Fallback success → `"partial_pass"` status with audit trail
### `assert_visible(locator, label="")` — Wait for visible + screenshot + capture text
### `write(status="passed") -> str` — Serialize sidecar JSON, update run history counters, return path

## Dependencies

- `src.evidence_serializer.EvidenceSerializer`
- `src.failure_reporter.FailureReporter`
- `src.hover_click_utils.try_hover_and_click`
- `src.locator_fallback.LocatorFallback`
- `src.browser_utils.dismiss_consent_overlays`

## Depended On By

Generated test code (runtime), `evidence_loader.py`, report builders