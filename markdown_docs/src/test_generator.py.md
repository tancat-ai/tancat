# `src/test_generator.py`

## High-Level Purpose

Test generation helpers for both direct generation and skeleton-first pipeline flows. Orchestrates LLM calls for skeleton generation and direct code generation, validates output, and persists generated tests to disk.

## Module Metadata

- **Lines:** 107
- **Imports:** `os`, `pathlib.Path`, `typing.Any`, `src.code_validator`, `src.file_utils`, `src.llm_client.LLMClient`, `src.prompt_utils`

## Class: `TestGenerator`

### `__init__(client=None, *, output_dir="generated_tests", model_name=None, provider_name=None, base_url=None, api_key=None)`
- Wraps `LLMClient` (or creates one from env/config)
- Ensures `output_dir` exists on disk
- Tracks `generated_files` list
- Default model: `qwen2.5:7b` (from `OLLAMA_MODEL` env var or hardcoded fallback)

### `generate_skeleton(user_story, conditions, target_urls=None, expected_count=None) -> str`
- Phase 1 of skeleton-first pipeline: generates placeholder-based skeleton code
- Builds prompt using `get_skeleton_prompt_template()` with user story, conditions, known URLs
- Appends explicit count instruction when `expected_count` is set
- Returns LLM response with `{{ACTION:description}}` placeholder tokens

### `generate_resolved_test(skeleton_code, pages_to_scrape) -> str`
- Compatibility seam for post-resolution polishing
- Currently returns skeleton code as-is (resolver does replacement work)

### `generate_and_save(request_text, page_context_or_base_url="") -> str`
- Direct (non-skeleton) generation: generates code, validates, and saves to disk
- Validates Python syntax via `validate_python_syntax()`
- Validates locator quality via `validate_generated_locator_quality()`
- Saves via `save_generated_test()` with slugified filename
- Returns path to saved test file

## Dependencies

- `src.code_validator.validate_generated_locator_quality`, `validate_python_syntax`
- `src.file_utils.save_generated_test`, `slugify`
- `src.llm_client.LLMClient`
- `src.prompt_utils.build_page_context_prompt_block`, `get_skeleton_prompt_template`

## Depended On By

- `src/orchestrator.py` — core pipeline orchestration
- `src/ui_pipeline.py` — Streamlit UI pipeline execution
- Generated test pipeline (both skeleton-first and direct modes)

## Notes

- Default model updated to `qwen2.5:7b` (was `qwen3.5:35b`)
- Supports both legacy direct generation and modern skeleton-first pipeline
- Validates generated code before saving to disk