# `src/evidence_report.py`

## High-Level Purpose
Evidence/annotated report generators that read `.evidence.json` sidecar files and produce interactive HTML visualizations with SVG overlays, heatmaps, and journey views.

## Module Metadata
- **Lines:** 760
- **Imports:** `__future__`, `base64`, `json`, `re`, `dataclasses`, `pathlib`, `typing`, `urllib.parse`, `src.report_builder.escape_html`

## Functions

### `generate_annotated_screenshot(*, sidecar_path, view_mode, title) -> str`
Returns interactive HTML with SVG overlay on a single screenshot. View modes: `annotated`, `heatmap`, `clean`.

### `generate_annotated_journey(*, sidecar_path, view_mode, title) -> str`
Multi-page journey viewer with segment selector for tests navigating across URLs.

### `list_evidence_from_package(package_dir: str) -> TestPackageEvidence`
Scans test package directory for `*.evidence.json` files, returns aggregated data.

### `generate_package_report(*, package_dir, view_mode, title) -> str`
Generates consolidated HTML report for an entire test package.

## Classes

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
- `_prepare_steps_for_display(steps: list[dict[str, Any]]) -> list[dict[str, Any]]` (function) — Return steps with labels normalized for UI rendering.
- `_safe_embed_image_data_uri(image_path: Path) -> str | None` (function) — (no docstring)
- `_safe_read_json(path: Path) -> dict[str, Any] | None` (function) — (no docstring)

### Internal utilities
- `_clean_evidence_label(label: str) -> str` (function) — Convert raw placeholder-token labels into cleaner user-facing text.
- `_format_label(label: str, matched_text: str | None = None, truncate: int = 80) -> str` (function) — Format a step label with optional matched text for user display.
- `_normalise_url(url: str) -> str` (function) — Normalise URLs for matching across redirects and trailing slashes.
- `_step_type_key(step: dict[str, Any]) -> str` (function) — (no docstring)
