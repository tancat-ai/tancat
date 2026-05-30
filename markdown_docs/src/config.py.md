# `src/config.py`

## High-Level Purpose
Centralized configuration for AI Playwright Test Generator. Defines enums for type-safe options and project-wide constants.

## Module Metadata
- **Lines:** 67
- **Imports:** `os`, `enum.Enum`

## Classes

### `AnalysisMode` (Enum)
Values: `FAST`, `THOROUGH`, `AUTO`

### `ReportFormat` (Enum)
Values: `CONFLUENCE`, `JIRA_XML`, `JSON`, `MARKDOWN`, `LOCAL`, `JIRA`, `SHAREABLE`

### `DetectionMode` (Enum)
Values: `AUTO`, `EXPLICIT`, `FAST`, `THOROUGH`

### `CaptureLevel` (Enum)
Values: `BASIC`, `STANDARD`, `THOROUGH`

### `ScreenshotNaming` (Enum)
Values: `SEQUENTIAL`, `DESCRIPTIVE`, `HYBRID`

## Constants
| Constant | Default | Note |
|----------|---------|------|
| `JIRA_PROJECT_KEY` | `"TEST"` | Env override via `JIRA_PROJECT_KEY` |
| `STORAGE_MODE` | `"filesystem"` | |
| `NAMING_CONVENTION` | Hybrid | |
| `CAPTURE_LEVEL` | Standard | |
| `SCREENSHOT_DIR` | `"screenshots"` | |
| `LLM_ANALYSIS_MODE` | Thorough | |
| `GENERATED_TESTS_DIR` | `"generated_tests"` | |

## Key Design Decisions
- Enums for type-safe configuration options
- Single source of truth for all project constants
- Environment variable support for sensitive/configurable values

## Dependencies
- None — stdlib only