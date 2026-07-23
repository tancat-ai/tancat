# src/agents/generator.py — GeneratorAgent

## Overview

LangGraph node: consumes the Planner's structured test plan and produces pytest skeleton code with double-brace placeholders. Uses a focused system prompt that mimics a Senior SDET.

## API

```python
class GeneratorAgent:
    def __init__(self, client: LLMClient) -> None: ...
    async def __call__(self, state: WorkflowState) -> dict[str, str | list]: ...
```

Returns `{"skeleton_code": "import pytest\\n...", "validation_errors": []}`.

## Prompt Strategy

- **System prompt:** ~25 lines — critical requirements (pytest sync format, double-brace placeholders only, no real selectors), placeholder format specification, example output.
- **User prompt:** Template with user story, test plan (or conditions fallback), and exact test count.
- **Fallback:** When `state.test_plan` is empty, generator uses `state.conditions` directly — handles single-call compatibility.

## Input/Output

| Input | Output |
|-------|--------|
| `state.user_story` | `state.skeleton_code` |
| `state.test_plan` (or `state.conditions`) | Valid Python with `{{ACTION:desc}}` placeholders |
| `state.expected_test_count` | Correct number of test functions |

## Notes

- `validation_errors` is reset to `[]` on each generation — the Validator re-evaluates from scratch.
- Real `LLMClient.generate()` handles code extraction and whitespace normalisation; the agent just passes through.
