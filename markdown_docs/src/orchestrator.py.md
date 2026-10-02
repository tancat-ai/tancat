# `src/orchestrator.py`

## High-Level Purpose

Primary intelligent generation pipeline for the Streamlit app. Coordinates the full skeleton-first test generation workflow: parses user stories into test conditions, generates skeleton code with placeholders, scrapes target URLs for DOM metadata, resolves placeholders to real selectors, post-processes code, and saves output.

**Phase 1c (2026-07-26):** Now supports dual-path execution — linear pipeline (default fallback) and multi-agent `PipelineGraph` (default when langgraph installed). `LANGGRAPH_ENABLED=0` forces linear mode. See `run_pipeline_via_graph()` and `resume_graph()` for the graph path.

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
- **RAG (2026-07-21):** `_build_rag_retriever()` constructs `RAGRetriever` when `RAG_ENABLED=1` env var is set; passed to `PlaceholderOrchestrator` via `rag_retriever` kwarg

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
- **Redirect-duplicate filter (2026-08-03):** after the stateful upgrade, pages whose stateless scrape redirected to another page *and* whose content duplicates that target are dropped — automationexercise serves HTTP 200 + redirect-to-home for guessed routes like `/inventory.html`, whose bogus keys otherwise win ASSERT resolution
- **RAG (2026-07-21):** When `RAG_ENABLED=1`, `_build_rag_retriever()` creates a `RAGRetriever` wired to `MilvusLiteBackend` + `SentenceTransformerEmbedder`; passed to `PlaceholderOrchestrator` for golden-pattern retrieval during resolution

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

### `_build_rag_retriever() -> RAGRetriever | None` (static, 2026-07-21)
- Checks `RAG_ENABLED` env var — returns `None` when not set or `"0"`
- Constructs `MilvusLiteBackend` at `get_storage().rag_path()` + `SentenceTransformerEmbedder` + `RAGStore`
- Returns `RAGRetriever(store)` when store is non-empty, `None` otherwise
- Graceful degradation: any import/init error logs a warning and returns `None`

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
- **RAG (2026-07-21):** Controlled by `RAG_ENABLED=1` env var. When enabled, golden-pattern retrieval runs during placeholder resolution, feeding `GOLDEN_PATTERN_BONUS` (+20) to element scoring. RAG store must be pre-built via `python scripts/rag_ingest.py --golden --docs`.
---

## B-036 Update (2026-08-03)

### Always-on RAG (Phase 1)
`_build_rag_retriever()` no longer requires `RAG_ENABLED=1` — a missing env
var means **enabled**. `RAG_ENABLED=0` is a transitional opt-out (removed in a
later release). Empty store ⇒ no patterns ⇒ no bonus ⇒ identical behavior to
pre-RAG. Any store/embedder failure degrades to no-RAG (never blocks
generation).

### Bundled auto-seed hook (Phase 2)
`TestOrchestrator.__init__` calls `src.rag_bundled.ensure_bundled_seeded()`
when the retriever is built — first-run seed of the bundled golden pack
(eval-001..006 keys + curated Playwright docs), idempotent via
`evidence/.rag_bundled_seeded.json`. Guarded: a failure (offline embedder
download, corrupt store) logs and proceeds without RAG; the seed retries next run.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `rag_enabled_by_config` (function): `rag_enabled_by_config() -> bool` - Return the configured RAG gate (B-036 Phase 1). RAG is always-on by default: a missing RAG_ENABLED means ENABLED; only RAG_ENABLED=0 opts out. Shared with the eval harness so run records label RAG state identi...
- `TestOrchestrator.graph_conditions` (method of `TestOrchestrator`): `TestOrchestrator.graph_conditions() -> list` - Access the test conditions from the last graph run (for UI display).


## How It Works (Internals)

Private `_`-helpers - the module's real logic (14 items). Grouped under the public function that calls them.

### `TestOrchestrator.__init__(test_generator: TestGenerator, *, credential_profile: CredentialProfile | None = None, journey_steps: list[JourneyStep] | None = None, pom_mode: bool = False, provider: str = '', model: str = '', flow_store: Any | None = None, resolution_timeout: float = DEFAULT_RESOLUTION_TIMEOUT, enable_thinking: bool | None = None) -> None` - method of `TestOrchestrator`

- `_build_rag_retriever() -> Any | None` (method of `TestOrchestrator`): Build a RAGRetriever by default; RAG_ENABLED=0 opts out. B-036 Phase 1 (2026-08-03): RAG is always-on for consumers - a missing RAG_ENABLED means enabled. Graceful degradation keeps behaviour identical to the...

### `TestOrchestrator.run_pipeline(user_story: str, conditions: str, target_urls: list[str] | None = None, consent_mode: str = 'auto-dismiss', reviewed_conditions: list[TestCondition] | None = None, prebuilt_skeleton: str | None = None) -> str` - method of `TestOrchestrator`

- `_debug(message: str) -> None` (method of `TestOrchestrator`): Debug; calls `time`; returns None.
- `_extract_journey_selectors(all_scraped_data: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]` (method of `TestOrchestrator`): Build synthetic resolver elements from journey-discovered selectors.
- `_scrape_journeys_statefully(journeys: list[TestJourney], starting_url: str, credential_profile: CredentialProfile | None = None) -> tuple[dict[str, list[dict[str, Any]]], list[str], dict[str, ObservedTrail]]` (method of `TestOrchestrator`): Scrape pages by following the generated skeleton journeys step-by-step. Journeys are independent - each starts from the same base URL and follows its own path. They run in parallel via asyncio.gather to cut the journe...
- `_build_generation_conditions(conditions_text: str, reviewed_conditions: list[TestCondition] | None) -> list[TestCondition]` (method of `TestOrchestrator`): Return ordered conditions used for skeleton generation.
- `_generate_combined_skeleton_for_conditions(*, user_story: str, conditions: list[TestCondition], target_urls: list[str]) -> str` (method of `TestOrchestrator`): Generate one skeleton fragment per condition and combine them into one module.
- `_build_candidate_urls(seed_urls: list[str], page_requirements: list[PageRequirement], journeys: list[TestJourney], user_story: str, conditions: str) -> list[str]` (method of `TestOrchestrator`): Return URLs to pre-scrape before placeholder resolution. Combines: - Seed URLs (the starting page) - URLs explicitly referenced by GOTO/URL placeholders in journeys - Common path candidates derived from user story and...
- `_inject_pom_imports(code: str, pom_imports: list[str]) -> str` (method of `TestOrchestrator`): Inject POM import statements after existing imports. Finds the last existing import line and inserts POM imports after it. Skips any import lines that are already present in the code to avoid duplicate imports when th...
- `_inject_pom_instantiation(code: str, pom_instantiation: list[str]) -> str` (method of `TestOrchestrator`): Inject POM instantiation lines at the start of each test function. Finds each 'def test_' line and inserts indented instantiation lines after it. Skips instantiation if those lines are already present in the function...
- `_inject_evidence_markers(code: str, conditions: list[TestCondition]) -> str` (method of `TestOrchestrator`): Inject @pytest.mark.evidence(condition_ref=..., story_ref=...) before each test function. Maps condition IDs to test functions by order - the Nth condition maps to the Nth test. If a test already has the decorator it...

### Internal utilities

- `_normalize_journey_urls(steps: list[JourneyStep]) -> list[JourneyStep]` (method of `TestOrchestrator`): Normalize URLs in navigate steps to handle common path variations.
- `_generate_single_condition_fragment(*, user_story: str, known_urls_block: str, ordered_conditions: list[str], condition: TestCondition) -> str` (method of `TestOrchestrator`): Generate one skeleton fragment for one reviewed condition. Prompt assembly uses the PEP 750 t-string PromptBuilder - same pattern as TestGenerator._generate_skeleton_single_call. Note this renders placeholder exam...
- `_combine_condition_fragments(fragments: list[str]) -> str` (method of `TestOrchestrator`): Combine one-condition skeleton fragments into a single skeleton module. Pages are now discovered organically by the journey scraper at runtime. PAGES_NEEDED pre-declaration is no longer emitted in combined output.
- `_strip_imports_and_pages_needed(code: str) -> str` (method of `TestOrchestrator`): Return fragment body without import lines or trailing PAGES_NEEDED block.
