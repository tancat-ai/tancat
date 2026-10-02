# `src/user_story_parser.py`

## Purpose
Parses user story text into structured `FeatureSpecification` with user story and acceptance criteria. Supports multiple input formats (Markdown headings, plain text, "As a" format).

## Metadata
- **Lines:** 288
- **Imports:** re, dataclasses, typing (Any, Literal)

## Classes
| Class | Description |
|-------|-------------|
| `FeatureSpecification` | Parsed result: user_story, acceptance_criteria list, raw_input |
| `ParseResult` | Success flag, specification, error_message |
| `RequirementModel` | Normalized requirement list with source tracking |
| `FeatureParser` | Main parser class |

## Functions
| Function | Description |
|----------|-------------|
| `FeatureParser.parse(text)` | Parse raw text → ParseResult with FeatureSpecification |
| `FeatureParser.build_requirement_model(spec)` | Build RequirementModel from specification |
| `FeatureParser._clean_criterion(stripped)` | Remove bullets, numbers, "Total: N criteria" markers |

## Parsing Strategy
1. Detect section headings (STORY_HEADINGS / CRITERIA_HEADINGS) with variable whitespace
2. Collect lines under active section into user_story or acceptance_criteria
3. Fallback: no headings found → collect all meaningful lines as story
4. `_clean_criterion` strips bullets (`-`, `*`, `•`), numbered lists, and "(Total: N criteria)"

## RequirementModel Sources
- `acceptance_criteria` — explicit AC section found
- `derived_from_story` — story lines used (skip "As a..." wrapper)
- `story_fallback` — single story line as sole requirement

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `FeatureSpecification.criteria_count` (method of `FeatureSpecification`): `FeatureSpecification.criteria_count() -> int` - Return the number of acceptance criteria.
- `FeatureSpecification.to_dict` (method of `FeatureSpecification`): `FeatureSpecification.to_dict() -> dict[str, Any]` - Convert to dictionary format for external use.
- `RequirementModel.count` (method of `RequirementModel`): `RequirementModel.count() -> int` - Return number of normalized requirements.
- `RequirementModel.to_text` (method of `RequirementModel`): `RequirementModel.to_text() -> str` - Render requirement lines for prompt injection.
- `RequirementModel.to_numbered_text` (method of `RequirementModel`): `RequirementModel.to_numbered_text() -> str` - Render requirement lines as a numbered list.
- `FeatureParser.parse` (method of `FeatureParser`): `FeatureParser.parse(text: str) -> ParseResult` - Parse a feature specification string into user story and acceptance criteria. Args: text: Raw feature specification text Returns: ParseResult containing parsed specification or error
- `FeatureParser.build_requirement_model` (method of `FeatureParser`): `FeatureParser.build_requirement_model(specification: FeatureSpecification) -> RequirementModel` - Build a consistent requirement model from parsed specification.


## How It Works (Internals)

Private `_`-helpers - the module's real logic (2 items). Grouped under the public function that calls them.

### `FeatureParser.build_requirement_model(specification: FeatureSpecification) -> RequirementModel` - method of `FeatureParser`

- `_join_wrapped_lines(lines: list[str]) -> list[str]` (method of `FeatureParser`): Join prose lines that are wrapped continuations of the previous line. A line is a continuation when the previous line does not end in sentence-terminal punctuation (., !, ?) and the line starts with a lowercase letter...
- `_clean_criterion(stripped: str) -> str` (method of `FeatureParser`): Clean a criterion line by removing bullet markers and whitespace. Args: stripped: Already stripped line text Returns: Cleaned criterion text
