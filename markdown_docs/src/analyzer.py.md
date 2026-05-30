# `src/analyzer.py`

## High-Level Purpose

Keyword-based test case analyzer that requires no LLM. Extracted from `cli/story_analyzer.py` so the CLI layer delegates to `src/` modules instead of maintaining duplicate logic. Analyzes test case text to identify actions, expectations, suggest test data, and estimate complexity using keyword matching.

## Module Metadata

- **Lines:** 284
- **Imports:** `dataclasses`, `datetime`, `typing.Any`

## Data Classes

### `AnalyzedTestCase`
Enhanced test case with keyword-analysis results. Fields: `title`, `description`, `preconditions`, `test_data`, `expected_outcome`, `test_type`, `priority`, `identified_actions`, `identified_expectations`, `suggested_data`, `dependencies`, `estimated_complexity`, `analysis_confidence`.
- `to_dict() -> dict` — serializes with timestamp

### `AnalysisResult`
Container for analysis results. Fields: `analyzed_test_cases`, `analysis_summary`, `detected_patterns`.
- `to_dict() -> dict` — serializes all cases with timestamp

## Class: `KeywordAnalyzer`

```python
class KeywordAnalyzer:
    """Analyze text for key test elements using keywords."""
```

### Class Constants

| Constant | Type | Description |
|----------|------|-------------|
| `ACTION_KEYWORDS` | `dict[str, list[str]]` | Maps action categories (navigation, data_interaction, confirmation, search, filter, form) to keyword lists |
| `EXPECTATION_KEYWORDS` | `dict[str, list[str]]` | Maps expectation categories (success, error, redirect, state_change, visibility, content) to keyword lists |
| `DATA_PATTERNS` | `dict[str, str]` | Regex patterns for extracting email, username, password, name, url, id, amount |
| `DATA_CATEGORIES` | `dict[str, list[str]]` | Maps data categories (auth, form, navigation, data, error) to keyword lists |
| `LOW/MEDIUM/HIGH_COMPLEXITY_KEYWORDS` | `list[str]` | Keywords for complexity estimation |

### Module-Level Constants

| Constant | Type | Description |
|----------|------|-------------|
| `COMMON_PRECONDITIONS` | `list[str]` | Keywords indicating auth prerequisites (login, register, etc.) |
| `COMMON_POSTCONDITIONS` | `list[str]` | Keywords indicating post-actions (logout, reset, etc.) |

### Class Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `identify_actions` | `(text: str) -> list[str]` | Identifies action types from text by matching against `ACTION_KEYWORDS` |
| `identify_expectations` | `(text: str) -> list[str]` | Identifies expected outcomes from text by matching against `EXPECTATION_KEYWORDS` |
| `suggest_data` | `(text: str) -> dict[str, Any]` | Suggests test data (email, password, form data, amounts) based on content keywords |
| `estimate_complexity` | `(text: str) -> str` | Estimates complexity as "low"/"medium"/"high" based on keyword counts |
| `analyze_parsed` | `(parsed: object) -> AnalysisResult` | Analyzes a `ParsedInput` object, handling test_cases or story attributes |
| `analyze` | `(title: str, description: str) -> AnalyzedTestCase` | Analyzes a single test case: identifies actions, expectations, data, complexity |

## Dependencies
- `cli.input_parser.InputParser` output (`ParsedInput`)
- No external library dependencies — pure keyword matching