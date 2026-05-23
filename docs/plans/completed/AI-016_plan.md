# Session Plan: AI-016 Spec Analysis Stage

## Goal
Implement `src/spec_analyzer.py` to run *before* test generation. This parses the user's input (spec, user story, or acceptance criteria) and derives explicit `TestCondition` objects (boundary values, assumptions, negative conditions, etc.) so a tester can review them. 

## Target Files
- **New File:** `src/spec_analyzer.py`
- **New File:** `tests/test_spec_analyzer.py`
- **Modified:** `streamlit_app.py` (Add new stage logic before "Generate Tests" button)
- **Modified:** `src/prompt_utils.py` (Update system prompt to receive derived conditions instead of raw acceptance criteria text)

## Implementation Specs & Rules
1. **Four Analysis Steps:** Extract business rules, map boundary values (at-limit, below, above), surface ambiguities, derive specific test conditions.
2. **Condition Types Derived:** `happy_path`, `boundary`, `negative`, `exploratory`, `regression`, `ambiguity`.
3. **TestCondition Object Structure:**
   - `id` (e.g. `BC01.02`)
   - `type`
   - `text` (description)
   - `expected` (expected result)
   - `source` (spec clause reference)
   - `flagged` (bool for ambiguities)
   - `src` (`ai`, `manual`, or `automation`)
4. **Integration Focus:** No elaborate UI here; primarily backend logic + minimal Streamlit display. Full UI goes in AI-017.

## Completion Criteria
- Thoroughly tested with edge cases in `test_spec_analyzer.py`.
- `bash fix.sh` passes cleanly.
- `pytest tests/test_spec_analyzer.py -v` passes cleanly.
