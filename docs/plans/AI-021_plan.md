# Session Plan: AI-021 Gantt Timeline in Evidence Bundle

## Goal
Add a per-story test execution Gantt timeline into the evidence report to help visualize which path evaluations consume the most duration.

## Target Files
- **New File:** `src/gantt_utils.py`
- **New File:** `tests/test_gantt_utils.py`
- **Modified:** `streamlit_app.py`

## Implementation Specs & Rules
1. **Gantt Source Data:** Reads from `.evidence.json` sidecars specifically pulling `test.duration_s`, `test.status`, and `test.condition_ref`.
2. **Timeline Behavior:** 
   - Horizontal bars sized by execution duration per condition.
   - Dash bars representing pending or not-yet-run tests.
   - Color encodes `passed`/`failed` status.
3. **Click Interaction:** Clicking a bar expands a detail card below the chart showing spec ref, expected result, evidence notes, and step sequences.
4. **Grouping Modes:** 
   - By condition type (testing view)
   - By sprint (scrum view)
   - By source (AI/manual/automation)
5. **Summary Row:** Under the chart, include natural language sentences reporting fastest test, slowest test, and test automation coverage percentage.

## Completion Criteria
- Execution time parsers and visual mappers tested via `pytest tests/test_gantt_utils.py -v`.
- `bash fix.sh` clean.
