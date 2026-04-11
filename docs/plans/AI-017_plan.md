# Session Plan: AI-017 Living Test Plan UI

## Goal
Implement a Living Test Plan UI (`display_test_plan()` in Streamlit) where a tester can review, edit, add, or remove AI-derived conditions. Generation is blocked until all conditions are reviewed and signed off by the tester.

## Target Files
- **New File:** `src/test_plan.py`
- **New File:** `tests/test_test_plan.py`
- **Modified:** `streamlit_app.py`

## Implementation Specs & Rules
1. **Core Data Structure:** Create `TestPlan` dataclass in `src/test_plan.py` capturing `story_ref`, `sprint`, `conditions`, `confirmed_ids` (set), `sign_off_notes`, `tester_name`, and `sign_off_date`.
2. **Logic Abstraction:** Any filtering, sorting, or condition-manipulation logic goes in `src/test_plan.py`. Do NOT place logic directly in `streamlit_app.py`.
3. **Session State Usage (`streamlit_app.py`):**
   - Use `test_plan` to hold the list of `TestCondition` objects.
   - Use `plan_confirmed` bool flag (True when all checked off).
4. **Tester Capabilities:**
   - Edit any condition's text/expected result/source reference.
   - Remove conditions.
   - Add new manual tests (with steps) and automation tests (with locators).
   - Flag conditions requiring PO clarification.
   - Click a "sign-off" button (unlocks test generation).

## Completion Criteria
- Test plan CRUD operations fully tested via `pytest tests/test_test_plan.py -v`.
- `bash fix.sh` clean.
