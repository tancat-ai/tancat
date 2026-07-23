# src/agents/graph.py — SkeletonGraph

## Overview

LangGraph `StateGraph` wiring for the multi-agent skeleton generation pipeline.

## Graph Topology

```
[Planner] → [Generator] → [Validator]
                          ↖_________↙ (retry loop, max 2)
                              ↓ (pass)
                         [Return skeleton]
```

## API

```python
class SkeletonGraph:
    def __init__(self, client: LLMClient) -> None: ...
    async def run(
        self,
        *,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        expected_test_count: int = 0,
        raw_dom_snapshot: str = "",
        max_retries: int = 2,
    ) -> dict[str, Any]: ...
```

Returns `{"skeleton_code": str, "test_plan": str, "validation_errors": list[str], "retry_count": int}`.

## Nodes

| Node | Class | Type | Description |
|------|-------|------|-------------|
| `plan` | `PlannerAgent` | async | Story → test plan Markdown |
| `generate` | `GeneratorAgent` | async | Plan → skeleton code |
| `validate` | `ValidatorAgent` | sync | Check skeleton, report errors |

## Routing

`_should_retry(state)` is the conditional edge from `validate`:
- **`"generate"`** — when `validation_errors` is non-empty AND `retry_count <= max_retries`
- **`END`** — when no errors OR retries exhausted

## Integration

Called by `TestGenerator._generate_skeleton_langgraph()` when `LANGGRAPH_ENABLED=1`. The `LLMClient` is injected at `__init__` — agents share the same provider/model configuration. All LLM calls happen within `asyncio.run()` via `graph.ainvoke()`.

## Dependencies

- `langgraph` (StateGraph, END, CompiledStateGraph)
- `src.agents.planner`, `src.agents.generator`, `src.agents.validator`
- `src.agents.state.WorkflowState`
