# `src/agents/synthesizer.py`

## Purpose

Script Synthesizer Agent — test conditions → pytest skeleton code. Wraps the existing `SkeletonGraph` (Planner → Generator → Validator retry loop) for skeleton generation. When no LLM client is available, produces a placeholder skeleton with `{{GOTO}}`/`{{ASSERT}}` placeholders.

## Key Class: `ScriptSynthesizerAgent`

### Constructor
```python
ScriptSynthesizerAgent(client=None)
```

| Param | Type | Description |
|---|---|---|
| `client` | `LLMClient \| None` | If provided, builds `SkeletonGraph` for real generation |

### `__call__(state: PipelineState) → dict`

LangGraph node interface. Returns a dict with:

- `test_code`: generated pytest skeleton code with placeholders
- `errors`: validation errors or generation failure messages
- `retry_count`: reset to 0 on success

### Generation paths
1. **LLM path** (client provided): Calls `SkeletonGraph.run()` with conditions text → Planner → Generator → Validator → returns skeleton code
2. **Fallback path** (no client): Produces minimal skeleton:
   - `happy_path` conditions → `{{GOTO:home}}` + `{{ASSERT:description}}`
   - Other types → `pytest.skip('type: description — TODO')`

### Placeholder skeleton format
```python
@pytest.mark.evidence(condition_ref='TC01.01', story_ref='S01')
def test_tc01_01(page: Page, evidence_tracker):
    # Login with valid credentials
    {{GOTO:home}}
    {{ASSERT:Login with valid credentials}}
```

## Dependencies

- `src.agents.graph.SkeletonGraph` (Planner → Generator → Validator)
- `src.agents.pipeline_state` (data types)
