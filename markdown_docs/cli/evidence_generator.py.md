# cli/evidence_generator.py

## Purpose

Handles screenshot capture and evidence generation for CLI-driven test execution.
Provides metadata, reporting, and packaging of screenshots and bug evidence.

## Key classes

### `ScreenshotMetadata`
- Fields: `test_case_id`, `timestamp`, `file_path`, `capture_stage`, `description`, `file_size`, `dimensions`
- Method: `to_dict() -> dict`

### `EvidenceCollection`
- Fields: `screenshots`, `videos`, `console_logs`, `network_requests`
- Method: `to_dict() -> dict`

### `ScreenshotCapturer`
- Purpose: capture screenshots and save them to disk.
- Constructor: `__init__(self) -> None`
- Public method: `capture(page: Any, test_case: AnalyzedTestCase, capture_stage: str, step_description: str = "") -> str | None`
- Internal methods:
  - `_generate_filename(test_case, capture_stage, step_description) -> str`
  - `_save_screenshot(screenshot_bytes, filename, test_title) -> str`
  - `_get_screenshot_dimensions(screenshot_bytes) -> tuple`
  - `_generate_case_id(title) -> str`

### `EvidenceGenerator`
- Purpose: collect evidence during test execution, summarize it, create reports, and archive artifacts.
- Constructor: `__init__(self, capture_level: CaptureLevel | None = None) -> None`
- Public methods:
  - `capture_test_evidence(page, test_case, capture_stage='step', step_description='') -> str | None`
  - `generate_evidence_summary() -> dict`
  - `generate_evidence() -> None`
  - `create_visual_report(output_path: str, test_cases: list[AnalyzedTestCase]) -> str`
  - `create_evidence_zip(output_path: str) -> str`
- Internal methods:
  - `_should_capture(capture_stage: str) -> bool`
  - `_generate_html_report(test_cases) -> str`

### `BugEvidenceGenerator`
- Purpose: capture bug reproduction evidence separately from normal test evidence.
- Methods:
  - `capture_bug_evidence(page, description: str) -> dict`
  - `generate_bug_report(output_path: str) -> str`

## Notes

- Uses optional Pillow support (`PIL_AVAILABLE`) to obtain screenshot dimensions.
- Reads capture settings from `src.config` and CLI `CaptureLevel`.
- Generates HTML, ZIP archives, and plain-text bug reports.
