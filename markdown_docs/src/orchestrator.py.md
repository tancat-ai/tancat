# `src/orchestrator.py`

## High-Level Purpose

Primary intelligent generation pipeline for the Streamlit app. Coordinates the full skeleton-first test generation workflow: parses user stories into test conditions, generates skeleton code with placeholders, scrapes target URLs for DOM metadata, resolves placeholders to real selectors, post-processes code, and saves output. Supports both single-condition and multi-condition (combined) skeleton generation.

## Module Metadata

- **Lines:** 791
- **Key imports:** `asyncio`, `dataclasses`, `json`, `logging`, `os`, `pathlib.Path`, `re`, `time`, `traceback`, `typing`
- **Project imports:** 
  - `src.code_postprocessor.normalise_generated_code`
  - `src.journey_scraper.*` (CredentialProfile, JourneyResult, JourneyScraper, JourneyStep, execute_journey)
  - `src.page_object_builder.PageObjectBuilder`
  - `src.pipeline_models.*` (GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney)
  - `src.placeholder_orchestrator.PlaceholderOrchestrator`
  - `src.placeholder_resolver.PlaceholderResolver`
  - `src.prerequisite_injector.PrerequisiteInjector`
  - `src.prompt_utils.*` (build_retry_conditions, build_single_condition_skeleton_prompt, count_conditions, prepare_conditions_for_generation)
  - `src.scraper.PageScraper, scrape_with_enrichment`
  - `src.semantic_candidate_ranker.SemanticCandidateRanker`
  - `src.skeleton_parser.SkeletonParser`
  - `src.skeleton_validator.SkeletonValidator`
  - `src.spec_analyzer.TestCondition, infer_condition_intent`
  - `src.test_generator.TestGenerator`
  - `src.url_utils.build_common_path_candidates, extract_route_concepts`

## Data Models

### PipelineRunResult
```python
@dataclass
class PipelineRunResult:
    skeleton_code: str = ""
    final_code: str = ""
    pages_to_scrape: list[str] = field(default_factory=list)
    scraped_pages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    scraped_errors: dict[str, str] = field(default_factory=dict)
    page_requirements: list[PageRequirement] = field(default_factory=list)
    journeys: list[TestJourney] = field(default_factory=list)
    scraped_page_records: list[ScrapedPage] = field(default_factory=list)
    generated_page_objects: list[GeneratedPageObject] = field(default_factory=list)
    unresolved_placeholders: list[str] = field(default_factory=list)
    pages_visited: list[str] = field(default_factory=list)
    pom_mode: bool = False
```

Captured metadata for the most recent pipeline run.

## Class: `TestOrchestrator`

### `__init__(test_generator, *, credential_profile=None, journey_steps=None, pom_mode=False, provider="", model="")`
- Accepts `TestGenerator` instance (no longer accepts raw LLM client or model/provider strings)
- Configures `SkeletonParser`, `PlaceholderOrchestrator`
- Stores credential profile and journey steps for authenticated scraping
- Supports POM mode flag
- Stores provider/model for vision enrichment
- Debug mode via `PIPELINE_DEBUG=1` environment variable
- Maintains pipeline diagnostics dict

### Backwards-Compatible Properties
- `resolver` → delegates to `PlaceholderOrchestrator.resolver`
- `scraper` → delegates to `PlaceholderOrchestrator.scraper`
- `page_object_builder` → delegates to `PlaceholderOrchestrator.page_object_builder`
- `semantic_ranker` → delegates to `PlaceholderOrchestrator.semantic_ranker`

These allow existing test code to mock directly on orchestrator instance without reaching into `_placeholder_orchestrator`.

### `run_pipeline(user_story, conditions, target_urls=None, consent_mode="auto-dismiss", reviewed_conditions=None) -> str`
- **Main entry point** — async pipeline execution
- Sets starting URL from target_urls
- Updates placeholder orchestrator with starting URL
- Returns final generated code as string

### Pipeline Phases

**Phase 1: Generate Skeleton**
- Parse conditions via `prepare_conditions_for_generation()`
- If reviewed_conditions provided and >1: generate combined skeleton via `_generate_combined_skeleton_for_conditions()`
- Otherwise: generate single skeleton via `test_generator.generate_skeleton()`
- Normalize placeholders via `parser.normalise_placeholder_actions()`
- Validate skeleton structure via `parser.validate_skeleton()`
- Validate no hallucinated selectors via `SkeletonValidator`
- **Phase 3.5:** Detect zero-placeholder skeletons and retry once with stricter prompt
- Parse placeholders and test journeys from skeleton
- Retry once if journey count mismatch

**Phase 2: Build Candidate URLs**
- Combine static seed URLs with page requirements and journeys
- URL guessing via common path patterns (uses `url_utils.build_common_path_candidates()`)

**Phase 3: Scrape Pages**
- Initial static scrape via `scraper.scrape_all()`
- **AI-027:** Apply vision enrichment to scraped elements when possible
- Re-extract elements from enriched ScrapeResult objects
- Fall back to raw_scraped_data if last_scrape_results is empty (mocked tests)

**Phase 4: Journey Execution (Phase B)**
- If journey_steps provided: execute authenticated journey via `execute_journey()`
- Captures pages during authenticated flow
- Records diagnostics

**Phase 5: Resolve Placeholders**
- Delegates to `PlaceholderOrchestrator` for placeholder resolution
- Combines static and journey-scraped data

**Phase 6: Post-Process and Save**
- Post-process code via `normalise_generated_code()`
- Save generated test file(s)

### `_build_generation_conditions(conditions, reviewed_conditions) -> list[TestCondition]`
- Prepares conditions for skeleton generation
- Uses reviewed_conditions if provided, otherwise parses from text

### `_generate_combined_skeleton_for_conditions(user_story, conditions, target_urls) -> str`
- Generates one skeleton fragment per condition
- Combines fragments into single module
- Strips duplicate imports and PAGES_NEEDED blocks

### `_generate_single_condition_fragment(...)`
- Generates skeleton for single condition
- Retries with correction prompt if fragment doesn't contain exactly one test function
- Validates no hallucinated selectors

### `_combine_condition_fragments(fragments) -> str`
- Strips imports and PAGES_NEEDED from each fragment
- Combines into single module with standard header

### `_build_candidate_urls(seed_urls, page_requirements, journeys, user_story, conditions) -> list[str]`
- Returns deduplicated seed URLs
- URL guessing via common path patterns using `url_utils`

### `_debug(message)`
- Conditional debug logging via `PIPELINE_DEBUG=1`

## Key Data Flow

```
User Story → Conditions → Skeleton (placeholders) → DOM Scraped → Resolved Code → Saved Test
```

With optional:
- Journey execution for authenticated flows
- Vision enrichment for scraped elements
- POM mode for Page Object Model generation

## Dependencies

- `src.test_generator.TestGenerator` — LLM code generation
- `src.skeleton_parser.SkeletonParser` — skeleton parsing & normalization
- `src.skeleton_validator.SkeletonValidator` — validates no hallucinated selectors
- `src.placeholder_orchestrator.PlaceholderOrchestrator` — resolves {{TOKEN}} to real selectors
- `src.journey_scraper.JourneyScraper` — stateful DOM scraping
- `src.scraper.PageScraper, scrape_with_enrichment` — static scraping with vision enrichment
- `src.semantic_candidate_ranker.SemanticCandidateRanker` — semantic ranking of candidates
- `src.page_object_builder.PageObjectBuilder` — POM generation
- `src.prompt_utils.*` — prompt building
- `src.code_postprocessor.normalise_generated_code` — post-processing
- `src.url_utils.build_common_path_candidates, extract_route_concepts` — URL discovery
- `src.test_plan.review_and_fix_conditions` — condition parsing via LLM

## Depended On By

- `src/ui_pipeline.py` — Streamlit UI calls `run_pipeline()`
- `cli/pipeline_runner.py` — CLI calls `run_pipeline()`
- `tests/test_orchestrator*.py` — unit tests

## Notes

- Constructor signature changed: now accepts `TestGenerator` instance directly instead of raw LLM client parameters
- Supports both legacy single-condition and new multi-condition combined skeleton generation
- Vision enrichment (AI-027) runs after initial scrape, before placeholder resolution
- Journey execution (Phase B) enables authenticated scraping for login-required flows
- POM mode generates Page Object Models instead of direct Playwright code
- Debug output controlled by `PIPELINE_DEBUG=1` environment variable