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