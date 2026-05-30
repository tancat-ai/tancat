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