# Session Plan: AI-022 Coverage Heat Map

## Goal
Implement a cross-story, cross-sprint test coverage confidence heat map.

## Target Files
- **New File:** `src/heatmap_utils.py`
- **New File:** `tests/test_heatmap_utils.py`
- **Modified:** `streamlit_app.py` 

## Implementation Specs & Rules
1. **Heat Map Data Aggregation:** Aggregates confidence levels from all `evidence/*.evidence.json` sidecars + `test_plan` session states locally.
2. **Confidence Color Mapping (Fixed Requirement):**
   - Tester confirmed: `#1D9E75` (dark teal)
   - AI covered, unreviewed: `#9FE1CB` (light teal)
   - Partial / pending: `#FAC775` (amber)
   - Gap / open question: `#F09595` (red)
   - Not in scope: `var(--color-background-secondary)`
3. **Interactivity:** Cells expand with detailed condition states on click. Sprint-over-sprint trend charts to be maintained directly underneath.
4. **Dimensions/Groupings:**
   - By condition type
   - By sprint
   - By source

## Completion Criteria
- Rigorous data accumulation validation via `pytest tests/test_heatmap_utils.py -v` to deal with missing folders/logs correctly.
- `bash fix.sh` clean.
