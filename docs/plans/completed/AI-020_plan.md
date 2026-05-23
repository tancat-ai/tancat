# Session Plan: AI-020 Annotated Screenshot Evidence View

## Goal
Extend `src/report_utils.py` to read `.evidence.json` sidecars and render an interactive SVG overlay over screenshots. Uses interaction bounds to draw numbered, sized circles denoting execution path/count.

## Target Files
- **Modified:** `src/report_utils.py`
- **Modified:** `streamlit_app.py` (evidence tab addition)

## Implementation Specs & Rules
1. **New Function:** `generate_annotated_screenshot()` in `report_utils.py`
2. **Overlay Logic:** Render SVG on top of each screenshot image. The layer remains interactive.
3. **View Modes:** 
   - `annotated` (numbered circles with type colors)
   - `heatmap` (density rings)
   - `clean` (raw image)
4. **Hover Interactivity:** Hovering a circle highlights the timeline step (synced via `hoveredId` or similar).
5. **Coordinate Rendering:** Uses `viewport_pct` data from the JSON sidecar, scaling dynamically (`(viewport_pct.x / 100) * container_width`).
6. **Circle Formula & Colors:**
   - `base_radius = 14 + min(run_count * 0.7, 20)`
   - Navigate: `#993556`, Fill: `#0F6E56`, Click: `#185FA5`, Assertion: `#854F0B`

## Completion Criteria
- `bash fix.sh` clean.
- Ensure HTML generation passes cleanly without unexpected layout shifts.
