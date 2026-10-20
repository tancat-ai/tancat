# `src/evidence_report.py`

## High-Level Purpose
Evidence/annotated report generators that read `.evidence.json` sidecar files and produce interactive HTML visualizations with SVG overlays, heatmaps, and journey views.

## Module Metadata
- **Lines:** 760
- **Imports:** `__future__`, `base64`, `json`, `re`, `dataclasses`, `pathlib`, `typing`, `urllib.parse`, `src.report_builder.escape_html`

## Functions

### `generate_annotated_screenshot(*, sidecar_path, view_mode, title, max_width=0, instance="") -> str`
Returns interactive HTML with SVG overlays. Every marker is drawn on the frame it was
measured in (B-105): a marker's percentage is only meaningful against the document it
came from, so a marker whose frame cannot be confirmed is not drawn and the step list
says why. View modes: `annotated`, `heatmap`, `clean`.

`max_width` embeds the frames as downscaled previews (the embed-size policy) and says so;
`instance` scopes the viewer's script to its own block, so a report can carry one overlay
per test without the instances drawing on each other.

### `overlay_counts(sidecar_path) -> tuple[int, int]`
Returns (frames, markers) the annotated viewer would draw for a sidecar - what the report
puts in the overlay's summary line before the reader opens it.

### `build_evidence_frames(steps) -> list[EvidenceFrame]`
One frame per distinct screenshot in the sidecar, each carrying the URL it shows and the
size of the document it captured.

### `match_frame(frames, *, doc_width, doc_height, own_rel_path, step_index) -> FrameMatch`
The frame a marker measured in that document may be drawn on. Only a frame of exactly
that size is a legal target; a sidecar without the sizes falls back to the step's own
frame and reports the match as unverified.

### `generate_annotated_journey(*, sidecar_path, view_mode, title) -> str`
Multi-page journey viewer with segment selector for tests navigating across URLs.

### `list_evidence_from_package(package_dir: str) -> TestPackageEvidence`
Scans test package directory for `*.evidence.json` files, returns aggregated data.

### `generate_package_report(*, package_dir, view_mode, title) -> str`
Generates consolidated HTML report for an entire test package.

## Classes

### `EvidenceFrame` (dataclass)
One captured page state: the screenshot path, the URL it shows, the document size it
captured, and the index of the step that captured it.

### `FrameMatch` (dataclass)
Where a marker may be drawn: the frame, whether the placement is confirmed, and the
reason when it is not.

### `EvidenceEntry` (dataclass)
Single evidence record: timestamp, action, selector, status, screenshot_path, notes.

### `TestPackageEvidence` (dataclass)
Aggregated evidence from a test package: test_files, entries, failures, total_duration.

## Key Design Decisions
- Base64-embedded screenshots for portable HTML reports
- SVG overlay for visual annotations on screenshots
- Three view modes for different analysis needs

## Dependencies
- `src.report_builder.escape_html`
- stdlib for everything else

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `EvidenceFile` (class)

Represents a single evidence sidecar file.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (12 items). Grouped under the public function that uses them:

### `generate_annotated_journey`
- `_build_bug_report_text(sidecar_path: Path, sidecar: dict[str, Any], image_data_uri: str = '', title: str = '') -> str` (function) — Build a plain-text bug report from the evidence sidecar.
- `_build_step_row_html(step: dict[str, Any], idx: int) -> str` (function) — Render a single step as a compact timeline row.
- `_empty_result(msg: str, bug_report_mode: bool) -> str` (function) — (no docstring)
- `_find_best_screenshot(steps: list[dict[str, Any]]) -> str` (function) — Find the most informative screenshot from steps (prefer failure or last assertion).
- `_is_failed_step(step: dict[str, Any]) -> bool` (function) — Check if a step resulted in a failure.

### `generate_annotated_screenshot`
- `_build_overlay_model(steps: list[dict[str, Any]]) -> dict[str, Any]` (function) — Work out which captured frame every step's marker belongs on.
- `_prepare_steps_for_display(steps: list[dict[str, Any]], notes: dict[int, str] | None = None) -> list[dict[str, Any]]` (function) — Return steps with labels normalized for UI rendering.
- `_resolve_evidence_image(sidecar_path: Path, rel_path: str) -> Path` (function) — Resolve a screenshot path recorded in a sidecar to a file on disk.
- `_safe_embed_image_data_uri(image_path: Path) -> str | None` (function) — (no docstring)
- `_safe_read_json(path: Path) -> dict[str, Any] | None` (function) — (no docstring)

### Internal utilities
- `_as_int(value: Any) -> int | None` (function) — Return *value* as an int, or None when it is not a usable number.
- `_clean_evidence_label(label: str) -> str` (function) — Convert raw placeholder-token labels into cleaner user-facing text.
- `_format_label(label: str, matched_text: str | None = None, truncate: int = 80) -> str` (function) — Format a step label with optional matched text for user display.
- `_normalise_url(url: str) -> str` (function) — Normalise URLs for matching across redirects and trailing slashes.
- `_step_type_key(step: dict[str, Any]) -> str` (function) — (no docstring)
