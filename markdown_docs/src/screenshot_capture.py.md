# screenshot_capture.py

## Purpose
Screenshot capture utilities extracted from evidence_tracker. Provides Playwright page screenshot functions with consistent naming conventions and file path management for test evidence.

## Location
`src/screenshot_capture.py`

## Dependencies
- `playwright.sync_api.Page` (external)
- `pathlib.Path` (standard library)
- `logging` (standard library)

## Public API

### `capture_screenshot(page: Page, test_name: str, suffix: str, output_dir: str = "screenshots") -> Path | None`
Take a full-page screenshot and save it to the output directory. Returns the `Path` to the saved file, or `None` on failure. Creates the output directory if it does not exist.

### `normalize_screenshot_path(path: str | Path) -> str`
Normalize a screenshot path for embedding in reports (converts to relative path where possible).

### `embed_screenshot_as_base64(path: str | Path) -> str | None`
Read a screenshot file and return it as a base64-encoded data URI suitable for embedding in HTML reports. Returns `None` if the file does not exist or cannot be read.

## Design Notes
- Extracted from `evidence_tracker.py` to separate screenshot I/O from evidence tracking logic
- Uses Playwright's `page.screenshot(full_page=True)` for consistent captures
- Files named as `{test_name}_{suffix}.png` for predictable lookups
- Base64 embedding enables self-contained HTML reports

## Related Files
- `src/evidence_tracker.py` — parent module from which this was extracted
- `src/report_formatters.py` — consumes base64 screenshots for HTML reports
- `src/failure_reporter.py` — captures screenshots on test failures