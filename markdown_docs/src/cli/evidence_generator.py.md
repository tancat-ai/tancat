# `src/cli/evidence_generator.py` — Evidence Generator

## Purpose

Handles screenshot capture and evidence generation for test execution verification, bug reproduction evidence, visual regression testing, and test documentation.

## Data Classes

### `ScreenshotMetadata`

| Field | Type | Description |
|-------|------|-------------|
| `test_case_id` | `str` | Unique test case identifier |
| `timestamp` | `str` | ISO-8601 capture time |
| `file_path` | `str` | On-disk path |
| `capture_stage` | `str` | Stage label (`entry`, `step`, `outcome`, `bug`) |
| `description` | `str` | Human-readable description |
| `file_size` | `int` | Bytes |
| `dimensions` | `tuple[int, int]` | Width × height (from PIL, `(0,0)` if unavailable) |

- `to_dict() -> dict` — Serialises metadata to a plain dict.

### `EvidenceCollection`

| Field | Type | Description |
|-------|------|-------------|
| `screenshots` | `list[ScreenshotMetadata]` | Collected screenshots |
| `videos` | `list[dict]` | Video evidence (reserved) |
| `console_logs` | `list[dict]` | Console log entries |
| `network_requests` | `list[dict]` | Network request captures |

- `to_dict() -> dict` — Full serialisation including collection timestamp.

## Classes

### `ScreenshotCapturer`

Handles screenshot capture and disk storage.

**Configuration:** Reads `STORAGE_MODE`, `NAMING_CONVENTION`, `CAPTURE_LEVEL`, `SCREENSHOT_DIR` from `src.config`.

**Methods:**

#### `capture(page: Any, test_case: AnalyzedTestCase, capture_stage: str, step_description: str = "") -> str | None`

Captures full-page screenshot from a Playwright page. Saves to disk and records metadata. Returns file path or `None` on failure.

#### `_generate_filename(test_case, capture_stage, step_description) -> str`

Generates filename based on `ScreenshotNaming` convention:
- `SEQUENTIAL`: `{stage}_{NNN}.png`
- `DESCRIPTIVE`: `{title}_{date}.png`
- `HYBRID` (default): `{title_short}_{NNN}_{date}.png`

#### `_save_screenshot(screenshot_bytes, filename, test_title) -> str`

Saves to disk with three storage modes:
- `organized`: `{screenshots_dir}/{test_type}/{date}/{filename}`
- `flatten`: `{screenshots_dir}/{filename}`
- `by_title` (default): `{screenshots_dir}/{title_safe}/{filename}`

#### `_get_screenshot_dimensions(screenshot_bytes) -> tuple`

Uses PIL to extract dimensions. Returns `(0, 0)` if PIL unavailable.

#### `_generate_case_id(title) -> str`

Generates `test_{safe_title}_{timestamp}` identifier.

### `EvidenceGenerator`

Orchestrates comprehensive evidence collection.

**Methods:**

#### `capture_test_evidence(page, test_case, capture_stage="step", step_description="") -> str | None`

Conditional capture based on `CaptureLevel`:
- `BASIC`: `entry`, `outcome` only
- `STANDARD`: `entry`, `step`, `outcome`
- `THOROUGH`: all stages

#### `generate_evidence_summary() -> dict`

Returns serialised evidence summary.

#### `create_visual_report(output_path, test_cases) -> str`

Generates an HTML report with test case details and metadata.

#### `create_evidence_zip(output_path) -> str`

Creates a ZIP archive of all screenshots plus `evidence_summary.json`.

### `BugEvidenceGenerator`

Specialised evidence capture for bug reporting.

**Methods:**

#### `capture_bug_evidence(page, description) -> dict`

Captures screenshot, URL, and timestamp for a bug reproduction.

#### `generate_bug_report(output_path) -> str`

Writes a plain-text bug report with all captured evidence.

## Module-Level Functions

### `capture_screenshot(page, test_case, capture_stage="step") -> str | None`

Convenience wrapper — creates an `EvidenceGenerator` and captures a single screenshot.

### `generate_test_evidence(test_cases, output_path) -> str`

Convenience wrapper — creates a visual HTML report.

## Dependencies

- `src.analyzer.AnalyzedTestCase`
- `src.cli.config.CaptureLevel`
- `src.config` (constants)
- `PIL` (optional, for dimension extraction)

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `ScreenshotCapturer.__init__` (method of `ScreenshotCapturer`): `ScreenshotCapturer.__init__() -> None`
- `EvidenceGenerator.__init__` (method of `EvidenceGenerator`): `EvidenceGenerator.__init__(capture_level: CaptureLevel | None = None) -> None`
- `EvidenceGenerator.generate_evidence` (method of `EvidenceGenerator`): `EvidenceGenerator.generate_evidence() -> None` - Generate evidence package.
- `BugEvidenceGenerator.__init__` (method of `BugEvidenceGenerator`): `BugEvidenceGenerator.__init__() -> None`
- `BugEvidenceGenerator.add_test_failure` (method of `BugEvidenceGenerator`): `BugEvidenceGenerator.add_test_failure(test_result: TestResult, page_url: str = 'N/A') -> dict` - Add a test failure as bug evidence (no live page required). Classifies the failure and records category, locator, and repair suggestion alongside the raw error data.
- `BugEvidenceGenerator.process_run_result` (method of `BugEvidenceGenerator`): `BugEvidenceGenerator.process_run_result(run_result: RunResult) -> list[dict]` - Process a RunResult and record all failed tests as bug evidence. Returns the list of evidence dicts created.


## How It Works (Internals)

Private `_`-helpers - the module's real logic (6 items). Grouped under the public function that calls them.

### `ScreenshotCapturer.capture(page: Any, test_case: AnalyzedTestCase, capture_stage: str, step_description: str = '') -> str | None` - method of `ScreenshotCapturer`

- `_generate_filename(test_case: AnalyzedTestCase, capture_stage: str, step_description: str, extension: str | None = None) -> str` (method of `ScreenshotCapturer`): Generate screenshot filename based on naming convention. Args: extension: File extension to use (e.g. ".webp"). Defaults to the configured evidence extension. Pass the format actually written by the adaptive encod...
- `_save_screenshot(screenshot_bytes: bytes, filename: str, test_title: str) -> str` (method of `ScreenshotCapturer`): Save screenshot to disk with proper organization.

### `EvidenceGenerator.capture_test_evidence(page: Any, test_case: AnalyzedTestCase, capture_stage: str = 'step', step_description: str = '') -> str | None` - method of `EvidenceGenerator`

- `_get_screenshot_dimensions(screenshot_bytes: bytes) -> tuple` (method of `ScreenshotCapturer`): Extract dimensions from screenshot bytes.
- `_generate_case_id(title: str) -> str` (method of `ScreenshotCapturer`): Generate unique test case ID.
- `_should_capture(capture_stage: str) -> bool` (method of `EvidenceGenerator`): Determine if capture is needed based on capture level.

### `EvidenceGenerator.create_visual_report(output_path: str, test_cases: list[AnalyzedTestCase]) -> str` - method of `EvidenceGenerator`

- `_generate_html_report(test_cases: list[AnalyzedTestCase]) -> str` (method of `EvidenceGenerator`): Generate HTML report content.
