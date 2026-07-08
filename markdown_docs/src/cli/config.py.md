# `src/cli/config.py` — CLI Config Re-exports

## Purpose

Backwards-compatible re-export layer. All enums and defaults are defined in `src/config.py`; this module re-exports them so existing CLI code continues to work without updating import paths.

## Re-exports from `src/config`

| Symbol | Type | Description |
|--------|------|-------------|
| `AnalysisMode` | Enum | Test analysis modes |
| `CaptureLevel` | Enum | Screenshot capture levels (`BASIC`, `STANDARD`, `THOROUGH`) |
| `DetectionMode` | Enum | Element detection strategies |
| `JIRA_PROJECT_KEY` | `str` | Default Jira project key |
| `ReportFormat` | Enum | Output report formats |
| `ScreenshotNaming` | Enum | Filename conventions for screenshots |

## Design Patterns

- **Alias module**: Zero logic — pure re-exports to maintain import compatibility during refactoring.
