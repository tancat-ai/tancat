# `src/agents/director.py`

## Purpose

QA Director Agent — routes test criteria, assigns priority, chains prerequisites, and flags ambiguities for human review. Takes the `StoryAnalysis` from the Ingestion Agent and produces a prioritised list of `Criterion` objects ready for the Script Synthesizer.

## Key Class: `QADirectorAgent`

### Constructor
```python
QADirectorAgent(client=None)
```

| Param | Type | Description |
|---|---|---|
| `client` | `LLMClient \| None` | Reserved for future LLM-based prioritisation |

### `__call__(state: PipelineState) → dict`

LangGraph node interface. Returns a dict with:

- `test_conditions`: list of `Criterion` with assigned priority, prerequisites, clarification flags
- `errors`: error strings (empty on success)

### Priority assignment
| Condition Type | Priority |
|---|---|
| `boundary`, `negative`, `ambiguity` | `high` |
| `happy_path`, `regression` | `medium` |
| `exploratory` | `low` |

### Prerequisite chaining
Simple heuristic: test N depends on test N-1's setup. Future: LLM-based dependency analysis for complex multi-page flows.

### Ambiguity detection
Conditions with type `ambiguity` or `exploratory` are flagged `needs_clarification=True`. The human checkpoint in `PipelineGraph` pauses for review when any condition needs clarification.

## Dependencies

- `src.agents.pipeline_state` (data types)
