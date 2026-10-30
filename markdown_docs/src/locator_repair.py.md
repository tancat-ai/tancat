# `src/locator_repair.py`

## High-Level Purpose

Surgical replacement of a broken locator in a generated test file. Replaces only the locator string while preserving the surrounding action (`.click()`, `.fill()`, etc.). Design-time only — not used at test runtime.

## Module Metadata

- **Lines:** 475
- **Imports:** `re`, `dataclasses`, `pathlib.Path`

## Data Classes

### `LocatorPatch`

Describes a single locator replacement.
- `original_locator: str` — The broken locator string from the error
- `repaired_locator: str` — The corrected locator (e.g., from codegen)
- `line_number: int` — 1-based line in the generated test to patch
- `test_file: str | Path` — Path to the generated test file

### `LocatorRepairError(Exception)`

Raised when the target locator could not be found on the expected line.

## Functions

### `apply_patch(patch: LocatorPatch) -> str`

Apply a locator patch to the test source and return the patched source. Finds the line containing `original_locator`, replaces only the locator string inside `.locator("...")`, preserves the action. Searches +/- 10 lines around reported line number since Playwright error lines don't always match the locator call line.

**B-042 hardening:**
- The reconstruction re-applies the original line's leading indentation, so a patched line inside a test function can never be dedented to module scope (which broke collection with `NameError` / 1 error, 0 tests).
- An empty `original_locator` (which would match every line in the search window and then mangle the file via `str.replace("", …)`) raises `LocatorRepairError` instead.

### `apply_patch_to_file(patch: LocatorPatch) -> None`

Apply a locator patch and write the result back to disk.

### `extract_locator_from_line(line: str) -> str | None`

Extract the locator string from a single line of test code. Looks for `.locator("...")` pattern.

### `apply_fix_from_codegen(outcome, *, original_locator, line_number, test_file, step_label="", step_type="", page_url="", site_name="", store=None) -> ManualFixOutcome` (j-0248)

The manual Fix Locator path end to end: apply the human's captured locator to
the test file and, **only if that write really happened**, record it as a
learned pattern for that site through `src.rag_learn.learn_from_manual_fix`
(the same write route the automatic repair uses). An abandoned session, a
failed session, a recording with no locator, or a patch that fails to apply
returns `applied=False` and writes nothing. The fix is still applied when
learning is switched off or has no usable description/site — the outcome's
`learned` dict says why it was not learned. Used by both the Streamlit repair
panel and the CLI's `repair_locator_cli`.

### `ManualFixOutcome` (dataclass) — `applied`, `reason`, `patch`, `learned`

What an attempt actually did. `applied` is the only thing that permits
learning.

### `pick_repair_step(steps)` / `repair_step_context(test_file, test_name)` (j-0248)

The one sidecar reader for the repair surfaces: `pick_repair_step` walks back
from a failed assertion to the interaction a human can replay, and
`repair_step_context` returns that step's `(label, url, type)` from the
evidence sidecar. Shared by the UI and the CLI so the two cannot drift; the UI
re-exports `pick_repair_step` under its old private name.

## Dependencies

None (stdlib only).

## Depended On By

Test repair workflows, CI auto-fix pipelines

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 3 items):

### `SetupScriptResult` (class)

Result of running prerequisite steps before a codegen session.

### `translate_setup_step_to_python(step: str) -> list[str]` (function)

Translate a generated test step line into Playwright setup script lines.

### `run_codegen_session(url: str, timeout_seconds: int = 120, state_file: str | None = None) -> str | None` (function)

Launch headed Playwright codegen and capture the first locator from the recorded script.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### `apply_patch`
- `_find_locator_action_line(source: str, line_number: int, original_locator: str) -> tuple[int, str]` (function) — Return (0-based index, raw_line) for the line containing *original_locator*.
