# `src/agents/ingestion.py`

## Purpose

Ingestion Agent — analyses raw user story text into structured `StoryAnalysis`. Wraps the existing `SpecAnalyzer` for deterministic criteria extraction (handles numbered lists, comma-separated concerns, and LLM fallback for unstructured text). Optionally queries the RAG vector store for domain-specific pattern enrichment.

## Key Class: `IngestionAgent`

### Constructor
```python
IngestionAgent(client, rag_retriever=None)
```

| Param | Type | Description |
|---|---|---|
| `client` | `LLMClient` | LLM client passed to `SpecAnalyzer` |
| `rag_retriever` | `RAGRetriever \| None` | Optional — queries RAG for domain vocabulary |

### `__call__(state: PipelineState) → dict`

LangGraph node interface. Analyses `state.user_story` and returns a dict with:

- `story_analysis`: `StoryAnalysis` with extracted criteria, domain terms, assumptions
- `errors`: list of error strings (empty on success)

### Processing pipeline
1. Run `SpecAnalyzer.analyze()` for criteria extraction
2. Query RAG for domain patterns (best-effort, non-blocking)
3. Map `SpecAnalyzer.TestCondition` → pipeline `Criterion`
4. Detect source format (numbered, gherkin, free-form)

## Dependencies

- `src.spec_analyzer.SpecAnalyzer` (deterministic + LLM criteria extraction)
- `src.agents.pipeline_state` (data types)
