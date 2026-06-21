# `src/analyzer.py`

## High-Level Purpose

`src/analyzer.py` provides a fast, deterministic, keyword-based analyzer for enriching parsed user stories or test cases without calling an LLM. It identifies likely user actions, expected outcomes, suggested test data, and coarse complexity from plain text. The module is designed as reusable `src/` logic that can be called by CLI/UI layers instead of duplicating analyzer behavior there.

The analyzer produces serializable dataclass results:

- `AnalyzedTestCase`: one enriched test case.
- `AnalysisResult`: a container for one or more analyzed test cases plus summary metadata.
- `KeywordAnalyzer`: a stateless class-method utility that performs keyword matching and result construction.

## Imports

- `from __future__ import annotations`: postpones annotation evaluation.
- `dataclass`, `field` from `dataclasses`: defines result containers with default factories.
- `datetime` from `datetime`: creates generated timestamps and dynamic test email suffixes.
- `Any` from `typing`: allows flexible test-data payloads.

## Module Constants

### `COMMON_PRECONDITIONS: list[str]`

Common text fragments that imply setup or authentication prerequisites:

- login/authentication phrases
- account creation and registration phrases
- navigation to login

This constant is declared but not currently consumed inside the module.

### `COMMON_POSTCONDITIONS: list[str]`

Common text fragments that imply cleanup or end-state actions:

- logout
- clear/reset form
- return home navigation

This constant is declared but not currently consumed inside the module.

## Dataclass: `AnalyzedTestCase`

Enhanced test-case model containing the original test-case text plus keyword-analysis output.

### Signature

```python
@dataclass
class AnalyzedTestCase:
```

### Fields

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `title` | `str` | required | Test case title. |
| `description` | `str` | required | Test case description or scenario text. |
| `preconditions` | `list[str]` | `field(default_factory=list)` | Setup conditions attached to the case. |
| `test_data` | `dict[str, Any]` | `field(default_factory=dict)` | Existing or supplied test-data values. |
| `expected_outcome` | `str` | `""` | Expected result text. |
| `test_type` | `str` | `"functional"` | Classification of the test. |
| `priority` | `str` | `"medium"` | Priority label. |
| `identified_actions` | `list[str]` | `field(default_factory=list)` | Action categories detected from the description. |
| `identified_expectations` | `list[str]` | `field(default_factory=list)` | Expectation categories detected from the description. |
| `suggested_data` | `dict[str, Any]` | `field(default_factory=dict)` | Analyzer-generated data hints. |
| `dependencies` | `list[str]` | `field(default_factory=list)` | Related or prerequisite cases. |
| `estimated_complexity` | `str` | `"low"` | Coarse complexity estimate: typically `low`, `medium`, or `high`. |
| `analysis_confidence` | `float` | `1.0` | Confidence score, reduced when signals are missing. |

### Method: `to_dict`

```python
def to_dict(self) -> dict:
```

Returns a serialization-friendly `dict` containing most dataclass fields plus a generated `created_at` ISO timestamp.

Notable behavior:

- Includes `title`, `description`, preconditions, test data, outcome, type, priority, detected actions/expectations, suggested data, complexity, and confidence.
- Adds `created_at` via `datetime.now().isoformat()`.
- Does not include the `dependencies` field in the serialized output.
- Uses unparameterized `dict` as the return annotation.

## Dataclass: `AnalysisResult`

Container for analysis output across one or more test cases.

### Signature

```python
@dataclass
class AnalysisResult:
```

### Fields

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `analyzed_test_cases` | `list[AnalyzedTestCase]` | required | Enriched test cases. |
| `analysis_summary` | `dict` | `field(default_factory=dict)` | Aggregate summary metadata. |
| `detected_patterns` | `list[str]` | `field(default_factory=list)` | Flattened list of detected action categories. |

### Method: `to_dict`

```python
def to_dict(self) -> dict:
```

Returns a serialization-friendly `dict` with:

- `analyzed_test_cases`: each case converted through `AnalyzedTestCase.to_dict()`.
- `analysis_summary`: summary metadata as stored on the instance.
- `detected_patterns`: detected pattern list.
- `analysis_timestamp`: generated with `datetime.now().isoformat()`.

Uses unparameterized `dict` as the return annotation.

## Class: `KeywordAnalyzer`

Stateless keyword-analysis service implemented with class-level dictionaries and class methods. It does not require construction and keeps all matching configuration on the class.

### Class Attributes

#### `ACTION_KEYWORDS: dict[str, list[str]]`

Maps action categories to substrings used for matching:

- `navigation`
- `data_interaction`
- `confirmation`
- `search`
- `filter`
- `form`

#### `EXPECTATION_KEYWORDS: dict[str, list[str]]`

Maps expected-result categories to substrings used for matching:

- `success`
- `error`
- `redirect`
- `state_change`
- `visibility`
- `content`

The `redirect` keyword list contains a duplicated `"go to"` entry.

#### `DATA_PATTERNS: dict[str, str]`

Regular-expression patterns for structured data such as:

- email
- username
- password
- name
- URL
- ID/key
- amount

This mapping is declared but not currently used by `suggest_data` or other module logic. The amount pattern contains mojibake-looking currency characters in the source string.

#### `DATA_CATEGORIES: dict[str, list[str]]`

Maps broad data domains to detection keywords:

- `auth`
- `form`
- `navigation`
- `data`
- `error`

The `data` category includes a duplicated `"item"` keyword.

#### Complexity Keyword Lists

```python
LOW_COMPLEXITY_KEYWORDS: list[str]
MEDIUM_COMPLEXITY_KEYWORDS: list[str]
HIGH_COMPLEXITY_KEYWORDS: list[str]
```

These lists drive coarse complexity scoring by counting keyword occurrences in the lowercased input text.

## Function and Method Signatures

### `KeywordAnalyzer.identify_actions`

```python
@classmethod
def identify_actions(cls, text: str) -> list[str]:
```

Parameters:

- `text: str`: scenario or test-case text to inspect.

Returns:

- `list[str]`: action category names detected in `ACTION_KEYWORDS`.

Behavior:

- Lowercases input for case-insensitive substring checks.
- Appends each action category where any configured keyword is present.
- If no configured category matches but generic interaction words such as `click`, `enter`, `select`, or `choose` are present, returns `["general"]`.
- Returns an empty list when no action-like text is found.

### `KeywordAnalyzer.identify_expectations`

```python
@classmethod
def identify_expectations(cls, text: str) -> list[str]:
```

Parameters:

- `text: str`: scenario or test-case text to inspect.

Returns:

- `list[str]`: expectation category names detected in `EXPECTATION_KEYWORDS`.

Behavior:

- Lowercases input for case-insensitive substring checks.
- Appends each expectation category where any configured keyword is present.
- Falls back to `["result_display"]` when no expectation category is detected.

### `KeywordAnalyzer.suggest_data`

```python
@classmethod
def suggest_data(cls, text: str) -> dict[str, Any]:
```

Parameters:

- `text: str`: scenario or test-case text to inspect.

Returns:

- `dict[str, Any]`: suggested data values inferred from keywords, or `{}` when no data hints are found.

Behavior:

- Lowercases the input.
- Detects broad categories using `DATA_CATEGORIES`.
- If auth-related terms such as `email`, `register`, or `login` appear, generates:
  - `email`: timestamped test email using `datetime.now().strftime('%Y%m%d_%H%M%S')`
  - `password`: fixed strong-looking test password
- If form-related category or `submit` is detected, adds `form_data` with a name and email.
- If payment/amount terms appear, adds `amount` and `currency`.
- Returns an empty dictionary if no suggestions were generated.

### `KeywordAnalyzer.estimate_complexity`

```python
@classmethod
def estimate_complexity(cls, text: str) -> str:
```

Parameters:

- `text: str`: scenario or test-case text to inspect.

Returns:

- `str`: one of the coarse complexity labels currently returned by the method: `"low"`, `"medium"`, or `"high"`.

Behavior:

- Counts occurrences by checking whether each low/medium/high keyword appears as a substring of the lowercased input.
- Returns `"low"` when no complexity keywords are found.
- Returns `"high"` when high-complexity matches outnumber medium-complexity matches.
- Returns `"medium"` when any high-complexity keyword is present or at least three medium-complexity keywords are present.
- Returns `"low"` otherwise.

### `KeywordAnalyzer.analyze_parsed`

```python
@classmethod
def analyze_parsed(cls, parsed: object) -> AnalysisResult:
```

Parameters:

- `parsed: object`: flexible parsed input object. The docstring expects a `ParsedInput` from `src.cli.input_parser.InputParser`, but the method intentionally uses duck typing.

Returns:

- `AnalysisResult`: container with analyzed cases, summary metadata, and detected action patterns.

Behavior:

- Initializes `analyzed_cases: list[AnalyzedTestCase]` and `detected_patterns: list[str]`.
- If `parsed` has a truthy `test_cases` attribute:
  - Iterates each test case.
  - Derives `title` from `tc.title`, then `tc.name`, then `"Untitled"`.
  - Derives `desc` from `tc.description`, then `tc.step`, then `""`.
  - Calls `cls.analyze(title, desc)`.
  - Extends `detected_patterns` with each analyzed case's `identified_actions`.
- Else if `parsed` has a `story` attribute:
  - Uses `"User Story"` as the title.
  - Analyzes `str(parsed.story)`.
- Else:
  - Uses `"Input"` as the title.
  - Analyzes `str(parsed)`.
- Returns an `AnalysisResult` with:
  - `analysis_summary["total_cases"]`
  - empty `complexity_distribution`
  - `requires_auth` set to `False`
  - flattened detected action patterns

Architectural notes:

- Uses `hasattr` and `# type: ignore[attr-defined]` to support multiple parsed object shapes without importing their concrete types.
- The summary fields are placeholders rather than fully aggregated metrics.

### `KeywordAnalyzer.analyze`

```python
@classmethod
def analyze(cls, title: str, description: str) -> AnalyzedTestCase:
```

Parameters:

- `title: str`: title for the resulting analyzed test case.
- `description: str`: text to analyze.

Returns:

- `AnalyzedTestCase`: enriched result with detected actions, expectations, data suggestions, complexity, and confidence.

Behavior:

- Calls:
  - `cls.identify_actions(description)`
  - `cls.identify_expectations(description)`
  - `cls.suggest_data(description)`
  - `cls.estimate_complexity(description)`
- Starts with `base_confidence = 1.0`.
- Reduces confidence by:
  - `0.2` if no actions were found.
  - `0.2` if no expectations were found.
  - `0.1` if no suggested data was found.
- Clamps confidence to a minimum of `0.5`.
- Returns an `AnalyzedTestCase` populated with the original title/description and analysis results.

Because `identify_expectations` falls back to `["result_display"]`, the `if not expectations` confidence penalty is normally unreachable through `analyze`.

## Key Architectural Patterns

### Deterministic Keyword Pipeline

The module uses static keyword maps and substring checks instead of LLM calls. This makes the analyzer fast, predictable, and suitable for CLI preprocessing or lightweight enrichment.

### Dataclass Result Models

`AnalyzedTestCase` and `AnalysisResult` separate analysis data from analyzer logic. Both include `to_dict` helpers for JSON-compatible serialization and timestamp metadata.

### Stateless Class-Method Analyzer

`KeywordAnalyzer` stores configuration in class attributes and exposes only class methods. There is no instance state, dependency injection, I/O, or external service access.

### Duck-Typed Adapter Boundary

`analyze_parsed` accepts `object` and adapts several possible parsed-input shapes using `hasattr`. This avoids importing parser models while allowing the analyzer to work with test cases, user stories, or arbitrary objects.

### Fallback-Oriented Enrichment

The analyzer favors returning usable defaults:

- Missing expectations become `["result_display"]`.
- Missing complexity signals become `"low"`.
- Missing titles/descriptions in parsed test cases fall back to `"Untitled"` and `""`.
- Confidence bottoms out at `0.5`.

## Data Flow

```text
parsed object or title/description
        |
        v
KeywordAnalyzer.analyze_parsed(...) or KeywordAnalyzer.analyze(...)
        |
        v
identify_actions + identify_expectations + suggest_data + estimate_complexity
        |
        v
AnalyzedTestCase
        |
        v
AnalysisResult, when analyzing parsed multi-case input
```

## Serialization Shape

### `AnalyzedTestCase.to_dict()`

Produces keys:

- `title`
- `description`
- `preconditions`
- `test_data`
- `expected_outcome`
- `test_type`
- `priority`
- `identified_actions`
- `identified_expectations`
- `suggested_data`
- `estimated_complexity`
- `analysis_confidence`
- `created_at`

### `AnalysisResult.to_dict()`

Produces keys:

- `analyzed_test_cases`
- `analysis_summary`
- `detected_patterns`
- `analysis_timestamp`

## Notable Implementation Details

- Matching uses simple substring checks, so keywords can match inside longer words.
- `DATA_PATTERNS` is currently unused despite containing regex definitions.
- `COMMON_PRECONDITIONS` and `COMMON_POSTCONDITIONS` are currently unused.
- Timestamps are generated at serialization time and suggested email generation time, so repeated calls can produce different output.
- `analysis_summary` includes `complexity_distribution` and `requires_auth`, but those values are not computed from analyzed cases in the current implementation.
- Return annotations for `to_dict` methods are plain `dict`, while other dictionaries use more specific generic annotations.
