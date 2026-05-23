# Session Plan: AI-018 Evidence Tracker Module

## Goal
Implement `src/evidence_tracker.py` to wrap Playwright Page interactions. It records element bounding boxes, interaction types, step sequence, and run history, writing a `.evidence.json` sidecar file alongside screenshots after each test run. 

## Target Files
- **New File:** `src/evidence_tracker.py`
- **New File:** `tests/test_evidence_tracker.py`
- **New File:** `generated_tests/conftest.py`
- **Modified:** `.gitignore` (add `evidence/` and `!evidence/.gitkeep`)

## Implementation Specs & Rules
1. **Wrapper Methods:** Implement `navigate()`, `fill()`, `click()`, `assert_visible()`, and `write(status)`.
2. **Coordinates:** Both `bbox` (absolute pixels) and `viewport_pct` (percentage) must be stored. Call `locator.bounding_box()` to get coordinates.
3. **Execution History:** Tracker must read existing sidecars to increment `total_runs`, `passed_runs`, `failed_runs`, and per-step `run_count` without overwriting prior history.
4. **conftest.py Integration:** 
   - Define an `evidence_tracker` fixture.
   - Use `pytest_runtest_makereport` hook to collect pass/fail status.
   - Fixture extracts `condition_ref` and `story_ref` from the `@pytest.mark.evidence` marker and yields the tracker.
   - Call `tracker.write(status)` during fixture teardown.

## Completion Criteria
- Code must be fully typed.
- `bash fix.sh` (ruff + mypy) passes cleanly.
- `pytest tests/test_evidence_tracker.py -v` passes cleanly.
