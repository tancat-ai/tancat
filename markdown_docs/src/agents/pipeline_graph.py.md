# `src/agents/pipeline_graph.py`

## Purpose

Full-pipeline LangGraph `StateGraph` — orchestrates the complete test-generation flow through four nodes: Ingestion → QA Director → Script Synthesizer → Postprocessor. Composes the existing `SkeletonGraph` as a sub-component of the Synthesizer node.

## Key Class: `PipelineGraph`

### Constructor
```python
PipelineGraph(client=None, rag_retriever=None, enable_checkpoint=True)
```

| Param | Type | Description |
|---|---|---|
| `client` | `LLMClient \| None` | LLM client shared across agents. None → mock agents |
| `rag_retriever` | `RAGRetriever \| None` | Optional RAG retriever for domain enrichment |
| `enable_checkpoint` | `bool` | If True, pause after QA Director for human review |

### Methods

- **`async run(user_story, base_url, ...)`** → `PipelineState`: Execute full graph. With `auto_confirm=True`, runs to completion. Without it, pauses at human checkpoint.
- **`async resume_after_checkpoint(state, confirmed_conditions)`** → `PipelineState`: Resume a paused graph with tester-confirmed conditions.
- **`compiled_graph`** → `CompiledStateGraph`: Expose the compiled graph for testing.

## Graph Structure

```
ingest → plan → [human checkpoint] → synthesize ⇄ postprocess → END
```

### Nodes
| Node | Agent | Input → Output |
|---|---|---|
| `ingest` | `IngestionAgent` | user_story → StoryAnalysis |
| `plan` | `QADirectorAgent` | StoryAnalysis → test_conditions |
| `synthesize` | `ScriptSynthesizerAgent` | test_conditions → test_code |
| `postprocess` | (inline) | test_code → validated + errors |

### Conditional Edges
- **After plan:** `auto_confirm` or `plan_confirmed` → synthesize; else → END (pause)
- **After synthesize:** errors + retries left → retry synthesize; else → postprocess

## Dependencies

- `langgraph` (optional — graph degrades gracefully if not installed)
- `src.agents.ingestion`, `src.agents.director`, `src.agents.synthesizer`
- `src.agents.pipeline_state`

## How It Works (Internals)

Private `_`-helpers — the module's real logic (3 items). Grouped under the public function that uses them:

### `PipelineGraph`
- `_after_qa_director(state: PipelineState) -> str` (function) — Route after QA Director: checkpoint, then route by persona.
- `_after_synthesizer(state: PipelineState) -> str` (function) — Route after Synthesizer: retry on failure, or proceed.
- `_route_entry(state: PipelineState) -> str` (function) — Route the entry point: document mode goes through parsing first.
