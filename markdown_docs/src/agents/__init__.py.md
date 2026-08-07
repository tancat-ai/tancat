# src/agents/__init__.py — Package Init

## Overview

Package init for the LangGraph multi-agent pipeline system (Phase 1a-c). Lazy-imports agent modules to avoid hard dependency on langgraph. Degrades gracefully when langgraph is not installed — the linear pipeline continues working normally.

Enabled by default when langgraph is available (`pip install ai-playwright-generator[langgraph]`). Set `LANGGRAPH_ENABLED=0` to force single-call linear mode.

## Public API

- `PipelineGraph` — Full multi-agent graph: Ingestion → QA Director → Script Synthesizer → Postprocessor
- `SkeletonGraph` — Skeleton-generation sub-graph: Planner → Generator → Validator (retry loop)
- `PipelineState`, `Criterion`, `StoryAnalysis` — Dataclass state types for the full pipeline
- `WorkflowState` — Pydantic state model for the skeleton-generation sub-phase
- `IngestionAgent` — Story analysis + RAG enrichment
- `QADirectorAgent` — Priority assignment + prerequisite chaining
- `ScriptSynthesizerAgent` — Skeleton code generation

## Usage

```python
from src.agents import PipelineGraph

graph = PipelineGraph(client=llm_client, rag_retriever=rag)
result = await graph.run(
    user_story="As a user I want to...",
    base_url="https://example.com",
    auto_confirm=True,
)
print(result.test_code)
```

## Dependencies

- `langgraph>=1.2.9` (optional — lazy import, degrades if not installed)

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### Internal utilities
- `_lazy_import(name: str) -> Any` (function) — Lazy-import a module that depends on optional langgraph.
