# src/agents/__init__.py — Package Init

## Overview

Package init for the LangGraph multi-agent skeleton generation system (Phase 1c). Enabled via `LANGGRAPH_ENABLED=1` environment variable.

## Public API

- `SkeletonGraph` — Compiled LangGraph workflow (Planner → Generator → Validator with retry loop)
- `WorkflowState` — Pydantic state model for inter-node communication

## Usage

```python
from src.agents import SkeletonGraph, WorkflowState

graph = SkeletonGraph(llm_client)
result = await graph.run(
    user_story="...",
    conditions="1. ...\\n2. ...",
    expected_test_count=2,
)
```

## Dependencies

- `langgraph>=1.2.9` (optional dependency)
- Falls back to single-call pipeline when not installed or `LANGGRAPH_ENABLED=0`
