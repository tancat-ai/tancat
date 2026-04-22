# FEATURE SPEC — Run Results & Report Improvements
## AI-008

**Status:** Ready for implementation  
**Priority:** High — demo quality depends on this  
**Protected files:** src/llm_client.py, src/test_generator.py, main.py  
**New files:** `src/pytest_output_parser.py`, `tests/test_pytest_output_parser.py`  
**Modified files:** `streamlit_app.py`

---

## Problem

The current run output is:

1. **Broken** — session state bug wipes results immediately after setting them
2. **Unreadable** — raw pytest stdout dumped into a `st.code()` block
3. **Disconnected** — pass/fail results have no link back to coverage criteria
4. **Incomplete** — HTML report contains only static coverage, not actual run results

---

## Bug Fix — Session State (Do This First)

In `display_run_button()`, lines 591-594:

```python
# CURRENT (broken):
st.session_state.last_run_success = success
st.session_state.last_run_output = output
st.session_state.last_run_success = None    # ← wipes it immediately
st.session_state.last_run_output = ""       # ← wipes it immediately

# FIX:
st.session_state.last_run_success = success
st.session_state.last_run_output = output
# remove the two None/empty lines entirely
```

---

## New Module — `src/pytest_output_parser.py`

Parse raw pytest stdout into structured data. No Streamlit imports.
Must be fully unit testable.

### Dataclasses

```python
@dataclass
class TestResult:
    name: str              # "test_01_login_page_displayed"
    status: str            # "passed" | "failed" | "error"
    duration: float        # seconds, 0.0 if not available
    error_message: str     # "" if passed, short error if failed
    file_path: str         # relative path to test file

@dataclass
class RunResult:
    results: list[TestResult]
    total: int
    passed: int
    failed: int
    errors: int
    duration: float        # total run duration in seconds
    raw_output: str        # preserve original for expander
```

### Functions

```python
def parse_pytest_output(raw: str) -> RunResult:
    """
    Parse raw pytest -v output into structured RunResult.
    
    Handles these pytest output patterns:
    
    PASSED line:
      test_file.py::test_01_login_page_displayed PASSED [ 50%]
    
    FAILED line:
      test_file.py::test_02_inventory FAILED [100%]
    
    Duration line (at end):
      2 passed, 1 failed in 3.45s
      3 passed in 1.20s
    
    Error message (after FAILED):
      FAILED test_file.py::test_name - AssertionError: expected...
    """
```

### Parsing logic

```python
# Regex patterns to match:
PASSED_RE = re.compile(r"(\S+\.py)::(\S+)\s+PASSED")
FAILED_RE = re.compile(r"(\S+\.py)::(\S+)\s+FAILED")
DURATION_RE = re.compile(r"(\d+) passed(?:, (\d+) failed)? in ([\d.]+)s")
ERROR_RE = re.compile(r"FAILED \S+::(\S+) - (.+)")
```

---

## Updated UI — `display_run_button()`

Replace the raw `st.code()` block with a structured results panel.

### Pass state

```
✅ All tests passed — 3/3 in 2.1s

┌─────────────────────────────────────────┬────────┬──────────┐
│ Test                                    │ Result │ Duration │
├─────────────────────────────────────────┼────────┼──────────┤
│ test_01_login_page_displayed            │ ✅ Pass │  1.2s   │
│ test_02_inventory_displayed             │ ✅ Pass │  0.5s   │
│ test_03_add_to_cart                     │ ✅ Pass │  0.4s   │
└─────────────────────────────────────────┴────────┴──────────┘

📄 Raw Output  ▼  (collapsed by default when all pass)
```

### Fail state

```
❌ 1 test failed — 2 passed, 1 failed in 4.1s

┌─────────────────────────────────────────┬────────┬──────────┐
│ Test                                    │ Result │ Duration │
├─────────────────────────────────────────┼────────┼──────────┤
│ test_01_login_page_displayed            │ ✅ Pass │  1.2s   │
│ test_02_inventory_displayed             │ ✅ Pass │  0.5s   │
│ test_03_add_to_cart                     │ ❌ Fail │  2.4s   │
└─────────────────────────────────────────┴────────┴──────────┘

⚠️  test_03_add_to_cart
    AssertionError: Expected element "Add to cart" to be visible

📄 Raw Output  ▼  (expanded by default when tests fail)
```

### Implementation in streamlit_app.py

```python
# After run_result = parse_pytest_output(run_output):

# Summary line
if run_result.failed == 0:
    st.success(f"✅ All tests passed — {run_result.passed}/{run_result.total} in {run_result.duration:.1f}s")
else:
    st.error(f"❌ {run_result.failed} test{'s' if run_result.failed > 1 else ''} failed — "
             f"{run_result.passed} passed, {run_result.failed} failed in {run_result.duration:.1f}s")

# Results table
rows = []
for r in run_result.results:
    icon = "✅ Pass" if r.status == "passed" else "❌ Fail"
    duration = f"{r.duration:.1f}s" if r.duration > 0 else "—"
    rows.append({"Test": r.name, "Result": icon, "Duration": duration})

st.dataframe(
    rows,
    use_container_width=True,
    hide_index=True,
)

# Failure detail — show error message for each failed test
for r in run_result.results:
    if r.status == "failed" and r.error_message:
        st.warning(f"⚠️ **{r.name}**\n\n`{r.error_message}`")

# Raw output expander
with st.expander("📄 Raw Output", expanded=run_result.failed > 0):
    st.code(run_result.raw_output, language="plaintext")
```

---

## Coverage + Results Integration

Connect test run results to coverage criteria in `display_coverage()`.

Add `run_result: RunResult | None = None` parameter to `display_coverage()`.

When run results are available, add a Result column to the coverage table:

```
┌────────┬──────────────────────────────────┬─────────┬────────────────────────────┬────────┐
│ ID     │ Requirement                      │ Status  │ Test                       │ Result │
├────────┼──────────────────────────────────┼─────────┼────────────────────────────┼────────┤
│ TC-001 │ Login form fields visible        │ covered │ test_01_login_page_...     │ ✅     │
│ TC-002 │ Enter username and password      │ covered │ test_01_login_page_...     │ ✅     │
│ TC-003 │ LOGIN button present             │ covered │ test_02_inventory_...      │ ✅     │
│ TC-004 │ Redirect on valid credentials    │ covered │ test_02_inventory_...      │ ✅     │
│ TC-005 │ Inventory displays products      │ covered │ test_03_add_to_cart        │ ❌     │
└────────┴──────────────────────────────────┴─────────┴────────────────────────────┴────────┘
```

Implementation: after run, look up each `RequirementCoverage.linked_tests[0].name`
in `run_result.results` by name match to get pass/fail status.

Store `RunResult` in session state as `last_run_result` (parsed object, not raw string).

---

## Updated HTML Report

`_generate_html_report()` needs a `run_result` parameter.

When run_result is provided, add a Results section above the Coverage section:

```html
<h2>🏃 Test Run Results</h2>
<p>2 passed, 1 failed in 4.1s — Run at 2026-03-09 14:32:01</p>
<table>
  <tr><th>Test</th><th>Result</th><th>Duration</th></tr>
  <tr><td>test_01_login_page_displayed</td><td>✅ Pass</td><td>1.2s</td></tr>
  <tr><td>test_02_inventory_displayed</td><td>✅ Pass</td><td>0.5s</td></tr>
  <tr><td>test_03_add_to_cart</td><td class="fail">❌ Fail</td><td>2.4s</td></tr>
</table>

<h2>📊 Coverage Analysis</h2>
<!-- existing coverage table, now with Result column -->
```

Add CSS for pass/fail colours:
```css
.pass { color: #2e7d32; font-weight: bold; }
.fail { color: #c62828; font-weight: bold; }
.pending { color: #e65100; }
```

---

## Session State Changes

Add to `_session_defaults`:

```python
"last_run_result": None,   # RunResult object from parser
```

Clear `last_run_result` when generate button is pressed (same as
`last_run_success` and `last_run_output`).

Pass `st.session_state.last_run_result` to `display_coverage()` and
`_generate_html_report()` in the output section.

---

## Unit Tests — `tests/test_pytest_output_parser.py`

Minimum 10 tests covering:

```python
class TestParsePytestOutput:
    def test_parses_all_passed(self) -> None: ...
    def test_parses_mixed_pass_fail(self) -> None: ...
    def test_extracts_test_names(self) -> None: ...
    def test_extracts_duration(self) -> None: ...
    def test_failed_count_correct(self) -> None: ...
    def test_passed_count_correct(self) -> None: ...
    def test_error_message_extracted(self) -> None: ...
    def test_handles_empty_output(self) -> None: ...
    def test_handles_collection_error(self) -> None: ...
    def test_preserves_raw_output(self) -> None: ...
```

Use real pytest output strings as fixtures — copy from actual runs.

---

## Implementation Order

1. Fix session state bug (2 lines) → run `pytest tests/ -v` to confirm still passing
2. Create `src/pytest_output_parser.py` with dataclasses and `parse_pytest_output()`
3. Write `tests/test_pytest_output_parser.py` — all tests passing before touching UI
4. Update `display_run_button()` — replace raw code block with structured table
5. Add `run_result` to session state, pass to `display_coverage()`
6. Update `_generate_html_report()` to include run results
7. Run full `ruff check . && mypy streamlit_app.py src/ && pytest tests/ -v`

---

## Acceptance Criteria

- [ ] Bug fix: run results persist after download button clicks
- [ ] Results table shows each test name, pass/fail, duration
- [ ] Failed tests show error message inline below table
- [ ] Coverage table shows run result per criterion when available
- [ ] HTML report includes run results section
- [ ] `pytest tests/ -v` passes with no new failures
- [ ] `mypy streamlit_app.py src/` passes clean
- [ ] `pytest_output_parser.py` has ≥10 unit tests all passing

---

*Created: 2026-03-09*  
*Author: Session 5 planning*
