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
| `_extract_step_points_by_url(sidecar)` | Extracts (points_by_url, frames_by_url) from one sidecar; every step is attributed to the page it RAN on |
| `list_evidence_urls(evidence_dir)` | The page URLs that have evidence points, most-covered first (drives the heatmap picker and the report's heatmap section) |
| `generate_suite_heatmap(evidence_dir, page_url, max_width=0, instance="")` | Renders per-URL heatmap as HTML with SVG circle overlays |

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
- Each step is attributed to the page it RAN on (B-105): a click is measured before it
  runs, so a link that navigates keeps its marker on the page it was measured on. The
  page a step ran on is the page the previous step left us on, or the step's own
  recorded measurement URL (`element.measured_url`).
- Background screenshot: the frame of that page that most of the points were measured
  in. A percentage is only meaningful against the document it came from, so a point
  measured on a different page layout is reported ("Not drawn: N"), never drawn on the
  wrong frame.
- Aggregates elements within 2% tolerance at same (x, y) position. A point inside the
  tolerance MERGES into the element it matched — the old code overwrote it, so an
  element hit by eight tests showed one hit and the status of the last hit only.
- The dominant status is the most common one; on a tie the worse status wins (an
  element that failed once out of two attempts did fail).
- A page arrival (a navigate step) is evidence that the page was reached, not an
  element hit: it is counted, never merged into an element.
- Status per point: passed, failed, partial_pass, skipped from step result
- Returns HTML with inline SVG overlay showing colored circles on screenshot
- Circle size proportional to the number of hits, colored by dominant status
- Filter buttons for all/passed/partial/failed views
- Element details table with hover highlighting
- Uses ResizeObserver for responsive SVG resizing
- Each heatmap scopes its script to its own root (`suite-heat-<id>`), so a report can carry one heatmap per page without the instances drawing on each other
- `max_width` embeds the background as a downscaled preview (the embed-size policy)

## How It Works (Internals)

Private `_`-helpers - the module's real logic (5 items). Grouped under the public function that calls them.

### `generate_suite_heatmap(*, evidence_dir: Path, page_url: str) -> str` - function

- `_normalise_url(url: str) -> str` (function): Normalise URLs for matching across redirects and trailing slashes.
- `_safe_embed_image_data_uri(image_path: Path) -> str | None` (function): Safe embed image data uri; calls `b64encode`, `decode`, `read_bytes`; returns str | None.
- `_extract_step_points_by_url(sidecar: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]` (function): Return (points_by_url, frames_by_url) from one sidecar. Every step is attributed to the page it RAN on, not the page it ended on: a click is measured before it runs, so a link that navigates would otherwise move its own marker to the destination page (B-105).
- `_point_matches_frame(point: dict[str, Any], frame: dict[str, Any]) -> bool` (function): Whether a point may be drawn on a frame — the document sizes must match; a sidecar or frame that does not record its size is accepted and reported as unverified.
- `_dominant_status(status_counts: dict[str, int]) -> str` (function): The status that best describes an element — the most common one; on a tie the worse status wins.

### `build_story_confidence(evidence_dir: Path, *, test_plan_state: dict[str, Any] | None = None) -> list[StoryConfidence]` - function

- `_safe_read_json(path: Path) -> dict[str, Any] | None` (function): Safe read json; calls `loads`, `read_text`; returns dict[str, Any] | None.
- `_extract_confirmed_ids(test_plan_state: dict[str, Any] | None, story_ref: str) -> set[str]` (function): Extract confirmed ids; returns set[str].
