# `src/config.py`

## High-Level Purpose

`src/config.py` centralizes project-wide configuration values and enum types for the AI Playwright Test Generator. It provides stable, typed names for analysis modes, report formats, input detection behavior, screenshot capture depth, screenshot naming style, output directories, and Jira project defaults.

The module is intentionally lightweight: it has no runtime functions, no classes with custom behavior, and no direct dependencies on other project modules. Its main role is to expose shared constants and `Enum` definitions that other parts of the application can import instead of duplicating string literals.

## Module Dependencies

```python
from __future__ import annotations

import os
from enum import Enum
```

- `os` is used to read the optional `JIRA_PROJECT_KEY` environment variable.
- `Enum` is used as the base class for all mode and format definitions.
- `annotations` future import keeps type annotation behavior modern and consistent.

## Classes

### `class AnalysisMode(Enum)`

```python
class AnalysisMode(Enum):
    FAST = "fast"
    THOROUGH = "thorough"
    AUTO = "auto"
```

Defines how user stories should be analyzed.

Members:

- `FAST: AnalysisMode` - Regex-based analysis without LLM usage.
- `THOROUGH: AnalysisMode` - LLM-powered analysis.
- `AUTO: AnalysisMode` - Fast analysis first, with thorough analysis available for complex inputs.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

### `class ReportFormat(Enum)`

```python
class ReportFormat(Enum):
    CONFLUENCE = "confluence"
    JIRA_XML = "jira_xml"
    JSON = "json"
    MARKDOWN = "markdown"
    LOCAL = "local"
    JIRA = "jira"
    SHAREABLE = "shareable"
```

Defines supported evidence and report output formats.

Members:

- `CONFLUENCE: ReportFormat` - HTML intended for Confluence or Confluence Cloud.
- `JIRA_XML: ReportFormat` - XML intended for Jira import.
- `JSON: ReportFormat` - Structured JSON data format.
- `MARKDOWN: ReportFormat` - Markdown documentation output.
- `LOCAL: ReportFormat` - Relative-path report output for local viewing.
- `JIRA: ReportFormat` - Absolute-path report output for Jira uploads.
- `SHAREABLE: ReportFormat` - Clean team documentation output.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

### `class DetectionMode(Enum)`

```python
class DetectionMode(Enum):
    AUTO = "auto"
    EXPLICIT = "explicit"
    FAST = "fast"
    THOROUGH = "thorough"
```

Defines how the application should detect an input format.

Members:

- `AUTO: DetectionMode` - Regex-first detection with LLM fallback.
- `EXPLICIT: DetectionMode` - User-specified input format.
- `FAST: DetectionMode` - Pure regex detection without LLM usage.
- `THOROUGH: DetectionMode` - LLM-based detection.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

### `class CaptureLevel(Enum)`

```python
class CaptureLevel(Enum):
    BASIC = "basic"
    STANDARD = "standard"
    THOROUGH = "thorough"
```

Defines how much screenshot evidence should be captured during generated test execution or reporting workflows.

Members:

- `BASIC: CaptureLevel` - Entry and outcome screenshots only.
- `STANDARD: CaptureLevel` - Entry, step, and outcome screenshots.
- `THOROUGH: CaptureLevel` - Screenshots for every major action.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

### `class ScreenshotNaming(Enum)`

```python
class ScreenshotNaming(Enum):
    SEQUENTIAL = "sequential"
    DESCRIPTIVE = "descriptive"
    HYBRID = "hybrid"
```

Defines available screenshot filename strategies.

Members:

- `SEQUENTIAL: ScreenshotNaming` - Sequential numeric naming, such as `test_entry_001.png`.
- `DESCRIPTIVE: ScreenshotNaming` - Descriptive timestamp-style naming, such as `login_success_20260303.png`.
- `HYBRID: ScreenshotNaming` - Descriptive plus sequence/timestamp-style naming, such as `login_success_001_20260303.png`.

Constructor parameters and return value:

- Uses the inherited `Enum` construction behavior.
- No custom `__init__`, methods, parameters, or return values are defined.

## Functions

No module-level functions are defined in `src/config.py`.

## Module Constants

### Jira Configuration

```python
JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "TEST")
```

- Type: `str`
- Value source: `JIRA_PROJECT_KEY` environment variable, defaulting to `"TEST"`.
- Purpose: Supplies the default Jira project key while allowing deployment or local environment overrides.

### Screenshot Storage Configuration

```python
STORAGE_MODE: str = "filesystem"
NAMING_CONVENTION: ScreenshotNaming = ScreenshotNaming.HYBRID
CAPTURE_LEVEL: CaptureLevel = CaptureLevel.STANDARD
SCREENSHOT_DIR: str = "screenshots"
```

- `STORAGE_MODE: str` - Selects screenshot storage backend. Current default is `"filesystem"`.
- `NAMING_CONVENTION: ScreenshotNaming` - Selects the default screenshot naming strategy. Current default is `ScreenshotNaming.HYBRID`.
- `CAPTURE_LEVEL: CaptureLevel` - Selects screenshot capture depth. Current default is `CaptureLevel.STANDARD`.
- `SCREENSHOT_DIR: str` - Directory name for screenshot output. Current default is `"screenshots"`.

### LLM Analysis Configuration

```python
LLM_ANALYSIS_MODE: AnalysisMode = AnalysisMode.THOROUGH
```

- Type: `AnalysisMode`
- Current default: `AnalysisMode.THOROUGH`
- Purpose: Preserves backward compatibility with older CLI configuration while exposing the default LLM analysis behavior.

### Output Directory Configuration

```python
GENERATED_TESTS_DIR: str = "generated_tests"
```

- Type: `str`
- Current default: `"generated_tests"`
- Purpose: Defines the output directory used for generated Playwright test files.

## Architectural Patterns

### Centralized Configuration Module

The file gathers shared settings into one importable module. This reduces repeated literals across UI, CLI, generation, screenshot, and reporting code.

### Typed Enum Boundaries

The module uses `Enum` classes to model constrained option sets instead of passing arbitrary strings throughout the codebase. This pattern gives downstream code named values for user story analysis, report rendering, input detection, screenshot capture, and screenshot naming.

### String Values for Interop

Each enum member stores a lowercase string value. This makes enum values suitable for serialization, command-line arguments, UI selections, configuration persistence, and report metadata while still giving Python callers strongly named members.

### Environment Override at Import Time

`JIRA_PROJECT_KEY` is read from the process environment when the module is imported. This supports local or deployment-specific Jira configuration without requiring a separate configuration file.

### Module-Level Defaults

Default configuration values are exposed as typed module-level constants. This keeps startup behavior simple and makes the current defaults discoverable from one place.

## Side Effects

Importing this module reads the `JIRA_PROJECT_KEY` environment variable once through `os.getenv`. No files are read or written, no network calls are made, and no application services are initialized.
