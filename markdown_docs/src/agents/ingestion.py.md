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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `IngestionAgent.__init__` (method of `IngestionAgent`): `IngestionAgent.__init__(client: Any, rag_retriever: Any | None = None) -> None`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (4 items). Grouped under the public function that calls them.

### `IngestionAgent.__call__(state: PipelineState) -> dict[str, Any]` - method of `IngestionAgent`

- `_criteria_from_text(conditions_text: str) -> list` (method of `IngestionAgent`): Extract criteria deterministically from numbered acceptance criteria. Each non-empty line becomes one TestCondition. Strips leading numbering (e.g. '1.', '1)', '[TC-01]'). Returns objects compatible with SpecAna...
- `_extract_change_deltas(document_text: str) -> list[ChangeDelta]` (method of `IngestionAgent`): Extract structured change deltas from a spec document via LLM. Sends a prompt asking the LLM to identify new features, modified systems, unchanged systems, and data schema changes. Parses the JSON response into Chan...
- `_extract_deltas_from_headings(text: str) -> list[ChangeDelta]` (method of `IngestionAgent`): Deterministic fallback: extract markdown headings as feature names. Each ## or ### heading becomes a ChangeDelta. Prefixes like New:, Modified: and suffixes like [NEW FEATURE], [REMOVED] ar...

### Internal utilities

- `_parse_change_deltas_json(response: str) -> list[ChangeDelta]` (method of `IngestionAgent`): Parse LLM JSON response into ChangeDelta objects. Handles common LLM output issues: markdown fences, trailing commas, and prose wrapping.
