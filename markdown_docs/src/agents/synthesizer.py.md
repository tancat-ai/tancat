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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `ScriptSynthesizerAgent.__init__` (method of `ScriptSynthesizerAgent`): `ScriptSynthesizerAgent.__init__(client: Any | None = None) -> None`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (3 items). Grouped under the public function that calls them.

### `ScriptSynthesizerAgent.__call__(state: PipelineState) -> dict[str, Any]` - method of `ScriptSynthesizerAgent`

- `_generate_per_condition(*, conditions: list[Criterion], user_story: str, base_url: str, additional_urls: list[str]) -> tuple[str, list[str]]` (method of `ScriptSynthesizerAgent`): Generate one skeleton fragment per condition and combine them. This prevents cumulative prerequisite chaining - each test function starts from scratch, matching the linear pipeline's behaviour.
- `_placeholder_skeleton(conditions: list[Criterion]) -> str` (method of `ScriptSynthesizerAgent`): Produce a minimal skeleton when no LLM client is available.

### Internal utilities

- `_strip_imports(code: str) -> str` (method of `ScriptSynthesizerAgent`): Return fragment body without import lines.
