---
purpose: >
  Extract placeholders, page requirements, and structured journey data from LLM-generated skeleton code.
  Validates skeleton output to catch hallucinated selectors, unsupported actions, and malformed placeholders.
lines: 463
created: "2026-05-30"
---

# `src/skeleton_parser.py`

## High-Level Purpose

Parses skeleton code produced by the LLM to extract `{{ACTION:description}}` placeholders, page requirements, and structured test journeys. Provides validation to reject malformed skeletons.

## Key Patterns

- **Placeholder regex:** `\{\{(CLICK|FILL|GOTO|URL|ASSERT):([^}]+)\}\}`
- **Single-brace placeholder:** `(?<!\{)\{ACTION:(.+)\}(?!\})` — repaired to double-brace
- **Test definition:** `^\s*def\s+(test_\w+)\s*\(`
- **Page reference:** `#\s*[-*]?\s*(\w+)(?:\s+(?:\((.*?)\)|—\s*(.*?)))?\s*$`

## Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `normalise_placeholder_actions(code)` | `str` | Repairs single-brace → double-brace, maps synonyms (ADD→CLICK, VERIFY→ASSERT, etc.) |
| `parse_placeholders(code)` | `list[tuple[str,str]]` | All (action, description) pairs |
| `parse_placeholder_uses(code)` | `list[PlaceholderUse]` | PlaceholderUses with line numbers |
| `parse_pages_needed(code)` | `list[tuple[str,str]]` | PAGES_NEEDED keywords (DEPRECATED) |
| `parse_page_requirements(code)` | `list[PageRequirement]` | Typed page requirements |
| `parse_test_journeys(code)` | `list[TestJourney]` | Structured journey with steps per test function |
| `get_test_class_names(code)` | `list[str]` | Class names declared in skeleton |
| `find_malformed_placeholders(code)` | `list[str]` | Single-brace placeholders that need repair |
| `validate_skeleton(code)` | `str \| None` | Validation error message or None |

## Synonym Mapping

- NAVIGATE/GO/OPEN/VISIT → GOTO
- ADD/REMOVE/DELETE/SUBMIT/PRESS/TAP/SELECT/CHOOSE → CLICK
- VERIFY/CHECK/CONFIRM/ENSURE → ASSERT
- TYPE/ENTER → FILL

## Validation Checks

1. Malformed single-brace placeholders
2. Unsupported action types (not CLICK/FILL/GOTO/URL/ASSERT)
3. Python format-string variables inside placeholders (`{item_name}`)
4. URLs in PAGES_NEEDED block (must be keywords)
5. Hallucinated raw selectors in evidence_tracker calls
6. `pytest.skip()` in non-statement positions

## Dependencies

- `src.pipeline_models` — `PageRequirement`, `PlaceholderUse`, `TestJourney`, `TestStep`

## Depended On By

- `src/orchestrator.py` — parses skeletons after LLM generation
- `src/code_validator.py` — uses `validate_skeleton()`

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `SkeletonParser` (class)

Extract placeholders and required URLs from generated skeletons.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `SkeletonParser.__init__` (method of `SkeletonParser`): `SkeletonParser.__init__() -> None`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (6 items). Grouped under the public function that calls them.

### `SkeletonParser.normalise_placeholder_actions(code: str) -> str` - method of `SkeletonParser`

- `_replace_unsupported_placeholder_actions(code: str) -> str` (method of `SkeletonParser`): Replace unsupported placeholder-action lines with standalone pytest skips. This keeps the pipeline runnable when the model echoes teaching examples like {{ACTION:description}} or invents unsupported actions such a...
- `_single_to_double_brace(code: str) -> str` (method of `SkeletonParser`): Convert single-brace placeholders {ACTION:desc} to double-brace {{ACTION:desc}}. LLMs trained on Python f-strings interpret {{ as an escaped literal brace, so they frequently emit {ACTION:desc} when the prompt shows {...

### `SkeletonParser.parse_test_journeys(code: str) -> list[TestJourney]` - method of `SkeletonParser`

- `_build_line_offsets(lines: list[str]) -> list[int]` (method of `SkeletonParser`): Return the starting character offset for each line.
- `_offset_to_line(line_offsets: list[int], offset: int) -> int` (method of `SkeletonParser`): Convert a character offset into a 1-based line number.
- `_build_steps(block_lines: list[str], start_line: int) -> list[TestStep]` (method of `SkeletonParser`): Build ordered steps for one test function block.
- `_extract_page_object_names(block_lines: list[str]) -> list[str]` (method of `SkeletonParser`): Return page object classes referenced within a test block.
