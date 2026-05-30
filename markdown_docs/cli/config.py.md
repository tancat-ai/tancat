# cli/config.py

## Purpose

Compatibility shim that re-exports CLI-related enums and constants from `src.config`.

## Exports

- `AnalysisMode`
- `CaptureLevel`
- `DetectionMode`
- `ReportFormat`
- `ScreenshotNaming`
- `JIRA_PROJECT_KEY`

## Implementation details

- Imports the values directly from `src.config`.
- Defines `__all__` to preserve the public CLI API surface for legacy imports.
