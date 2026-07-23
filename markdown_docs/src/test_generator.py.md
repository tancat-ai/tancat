# `src/test_generator.py`

## High-Level Purpose

Generates placeholder-based pytest skeleton code for the intelligent pipeline. Supports two modes:

- **Single-call** (`LANGGRAPH_ENABLED=0`, default): One LLM call with full user story + conditions.
- **LangGraph** (`LANGGRAPH_ENABLED=1`): Multi-agent Planner → Generator → Validator workflow with retry loop.

## Class: `TestGenerator`

### `__init__(client=None, *, output_dir="generated_tests", model_name=None, provider_name=None, base_url=None, api_key=None)`

- Wraps `LLMClient` (or creates one from env/config)
- Ensures `output_dir` exists on disk
- Tracks `generated_files` list
- Default model: `qwen3.5:35b` (from `OLLAMA_MODEL` env var)

### `generate_skeleton(user_story, conditions, target_urls=None, expected_count=None) -> str`

- Dispatches to LangGraph or single-call path based on `LANGGRAPH_ENABLED` env var
- Returns skeleton code with `{{ACTION:description}}` placeholder tokens

### `_generate_skeleton_single_call(...)` — Private

- Original single-call pipeline: builds prompt via `get_skeleton_prompt_template()`, calls LLM
- Returns raw skeleton code

### `_generate_skeleton_langgraph(...)` — Private

- Creates `SkeletonGraph` with the configured `LLMClient`
- Runs the full Planner → Generator → Validator workflow
- Imports `langgraph` lazily; raises helpful `ImportError` if not installed
- Raises `RuntimeError` if all retries exhausted with no skeleton code

## Dependencies

- `src.llm_client.LLMClient`
- `src.prompt_utils.get_skeleton_prompt_template`
- `src.agents.graph.SkeletonGraph` (lazy import, only when `LANGGRAPH_ENABLED=1`)

## Depended On By

- `src/orchestrator.py` — core pipeline orchestration
- `src/ui_pipeline.py` — Streamlit UI pipeline execution
- `src/cli/test_case_orchestrator.py` — CLI orchestration

## Design Notes

- **Safe default:** `LANGGRAPH_ENABLED=0` — zero risk, existing behaviour preserved
- **Optional dependency:** `langgraph` is not required for normal operation
- **Import guard:** Lazy import with helpful error message if langgraph missing
- **Shared client:** Both paths use the same `LLMClient` instance — consistent provider/model across all LLM calls
