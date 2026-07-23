# src/agents/planner.py — PlannerAgent

## Overview

LangGraph node: parses user story + acceptance criteria into a structured test plan (Markdown). This node does NOT write code — it outputs step descriptions tagged with action types (GOTO, CLICK, FILL, ASSERT).

## API

```python
class PlannerAgent:
    def __init__(self, client: LLMClient) -> None: ...
    async def __call__(self, state: WorkflowState) -> dict[str, str]: ...
```

Returns `{"test_plan": "## Test Plan\\n### test_01_..."}`.

## Prompt Strategy

- **System prompt:** ~30 lines of structured instructions — output format specification, prerequisite step rules, short description discipline.
- **User prompt:** Template with user story, prepared conditions, and exact test count.
- **Separation of concerns:** The planner outputs Markdown, not code. This is a smaller, more focused task than generating code directly — reduces hallucination.

## Input/Output

| Input | Output |
|-------|--------|
| `state.user_story` | `state.test_plan` |
| `state.conditions` | Markdown with numbered test functions |
| `state.expected_test_count` | Each function has GOTO/CLICK/FILL/ASSERT steps |

## Dependencies

- `LLMClient.generate()` (async)
- `prompt_utils.prepare_conditions_for_generation()`
