# cli/__init__.py

## Purpose

Provides backwards-compatible re-exports for the CLI package.
This module exists so that `import cli` consumers can access common CLI constants and enums without importing from `src.config` directly.

## Exports

- `AnalysisMode`
- `CaptureLevel`
- `DetectionMode`
- `ReportFormat`
- `ScreenshotNaming`
- `JIRA_PROJECT_KEY`

## Implementation details

- Imports selected constants and enum types from `src.config`.
- Defines `__all__` so re-exports are explicit and importable by `from cli import *`.
