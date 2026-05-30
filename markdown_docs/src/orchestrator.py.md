# `src/orchestrator.py`

## High-Level Purpose

Core pipeline orchestrator that coordinates the full skeleton-first test generation workflow: parses user stories into test conditions, generates skeleton code with placeholders, scrapes target URLs for DOM metadata, resolves placeholders to real selectors, post-processes code, and saves output. Supports both single-condition and multi-condition (combined) skeleton generation.

## Module Metadata

- **Lines:** 666
- **Key imports:** `asyncio`, `dataclasses`, `json`, `logging`, `pathlib.Path`, `re`, `time`, `traceback`, `typing`
- **Project imports:** `src.code_validator`, `src.file_utils`, `src.journey_scraper.JourneyScraper`, `src.llm_client.LLMClient`, `src.llm_errors`, `src.orchestration_models.OrchestrationResult`, `src.pipeline_models.*`, `src.placeholder_orchestrator.PlaceholderOrchestrator`, `src.prompt_utils.*`, `src.skeleton_parser.SkeletonParser`, `src.skeleton_validator.SkeletonValidator`, `src.test_generator.TestGenerator`, `src.test_plan.review_and_fix_conditions`

## Class: `TestOrchestrator`

### `__init__(base_url, output_dir, *, client, ...)`
- Accepts LLM client or model name/provider name/base URL/api_key (creates one)
- Configures `TestGenerator`, `SkeletonParser`, `PlaceholderOrchestrator`
- Stores logging callback for progress tracing

### `run_pipeline(user_story, target_url, base_url, pages_needed) -> OrchestrationResult`
- **Entry point** — synchronous wrapper around `run_pipeline_async()`
- Runs async pipeline in a new event loop to avoid conflicts with Streamlit/Jupyter

### `run_pipeline_async(...) -> OrchestrationResult`
- Full async pipeline with 10-minute timeout
- **Phase 1:** Parse user story → test conditions via `review_and_fix_conditions()`
- **Phase 2:** Generate skeleton code with `{{ACTION:description}}` placeholders
- **Phase 3:** Scrape target URLs via `JourneyScraper` for DOM metadata
- **Phase 4:** Resolve placeholders to real selectors via `PlaceholderOrchestrator`
- **Phase 5:** Post-process code (normalize newlines, fix quotes, remove trailing whitespace)
- **Phase 6:** Save generated test file(s)

### `generate_skeleton(...) -> str`
- Public API — parses conditions then generates combined skeleton
- Validates skeleton has correct number of test functions
- Validates no hallucinated CSS selectors via `SkeletonValidator`

### `_generate_combined_skeleton_for_conditions(...)`
- Generates one skeleton fragment per condition, then combines into one module
- Each fragment validated for exactly one test function (with retry correction)
- Combined output stripped of duplicate imports and PAGES_NEEDED blocks

### `_generate_single_condition_fragment(...)`
- Generates skeleton for a single condition using `build_single_condition_skeleton_prompt()`
- Retries with correction prompt if fragment doesn't contain exactly one test function
- Validates no hallucinated selectors

### `_combine_condition_fragments(fragments) -> str`
- Strips imports and PAGES_NEEDED from each fragment
- Combines into single module with `from playwright.sync_api import Page, expect` header

### `_build_candidate_urls(seed_urls, page_requirements, journeys, ...) -> list[str]`
- Returns deduplicated seed URLs only
- URL guessing via common path patterns has been removed (journey scraper discovers all pages)

### Backwards-compatible delegation
- `_resolve_placeholder_for_page()` → delegates to `PlaceholderOrchestrator`

## Key Data Flow

```
User Story → Conditions → Skeleton (placeholders) → DOM Scraped → Resolved Code → Saved Test
```

## Dependencies

- `src.test_generator.TestGenerator` — LLM code generation
- `src.skeleton_parser.SkeletonParser` — skeleton parsing & normalization
- `src.skeleton_validator.SkeletonValidator` — validates no hallucinated selectors
- `src.placeholder_orchestrator.PlaceholderOrchestrator` — resolves {{TOKEN}} to real selectors
- `src.journey_scraper.JourneyScraper` — stateful DOM scraping
- `src.test_plan.review_and_fix_conditions` — condition parsing via LLM
- `src.prompt_utils.*` — prompt building
- `src.code_validator.validate_python_syntax`, `validate_generated_locator_quality`
- `src.file_utils.save_generated_test`

## Depended On By

- `src/ui_pipeline.py` — Streamlit UI calls `run_pipeline()`
- `cli/pipeline_runner.py` — CLI calls `run_pipeline()`
- `tests/test_orchestrator*.py` — unit tests