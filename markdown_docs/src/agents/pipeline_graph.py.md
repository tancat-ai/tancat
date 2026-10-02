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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `PipelineGraph.__init__` (method of `PipelineGraph`): `PipelineGraph.__init__(client: Any | None = None, rag_retriever: Any | None = None, enable_checkpoint: bool = True) -> None`


### Additional helpers (docs refresh 2026-10-02)

Private helpers with real logic not listed above.

### `PipelineGraph.__init__(client: Any | None = None, rag_retriever: Any | None = None, enable_checkpoint: bool = True) -> None` - method of `PipelineGraph`

- `_build_graph() -> CompiledStateGraph` (method of `PipelineGraph`): Build and compile the StateGraph. Entry routing: text mode -> ingest; document mode -> parse_document -> ingest.

- `_parse_document(state: PipelineState) -> dict[str, Any]` (method of `PipelineGraph`): Pre-processing node: PDF/Markdown -> structured text. Only runs when input_mode == "document" (routed by _route_entry). Uses the configured OCR backend (OCR_BACKEND env var, default: pymupdf). 16b Phase 2 (...
- `_ingest(state: PipelineState) -> dict[str, Any]` (method of `PipelineGraph`): Ingestion Agent: analyse the user story.
- `_ingest_mock(state: PipelineState) -> dict[str, Any]` (method of `PipelineGraph`): Mock ingestion for when no LLM client is available.
- `_impact_map(state: PipelineState) -> dict[str, Any]` (method of `PipelineGraph`): Impact Mapper: ChangeDelta + persona_role -> ImpactMap per change. For each ChangeDelta extracted by the Ingestion Agent, builds an ImpactMap describing the blast radius, regression areas, test scenarios, and risk leve...
- `_consolidated_report(state: PipelineState) -> dict[str, Any]` (method of `PipelineGraph`): Build a ConsolidatedReport from all pipeline outputs. Used by the product_owner persona route - skips test code generation and produces a human-readable report instead.
- `_postprocess(state: PipelineState) -> dict[str, Any]` (method of `PipelineGraph`): Code Postprocessor: validate syntax, strip evidence for export. Skips syntax validation when the code contains double-brace placeholders (skeleton mode) - placeholders are not valid Python until resolved.
