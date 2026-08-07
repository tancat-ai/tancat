# `src/ui/ui_run_results.py` — Run Results Display, Failure Classification, and Locator Repair

## Purpose

Streamlit component for displaying test run results with failure classification, coverage analysis, locator repair panel, and inline evidence viewer.

## Class: `RunResultsDisplay`

### `render(run_result: RunResult) -> None` (static)

Full run results display:

1. **Command caption**: Shows the pytest command used
2. **Error banner**: If pytest hit collection/import errors
3. **Metrics row**: Total, Passed, Failed, Skipped, Errors (5 columns)
4. **Coverage table**: Criteria-level coverage analysis with pass/fail mapping
5. **Results table**: Per-test results with repair buttons (see `_render_results_table`)
6. **Repair panel**: Shown when user clicks a repair button (see `_render_repair_panel`)
7. **Inline evidence**: Annotated screenshots for just-run tests (see `_render_inline_evidence`)
8. **Pytest output**: Expandable raw output (auto-expanded on errors)
9. **Downloads**: Report download buttons via `RenderDownloads.render()`

**Added 2026-07-20:**
- Self-healing integration: "🩹 Self-Heal Failed Tests" button + healing results
- Failed test expanders with error preview, completed steps, full traceback
- Test results table includes Ref column (condition_ref from @pytest.mark.evidence)
- Pytest Output expander opens on any failure (was: only collection errors)

## Functions

### `_render_inline_evidence(run_result) -> None`

Renders inline evidence viewer:
- Loads evidence sidecars from `evidence/` directory
- Filters to only tests that just ran (matches test names from `RunResult`)
- Selectable sidecar with view modes: annotated, heatmap, clean
- Shows step details with pass/fail icons

### `_render_results_table(results) -> None`

Per-test results table with repair buttons:

| Status | Display |
|--------|---------|
| Passed | ✅ icon |
| Failed | ❌ icon + error caption + repair button (if locator failure) |
| Skipped | ⏭️ icon |

**Repair button logic:**
- `LOCATOR_TIMEOUT` / `STRICT_VIOLATION`: Shows 🔧 Fix locator button → opens repair panel
- `ASSERTION_FAILURE`: Shows info caption (no repair)
- `NAVIGATION_ERROR`: Shows info caption (no repair)

### `_render_repair_panel() -> None`

Dispatcher based on `st.session_state.repair_status`:
- `"waiting"` → `_render_repair_waiting_panel()`
- `"browser_requested"` → `_render_repair_browser_session()`
- `"patched"` / `"error"` → `_render_repair_result_panel()`

### `_render_repair_waiting_panel() -> None`

Shows repair mode UI with failed locator info, test file path, and "Open browser and fix locator" button. Sets `repair_status = "browser_requested"` on click.

### `_render_repair_browser_session() -> None`

Runs a headed browser session via `run_codegen_session()`:
1. Opens browser at the failure URL
2. Waits up to 120s for user to click the correct element
3. Applies the new locator via `LocatorPatch` + `apply_patch_to_file()`
4. Sets `repair_status = "patched"` or `"error"` based on outcome

### `_render_repair_result_panel() -> None`

Shows success/error message with:
- Updated test file viewer (expanded)
- "Run Generated Tests" button (enabled only if patched)
- "Done" button to reset repair state

### `_render_self_healing_results(report: HealingReport) -> None` (added 2026-07-20)

Renders self-healing report after automated repair:
- Metrics: Failures, Fixed, Remaining, Iterations (4 columns)
- Per-patch expanders with diagnosis and diff display
- "🎉 All failures fixed" success or warning for remaining failures
- "🔄 Re-run Tests" and "🧹 Clear Healing Results" buttons

### `_render_failed_tests_repair(results, run_result=None) -> None` (updated 2026-07-20)

Shows expanders for every failed test with:
- Error preview extracted from pytest output or raw output
- **Steps completed before failure** — parsed from test source
- Full error output in collapsible sub-expander
- "🔧 Fix Locator" button for locator-classified failures
- Self-healing button at top of section when failures exist

### `_parse_condition_refs_from_source(source: str) -> dict[str, str]` (added 2026-07-20)

Parses `@pytest.mark.evidence(condition_ref="TC01.05", ...)` decorators to map test function names to their condition references. Used to populate the Ref column in the test results table.

### `_extract_error_from_raw_output(raw_output, test_name) -> str` (added 2026-07-20)

Extracts error details from raw pytest output when `TestResult.error_message` is empty (common for timeouts). Searches the FAILURES block for the test's error.

### `_extract_last_steps_before_failure(source, test_name) -> list[str]` (added 2026-07-20)

Parses test source to find the last completed action steps (Navigate, Click, Fill, Assert) before the failure point. Returns up to 6 steps for context.

### `_run_setup_script(base_url, target_url, steps) -> SetupScriptResult`

Builds and executes a temporary Playwright setup script that replays prerequisite steps and saves browser storage state for the locator-repair codegen session.

**Cart-seeding (2026-08-03):**
- Triggered via `url_utils.is_stateful_cart_checkout_path` (site-agnostic — covers saucedemo `/cart.html` as well as `/view_cart`/`/checkout`)
- Best-effort login with saucedemo demo credentials when a login form is present
- Product-page navigation tries `(/products, /inventory.html)` candidates via HTTP status probe
- Add-to-cart Strategy C: direct grid button (`button:has-text("Add to cart"), [data-test^="add-to-cart"], .btn_inventory`) for saucedemo-style inventory pages
- Modal dismissal scoped to modal containers (B-015 lesson — a visible cart-page "Continue Shopping" must not be clicked)

**Known Windows gotcha (pre-existing):** the storage-state print line embeds the temp path without `r''` escaping, so `C:\Users\...` breaks the generated script's parse on Windows.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (13 items). Grouped under the public function that uses them:

### `RunResultsDisplay`
- `_get_generated_code_for_coverage() -> str` (function) — Get generated test code for coverage analysis.
- `_read_test_code_from_path(saved_path: str) -> str` (function) — Read test code from a saved test file or package directory.
- `_render_skip_repair_panel() -> None` (function) — Render the skip repair panel — opens codegen and replaces pytest.skip() with a real action.
- `_render_skipped_tests_info(results: list[TestResult]) -> None` (function) — Render information about skipped tests, showing why they were skipped.

### Internal utilities
- `_extract_all_steps_before_test(source: str, test_name: str) -> list[str]` (function) — Extract all action steps from all tests before the given test.
- `_extract_code_lines_before_skip(source: str, test_name: str, skip_line: int) -> list[str]` (function) — Extract the actual code lines before the pytest.skip() line for display.
- `_extract_steps_before_skip(source: str, test_name: str, skip_line: int) -> list[str]` (function) — Extract the action steps (clicks, fills, etc.) before the pytest.skip() line.
- `_failure_context(saved_path: str, test_name: str, run_result: RunResult | None) -> tuple[str, str, int | None]` (function) — Best-effort failure context for the repair flow (B-041).
- `_find_skip_line_number(source: str, test_name: str) -> int | None` (function) — Find the line number (1-based) of the pytest.skip() in a test function.
- `_find_url_before_skip(source: str, test_name: str, skip_line: int) -> str | None` (function) — Find the URL the test navigates to before the pytest.skip() line.
- `_render_skip_repair_capture() -> None` (function) — Run codegen and capture the locator, then replace pytest.skip() in the test file.
- `_render_skip_repair_result() -> None` (function) — Show the skip repair result.
- `_render_skip_repair_waiting() -> None` (function) — Show explanation before opening the browser for skipped test fix.
