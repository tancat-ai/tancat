# FEATURE_SPEC_AI023_locator_repair.md
## AI-023 — Interactive Locator Repair Loop

**Status:** Design complete — ready for implementation sessions
**Last updated:** 2026-05-01
**Depends on:** Evidence sidecar (AI-018 complete), `src/pytest_output_parser.py` (complete)
**Blocks:** Nothing — standalone feature
**Priority:** High — directly addresses the most frustrating part of the current workflow

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
The tool records what Playwright reports about that element and writes it back to the
test file.

This maps directly to how an automation tester would actually debug the problem —
open the page, find the element, copy the locator. The tool just removes the manual
file editing step at the end.

---

## Scope Constraints

**Only for locator failures, not assertion failures.**

A `TimeoutError waiting for locator` means the element could not be found — that is
a tool problem. An `AssertionError: expected "Cart" to contain text "Checkout"` means
the element was found but the page content is wrong — that is a test correctness
problem the tester must diagnose themselves. The repair loop never triggers for
assertion failures.

**Only in the Streamlit UI, not CI.**

Opening a headed browser requires an interactive display. The repair loop is a manual
assist feature, not an automated recovery mechanism. Generated tests must still be
deterministic and non-interactive when run headlessly in CI.

**One locator repair per invocation.**

The tester is shown the first unresolved locator failure and fixes it. After re-run,
if another failure appears, they can invoke the repair loop again. This keeps the
interaction simple and avoids the tester feeling overwhelmed by a list of failures
to fix all at once.

---

## Implementation Plan

Four Cline sessions in strict order. Do not combine sessions.

---

### Session 1 — `src/failure_classifier.py`

**What this session does:** Adds failure type classification to the existing pytest
output model. No UI changes. No browser. Fully unit-testable.

**Files created:**
- `src/failure_classifier.py`
- `tests/test_failure_classifier.py`

**Files touched:** None — classifier is a pure function that takes a `TestResult`
and returns a classification.

**`FailureCategory` enum:**

```python
class FailureCategory(StrEnum):
    LOCATOR_TIMEOUT    = "locator_timeout"      # TimeoutError waiting for locator
    STRICT_VIOLATION   = "strict_violation"     # resolved to N elements
    ASSERTION_FAILURE  = "assertion_failure"    # AssertionError on value/text
    NAVIGATION_ERROR   = "navigation_error"     # ERR_CONNECTION_REFUSED etc.
    OTHER              = "other"
```

**`FailureDetail` dataclass:**

```python
@dataclass
class FailureDetail:
    category: FailureCategory
    raw_locator: str | None      # the locator string that failed, extracted from error
    failure_url: str | None      # URL from evidence sidecar if available
    line_number: int | None      # line in the test file where the failure occurred
    error_message: str           # original error text
```

**`classify_failure(result: TestResult) -> FailureDetail` — detection patterns:**

| Category | Pattern to match in `error_message` |
|---|---|
| `LOCATOR_TIMEOUT` | `TimeoutError` + `waiting for` (case-insensitive) |
| `STRICT_VIOLATION` | `strict mode violation` OR `resolved to \d+ elements` |
| `ASSERTION_FAILURE` | starts with `AssertionError` without locator context |
| `NAVIGATION_ERROR` | `ERR_CONNECTION_REFUSED` OR `net::ERR_` |
| `OTHER` | anything else |

**Locator extraction for `LOCATOR_TIMEOUT`:**

Parse the locator string from the error message. Playwright timeout errors follow
the pattern:

```
TimeoutError: Timeout 5000ms exceeded.
...waiting for locator('page.locator("#submit-btn")')
```

Extract the string inside `locator('...')` as `raw_locator`. If the pattern does
not match, `raw_locator` is `None`.

**Unit tests required (minimum 8):**

- `test_classifies_timeout_as_locator_timeout`
- `test_classifies_strict_mode_as_strict_violation`
- `test_classifies_assertion_error_as_assertion_failure`
- `test_classifies_connection_refused_as_navigation_error`
- `test_extracts_locator_string_from_timeout_message`
- `test_returns_none_locator_when_not_extractable`
- `test_assertion_without_locator_context_is_not_locator_failure`
- `test_empty_error_message_returns_other`

**Session end gate:** `bash fix.sh` → `pytest tests/ -v` green → commit.

---

### Session 2 — `src/locator_repair.py` (file surgery, no browser)

**What this session does:** Adds the locator patching logic — given a test file path,
a line number or original locator string, and a replacement locator string, writes
the corrected line back to the file. No browser, no UI. Fully unit-testable with
temp files.

**Files created:**
- `src/locator_repair.py`
- `tests/test_locator_repair.py`

**Files touched:** None.

**`LocatorPatch` dataclass:**

```python
@dataclass
class LocatorPatch:
    test_file_path: str
    original_locator: str     # the string to find and replace
    replacement_locator: str  # the new locator from codegen
    line_number: int | None   # if known, used to narrow the replacement
    lines_changed: int = 0    # populated after apply()
```

**`apply_patch(patch: LocatorPatch) -> LocatorPatch`:**

1. Read the test file as a list of lines.
2. If `line_number` is set, search only within ±3 lines of that line for safety.
   Otherwise search the full file.
3. Replace the first occurrence of `original_locator` in the search range with
   `replacement_locator`.
4. If no occurrence found, raise `LocatorNotFoundError` with a clear message —
   never silently skip.
5. Write the file back.
6. Return the patch with `lines_changed` populated.

**`LocatorNotFoundError(Exception)`:** raised when the original locator cannot
be found in the file. Message must include the file path, the locator searched
for, and the line range searched.

**Important constraint:** The patch replaces the locator string only, not the
whole line. `page.locator("#old-id").click()` with a replacement of
`page.get_by_test_id("submit")` becomes
`page.get_by_test_id("submit").click()` — the `.click()` is preserved.

This requires splitting the locator from the action. Use a regex that captures
everything up to (but not including) the first `.` after the closing `)` of the
locator call.

**Unit tests required (minimum 8):**

- `test_patches_locator_in_simple_file`
- `test_preserves_action_after_locator`
- `test_patches_by_line_number_when_provided`
- `test_raises_when_locator_not_found`
- `test_does_not_modify_other_lines`
- `test_handles_get_by_test_id_replacement`
- `test_handles_get_by_role_replacement`
- `test_patch_records_lines_changed`

**Session end gate:** `bash fix.sh` → `pytest tests/ -v` green → commit.

---

### Session 3 — UI wiring in `streamlit_app.py`

**What this session does:** Adds the "Fix this locator" button to the run results
panel when a locator failure is detected. No browser session yet — clicking the
button prepares state and shows a clear explanation of what will happen next.

**Files touched:**
- `streamlit_app.py` — extend `display_run_button()` to classify failures and
  render repair buttons
- `src/failure_classifier.py` — imported (already exists from Session 1)

**New session state keys:**

```python
"repair_target": None  # FailureDetail | None — the failure selected for repair
"repair_status": None  # "waiting" | "patched" | "error" | None
"repair_message": None # str | None — result message shown to tester
```

**UI changes in `display_run_button()`:**

After the existing results table, for each failed test:

1. Call `classify_failure(result)` to determine category.
2. If `category == FailureCategory.LOCATOR_TIMEOUT` or `STRICT_VIOLATION`:
   - Render a `st.button("🔧 Fix this locator", key=f"repair_{result.name}")` below
     the failure detail line.
   - Button label includes the extracted locator string if available, e.g.
     `🔧 Fix locator: page.locator("#add-to-cart")`
3. If `category == FailureCategory.ASSERTION_FAILURE` or `NAVIGATION_ERROR`:
   - Render a muted info note: `ℹ️ This is an assertion failure — the element was
     found but the page content was unexpected. Review the test logic manually.`
   - No repair button.

**When the repair button is clicked:**

```python
st.session_state.repair_target = failure_detail
st.session_state.repair_status = "waiting"
st.rerun()
```

**Repair panel (rendered when `repair_status == "waiting"`):**

Show below the results table:

```
🔧 Locator Repair Mode

Failed locator: page.locator("#add-to-cart")
Test file: generated_tests/test_20260501_cart_flow.py

The browser will open at the page where this test got stuck.
Click the element you want to use as the locator.
The test file will be updated automatically.

[ Open browser and fix locator ]   [ Cancel ]
```

The "Open browser and fix locator" button sets `repair_status = "browser_requested"`
and calls `st.rerun()`. Browser launch is handled in Session 4.

**Session end gate:** `bash fix.sh` → `pytest tests/ -v` green → commit.
UI can be reviewed manually — the button renders and state transitions work.

---

### Session 4 — Browser integration (`src/locator_repair.py` extension)

**What this session does:** Adds the headed browser session to `src/locator_repair.py`
and wires it into the Streamlit repair panel. This is the only session that touches
Playwright directly.

**Files touched:**
- `src/locator_repair.py` — add `run_codegen_session()` function
- `streamlit_app.py` — handle `repair_status == "browser_requested"` state

**`run_codegen_session(url: str, timeout_seconds: int = 90) -> str | None`:**

Opens a headed Chromium browser at `url`, enables Playwright Inspector mode (which
highlights elements on hover and shows their locator), and waits up to
`timeout_seconds` for the tester to click an element.

Returns the locator string that Playwright reports for the clicked element, or
`None` if the session times out or the tester cancels.

Implementation uses `subprocess` to launch `playwright codegen <url>` and captures
the first recorded locator from its stdout. This keeps the Playwright session
isolated from the Streamlit process (same pattern as `scrape_page_context` uses
for the DOM scraper).

**Navigation to failure point:**

If the evidence sidecar for the failing test exists and contains
`steps[N].page.url`, pass that URL to `run_codegen_session` instead of the base
URL. The tester lands on the exact page where the test got stuck, not the
homepage.

URL resolution priority:
1. Evidence sidecar `failure_url` (most specific)
2. `st.session_state.get("base_url")` normalised (fallback)

**Subprocess contract:**

```bash
playwright codegen <url> --output /tmp/repair_locator_<timestamp>.py
```

Parse the output file for the first `page.locator(...)` or `page.get_by_*(...)` 
call. That is the replacement locator. Delete the temp file after reading.

**Streamlit repair panel when `repair_status == "browser_requested"`:**

```python
with st.spinner("⏳ Browser is open — click the element you want to use..."):
    replacement = run_codegen_session(
        url=st.session_state.repair_target.failure_url or base_url,
        timeout_seconds=120,
    )

if replacement:
    patch = LocatorPatch(
        test_file_path=st.session_state.saved_test_path,
        original_locator=st.session_state.repair_target.raw_locator,
        replacement_locator=replacement,
        line_number=st.session_state.repair_target.line_number,
    )
    try:
        apply_patch(patch)
        st.session_state.repair_status = "patched"
        st.session_state.repair_message = (
            f"✅ Locator patched: `{replacement}`\n"
            f"Changed {patch.lines_changed} line(s) in `{patch.test_file_path}`\n"
            "Click **▶️ Run Now** to verify the fix."
        )
    except LocatorNotFoundError as e:
        st.session_state.repair_status = "error"
        st.session_state.repair_message = f"❌ Could not patch: {e}"
else:
    st.session_state.repair_status = "error"
    st.session_state.repair_message = (
        "❌ No locator captured. The browser may have timed out or been closed."
    )

st.rerun()
```

**After patching — success state:**

Show the patch result message. Show the updated code block (re-read from file).
Show a "▶️ Re-run this test" button that runs only the patched test via
`pytest <test_file>::<test_name> -v` (same pattern as existing re-run failed).

**Session end gate:** `bash fix.sh` → `pytest tests/ -v` green → manual end-to-end
test on a real page before committing. The repair loop must complete at least one
full cycle (detect failure → open browser → click element → patch file → re-run)
successfully before this session is considered done.

---

## File Summary

| File | Session | New / Modified |
|------|---------|----------------|
| `src/failure_classifier.py` | 1 | New |
| `tests/test_failure_classifier.py` | 1 | New |
| `src/locator_repair.py` | 2, 4 | New |
| `tests/test_locator_repair.py` | 2 | New |
| `streamlit_app.py` | 3, 4 | Modified |

---

## What This Does Not Do

These are explicit non-goals — do not add them without a new design session.

**No automatic locator guessing.** The tool does not attempt to find a replacement
locator by itself. It only records what the tester clicks. Any attempt to infer a
replacement from the DOM would reproduce the exact problem the feature is designed
to avoid.

**No batch repair.** One locator failure per invocation. If three tests fail on
locators, the tester fixes them one at a time and re-runs between each fix. This
is intentional — it keeps each repair verifiable before moving to the next.

**No repair in CI.** The headed browser requirement is a hard constraint.
Nothing in this feature should touch the CI pipeline.

**No modification of evidence sidecars.** After patching, the existing sidecar
from the failed run is left as-is. It is historical evidence of what failed and
why. The next run produces a new sidecar reflecting the patched test.

---

## Accessibility Tree Improvement (related, separate item)

During the design of AI-023 it was identified that the DOM scraper misses
accessibility-tree attributes that browsers compute from parent elements, ARIA
relationships, and SVG child elements. These are precisely the attributes a tester
would find if they opened DevTools.

This is a separate improvement, not part of AI-023. It should be tracked as
**AI-024 — Accessibility Tree Enrichment** and scoped to `src/page_context_scraper.py`
adding a `page.accessibility.snapshot()` call alongside the existing DOM scraping
in `_extract_context()`. Elements without `aria-label` in raw HTML but with a
computed accessible name from the accessibility tree get that name added to their
`PageElement.label` field.

AI-024 can be implemented independently in a single session and will reduce the
frequency of locator failures that trigger AI-023.

---

## Backlog Entry (copy into BACKLOG.md)

```
### AI-023 — Interactive Locator Repair Loop
**What:** When a generated test fails with a locator error (TimeoutError or strict
mode violation), the tool offers an interactive repair mode. A headed browser opens
at exactly the page where the test got stuck. The tester clicks the element they
want. The tool captures the locator Playwright reports for that click and patches
it directly into the test file. The tester then re-runs to verify.

**Why:** This closes the loop between "test generated" and "test working." Currently
locator failures require the tester to debug the DOM manually and edit the file
themselves — work the tool should handle. This feature maps directly to what an
automation tester would do: open the page, find the element, copy the locator.

**Spec:** docs/FEATURE_SPEC_AI023_locator_repair.md

**New files:**
- src/failure_classifier.py — classify pytest failure type from error message
- tests/test_failure_classifier.py
- src/locator_repair.py — patch locator in test file + codegen browser session
- tests/test_locator_repair.py

**Modified files:**
- streamlit_app.py — repair button on locator failures, browser session state

**Implementation sequence (4 Cline sessions, strict order):**
1. src/failure_classifier.py + tests
2. src/locator_repair.py patch logic + tests (no browser)
3. streamlit_app.py UI — repair button and state transitions (no browser)
4. src/locator_repair.py codegen session + full wiring in streamlit_app.py

**Constraints:**
- Locator failures only — assertion failures get an explanation note, no repair button
- Streamlit UI only — not available in CI or headless runs
- One locator repair per invocation — not batch
- Never guesses a replacement — only records what the tester clicks

**Related:** AI-024 (Accessibility Tree Enrichment) reduces locator failure frequency
independently of this feature.

**Priority:** High
**Design session:** Complete — 2026-05-01
```
