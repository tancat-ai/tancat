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