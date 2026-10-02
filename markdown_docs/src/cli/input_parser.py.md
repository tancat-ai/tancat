# `src/cli/input_parser.py` — Multi-Format Input Parser

## Purpose

Intelligent parsing of various input formats into standardised `TestCase` objects. Designed with hybrid detection (regex-first, LLM fallback) for speed and accuracy.

## Data Classes

### `TestCase`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | `str` | — | Test case title |
| `description` | `str` | — | Full description |
| `preconditions` | `list[str]` | `[]` | Prerequisites |
| `test_data` | `dict` | `{}` | Test data inputs |
| `expected_outcome` | `str` | `""` | Expected result |
| `test_type` | `str` | `"functional"` | `happy_path`, `validation`, `error_handling`, `edge_case` |
| `priority` | `str` | `"medium"` | `high`, `medium`, `low` |

- `to_dict() -> dict` — Serialises with `created_at` timestamp.
- `to_prompt() -> str` — Converts to LLM-friendly prompt string.

### `ParsedInput`

| Field | Type | Description |
|-------|------|-------------|
| `test_cases` | `list[TestCase]` | Extracted test cases |
| `source_format` | `str` | Detected format name |
| `raw_input` | `str` | Original text |
| `metadata` | `dict` | Confidence, detection method, timestamp |

- `to_dict() -> dict` — Serialises with raw input sample (truncated to 200 chars).
- `save_to_json(output_path) -> str` — Writes to JSON file.

## Classes

### `FormatDetector`

Auto-detects input format using regex patterns.

**Supported formats:**
- **Jira**: `Issue`, `Summary`, `Acceptance Criteria`, `Description` headers
- **Gherkin**: `Feature:`, `Scenario:`, `Given/When/Then`
- **Bullets**: Lines starting with `-`, `*`, or `1.`

#### `detect(text, method=DetectionMode.AUTO) -> tuple[str, float]`

Returns `(format_name, confidence_score)`. Confidence thresholds:
- Jira: 0.9 (3+ pattern matches)
- Gherkin: 0.9 (2+ pattern matches)
- Bullets: 0.8 (3+ bullet lines)
- Plain text: 0.5 (default)

### `PlainTextParser`

Parses plain text user stories.

#### `parse(text) -> list[TestCase]`

Looks for patterns like "As a...", "I want to...", "Users can...". Falls back to treating entire text as a single "Main Flow" scenario.

### `JiraParser`

Parses Jira-style copy-paste format.

#### `parse(text) -> list[TestCase]`

Extracts metadata (issue key, summary), then generates `TestCase` objects from acceptance criteria lines. Uses keyword-based heuristics to determine `test_type`:
- **error_handling**: "error", "invalid", "fail"
- **happy_path**: "valid", "successful", "logged", "redirect"
- **validation**: "empty", "missing", "null"
- **functional**: default

Priority from keywords: "required"/"must" → high, "should" → medium, else → low.

### `GherkinParser`

Parses Gherkin/BDD format.

#### `parse(text) -> list[TestCase]`

Extracts `Scenario:` blocks, splits steps into `Given`/`When`/`Then` groups. Maps `Given` → preconditions, `Then` → expected outcome.

### `BulletParser`

Parses bullet-point style acceptance criteria.

#### `parse(text) -> list[TestCase]`

Extracts lines starting with `-`, `*`, or `1.`. Uses same keyword heuristics as `JiraParser` for test type classification.

### `InputParser`

Main orchestrator — multi-format parser with auto-detection.

#### `__init__(detection_method=DetectionMode.AUTO)`

#### `parse(text, explicit_format=None) -> ParsedInput`

Routes to appropriate parser based on auto-detection or explicit override.

#### `parse_json(json_str) -> ParsedInput`

Parses JSON strings — handles both list and dict formats (including wrapper `{"test_cases": [...]}`).

#### `parse_and_save(text, output_dir=None) -> str`

Parses and saves to timestamped JSON file in `EVIDENCE_DIR` or custom directory.

## Module-Level Functions

| Function | Description |
|----------|-------------|
| `parse_jira_format(text)` | Convenience wrapper for Jira parsing |
| `parse_gherkin_format(text)` | Convenience wrapper for Gherkin parsing |
| `parse_bullet_format(text)` | Convenience wrapper for bullet parsing |
| `parse_plain_text(text)` | Convenience wrapper for plain text parsing |

## Design Patterns

- **Strategy pattern**: `InputParser._parse_by_format` routes to format-specific parser implementations.
- **Keyword-based classification**: Test type and priority derived from acceptance criterion content.

## How It Works (Internals)

Private `_`-helpers - the module's real logic (11 items). Grouped under the public function that calls them.

### `FormatDetector.detect(text: str, method: DetectionMode = DetectionMode.AUTO) -> tuple[str, float]` - method of `FormatDetector`

- `_fast_detect(text: str) -> tuple[str, float]` (method of `FormatDetector`): Quick regex-based detection.

### `PlainTextParser.parse(text: str) -> list[TestCase]` - method of `PlainTextParser`

- `_extract_test_case(text: str) -> TestCase` (method of `PlainTextParser`): Extract a test case from a user story statement.

### `JiraParser.parse(text: str) -> list[TestCase]` - method of `JiraParser`

- `_extract_from_acceptance_criteria(ac_text: str, metadata: dict) -> list[TestCase]` (method of `JiraParser`): Parse acceptance criteria items.

### `BulletParser.parse(text: str) -> list[TestCase]` - method of `BulletParser`

- `_determine_test_type(line: str) -> str` (method of `JiraParser`): Determine test case type from acceptance criterion.
- `_generate_title(line: str, metadata: dict) -> str` (method of `JiraParser`): Generate a concise title from the acceptance criterion.
- `_determine_test_type(line: str) -> str` (method of `BulletParser`): Determine test type from bullet point.

### `GherkinParser.parse(text: str) -> list[TestCase]` - method of `GherkinParser`

- `_extract_scenarios(text: str) -> list[dict]` (method of `GherkinParser`): Extract all scenarios from Gherkin text.
- `_scenario_to_test_case(scenario: dict) -> TestCase` (method of `GherkinParser`): Convert a scenario to a TestCase.

### `InputParser.parse(text: str, explicit_format: str | None = None) -> ParsedInput` - method of `InputParser`

- `_parse_by_format(text: str, format_name: str) -> list[TestCase]` (method of `InputParser`): Route to appropriate parser based on format.

### Internal utilities

- `_determine_priority(line: str) -> str` (method of `JiraParser`): Determine test priority from acceptance criterion.
- `_extract_steps(steps_text: str) -> list[dict]` (method of `GherkinParser`): Extract and categorize Gherkin steps.
