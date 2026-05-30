# cli/input_parser.py

## Purpose

Parses multiple input formats into normalized test cases for the CLI pipeline.
Supports Jira-style text, Gherkin, bullet lists, plain text, and JSON input.

## Key dataclasses

### `TestCase`
- Fields: `title`, `description`, `preconditions`, `test_data`, `expected_outcome`, `test_type`, `priority`
- Method: `to_dict() -> dict`
- Method: `to_prompt() -> str`

### `ParsedInput`
- Fields: `test_cases`, `source_format`, `raw_input`, `metadata`
- Methods: `to_dict() -> dict`, `save_to_json(output_path: str) -> str`

## Format detection

### `FormatDetector`
- Public:
  - `detect(text: str, method: DetectionMode = DetectionMode.AUTO) -> tuple[str, float]`
- Uses regex patterns for:
  - `jira`
  - `gherkin`
  - `bullets`
  - `plain_text`

## Parsers

### `PlainTextParser`
- Extracts user story style sentences and falls back to a single scenario when no structured patterns are found.
- Methods:
  - `parse(text: str) -> list[TestCase]`
  - `_extract_test_case(text: str) -> TestCase`

### `JiraParser`
- Parses Jira-style issue metadata, description, and acceptance criteria.
- Methods:
  - `parse(text: str) -> list[TestCase]`
  - `_extract_from_acceptance_criteria(ac_text: str, metadata: dict) -> list[TestCase]`
  - `_determine_test_type(line: str) -> str`
  - `_generate_title(line: str, metadata: dict) -> str`
  - `_determine_priority(line: str) -> str`

### `GherkinParser`
- Parses Feature/Scenario/Given-When-Then text into test cases.
- Methods:
  - `parse(text: str) -> list[TestCase]`
  - `_extract_scenarios(text: str) -> list[dict]`
  - `_extract_steps(steps_text: str) -> list[dict]`
  - `_scenario_to_test_case(scenario: dict) -> TestCase`

### `BulletParser`
- Parses bullet lists and numbered criteria into test cases.
- Methods:
  - `parse(text: str) -> list[TestCase]`
  - `_generate_title(line: str) -> str`
  - `_determine_test_type(line: str) -> str`

## Main parser

### `InputParser`
- Constructor: `__init__(self, detection_method: DetectionMode | None = None) -> None`
- Methods:
  - `parse(text: str, explicit_format: str | None = None) -> ParsedInput`
  - `parse_json(json_str: str) -> ParsedInput`
  - `parse_and_save(text: str, output_dir: str | None = None) -> str`
- Convenience functions:
  - `parse_jira_format(text: str) -> list[TestCase]`
  - `parse_gherkin_format(text: str) -> list[TestCase]`
  - `parse_bullet_format(text: str) -> list[TestCase]`
  - `parse_plain_text(text: str) -> list[TestCase]`

## Notes

- `parse_json` supports both array and object payloads.
- The parser adds detection metadata including confidence and timestamp.
