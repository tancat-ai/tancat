# `src/prompt_utils.py`

## High-Level Purpose
Utilities for building, formatting, and managing LLM prompts used in skeleton generation and placeholder resolution phases.

## Module Metadata
- **Lines:** ~250
- **Imports:** `dataclasses`, `typing`, `src.pipeline_models`

## Functions

### `build_skeleton_prompt(story: UserStory, page_count: int) -> str`
Builds Phase 1 prompt for skeleton generation with placeholder tokens.

### `build_resolution_prompt(code: str, candidates: list[Element]) -> str`
Builds Phase 2 prompt for LLM-assisted resolution (fallback mode).

### `format_criteria_list(criteria: list[str]) -> str`
Formats acceptance criteria with numbered list and total count.

### `inject_placeholder_rules(prompt: str) -> str`
Appends allowed placeholder types and usage rules to a prompt.

## Key Design Decisions
- Prompt templates separated from orchestration logic
- Explicit "DO NOT skip" rules baked into templates
- Placeholder syntax enforced at prompt level

## Dependencies
- `src.pipeline_models`

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 7 items):

### `count_conditions(conditions: str) -> int` (function)

Return the number of numbered criteria in the conditions text.

### `prepare_conditions_for_generation(conditions: str) -> str` (function)

Prepare conditions text for LLM generation by ensuring proper numbering.

### `build_retry_conditions(conditions: str, expected_count: int) -> str` (function)

Format conditions for a retry with a strict count requirement.

### `build_single_condition_skeleton_prompt(user_story: str, known_urls_block: str, ordered_conditions: list[str], target_condition_ref: str, target_condition_text: str, target_condition_expected: str, target_condition_intent: str | None) -> str` (function)

Build a prompt for generating a single test function fragment.

### `get_skeleton_prompt_template(expected_count: int | None = None) -> str` (function)

Return a template for Phase 1 skeleton-generation prompt.

### `get_streamlit_system_prompt_template() -> str` (function)

Return the system prompt for the Streamlit UI.

### `build_page_context_prompt_block(page_context: str) -> str` (function)

Format the scraped page context for inclusion in an LLM prompt.
