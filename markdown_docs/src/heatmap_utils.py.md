# `src/heatmap_utils.py`

## Purpose
Coverage confidence heatmap aggregation from EvidenceTracker sidecars. Includes Tier 3 per-URL suite heatmap rendering (moved from `src/evidence_report.py`). Produces Plotly treemaps and interactive HTML heatmaps with SVG overlays.

## Metadata
- **Lines:** 719
- **Imports:** base64, json, dataclasses.dataclass, pathlib.Path, typing.Any|Literal, pandas, plotly.express, plotly.graph_objects, src.report_builder.escape_html

## Classes/Dataclasses
| Class | Description |
|-------|-------------|
| `StoryConfidence` | Frozen dataclass: story_ref, level, color, total/passed/failed/skipped_conditions |

## Type Aliases
| Type | Values |
|------|--------|
| `ConfidenceLevel` | Literal["tester_confirmed", "ai_covered_unreviewed", "partial_pending", "gap_open_question", "not_in_scope"] |

## Constants
| Constant | Description |
|----------|-------------|
| `CONFIDENCE_COLORS` | Maps ConfidenceLevel to hex colors (green→light green→yellow→red→secondary bg) |
| `_STATUS_COLORS` | passed=green, partial_pass=yellow, failed=red, skipped=gray |
| `_EVIDENCE_STEP_COLORS` | navigate=pink, fill=green, click=blue, assertion=brown |

## Functions
| Function | Description |
|----------|-------------|
| `_normalise_url(url)` | Normalizes URLs: lowercases scheme/netloc, strips trailing slashes |
| `_safe_read_json(path)` | Reads JSON file — returns None if missing or invalid |
| `_safe_embed_image_data_uri(image_path)` | Reads image file → base64 data URI with correct MIME type |
| `_extract_confirmed_ids(test_plan_state, story_ref)` | Extracts confirmed condition IDs from test plan state |
| `build_story_confidence(evidence_dir, test_plan_state)` | Aggregates .evidence.json into StoryConfidence list per story |
| `build_confidence_heatmap(stories)` | Builds Plotly treemap for story confidence levels |
| `_extract_step_points_by_url(sidecar)` | Extracts (points_by_url, bg_screenshot_by_url) from one sidecar |
| `generate_suite_heatmap(evidence_dir, page_url)` | Renders per-URL heatmap as HTML with SVG circle overlays |

## Key Logic

### Story Confidence Aggregation
- Groups sidecars by `story_ref`, counts passed/failed/skipped per condition
- Confidence ladder: failed>0 → gap_open_question; no sidecars → partial_pending; all confirmed → tester_confirmed; else → ai_covered_unreviewed
- `confirmed_ids` from test_plan_state can be global set or per-story mapping

### Confidence Heatmap (Plotly)
- Uses `px.treemap` with path=["Confidence", "Story"] for hierarchical grouping
- Equal sizing per story (Value=1), colored by confidence level
- Hover shows Passed/Failed/Skipped/Total

### Tier 3 Per-URL Suite Heatmap
- Aggregates all evidence points across sidecars for one normalized URL
- Tracks current URL as navigate steps occur, groups screenshots into URL segments
- Background screenshot selection: assertion screenshots (priority 3) > meaningful interaction (2) > navigate (0)
- Deprioritizes consent/overlay/cookie screenshots
- Aggregates elements within 2% tolerance at same (x, y) position
- Status per point: passed, failed, partial_pass, skipped from step result
- Returns HTML with inline SVG overlay showing colored circles on screenshot
- Circle size proportional to run_count, colored by dominant status
- Filter buttons for all/passed/partial/failed views
- Element details table with hover highlighting
- Uses ResizeObserver for responsive SVG resizing