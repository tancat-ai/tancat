# Architecture Overview: AI-Playwright-Test-Generator

This document provides a high-level architectural overview of the AI-Playwright-Test-Generator, detailing its modular structure, component interactions, and core data pipelines.

## 1. High-Level Summary

The system is designed as an **Intelligence Pipeline** that transforms unstructured natural language user stories into executable, high-quality Playwright Python test scripts. It leverages Large Language Models (LLMs) for reasoning and automated web scraping to gain real-world context from target applications.

---

## 2. Project Structure & Module Responsibilities

### 🌐 Interface Layer

| Module | Role |
|--------|------|
| `streamlit_app.py` | Primary entry point. Web-based UI to input user stories, configure LLM providers, and view generation progress/reports. |
| `cli/main.py` | CLI entry point (argparse-based). Triggers the generation pipeline for CI/CD integration. |
| `cli/config.py` | `AnalysisMode`, `ReportFormat` enums and CLI configuration. |
| `cli/input_parser.py` | Parses user story input and file arguments. |
| `cli/test_case_orchestrator.py` | CLI-specific test orchestration wrapper. |
| `cli/evidence_generator.py` | CLI evidence collection and export. |
| `cli/report_generator.py` | CLI report generation (HTML/Markdown/Jira). |
| `main.py` | **DEPRECATED** — compatibility wrapper that forwards to `cli.main`. |

### ⚙️ Orchestration Layer

| Module | Role |
|--------|------|
| `src/orchestrator.py` (`TestOrchestrator`) | The "brain" of the system. Manages sequential execution of the entire pipeline via `run_pipeline()`: analysis → skeleton generation → scraping → placeholder resolution → post-processing. |
| `src/placeholder_orchestrator.py` (`PlaceholderOrchestrator`) | Resolution coordinator. Owns scraper, resolver, and ranker instances. Handles stateful scraping upgrades and sequential placeholder replacement with journey-aware page tracking. |

### 🧠 Intelligence & Analysis Layer

| Module | Role |
|--------|------|
| `src/spec_analyzer.py` | Uses LLMs to parse raw user stories into structured `TestCondition` objects (acceptance criteria). |
| `src/user_story_parser.py` | Breaks down raw user stories into structured components. |
| `src/test_plan.py` | Data model for test planning and coverage tracking. |
| `src/test_generator.py` (`TestGenerator`) | Core engine that generates skeleton Playwright tests with `{{ACTION:description}}` placeholders using the LLM. |
| `src/llm_client.py` (`LLMClient`) | Unified interface for interacting with LLM providers (Ollama, etc.). |
| `src/llm_providers/__init__.py` | Provider registry — maps provider names to implementations. |
| `src/llm_errors.py` | LLM error types and retry logic helpers. |
| `src/prompt_utils.py` | Prompt construction: `build_single_condition_skeleton_prompt()`, `prepare_conditions_for_generation()`, `build_retry_conditions()`. |

### 🔍 Context Extraction Layer

| Module | Role |
|--------|------|
| `src/scraper.py` (`PageScraper`) | Stateless HTTP scraper using httpx + BeautifulSoup. Extracts DOM metadata (selectors, text, role) for placeholder resolution. Locators are NEVER injected into LLM prompts. |
| `src/stateful_scraper.py` (`StatefulPageScraper`) | Session-aware browser automation for pages requiring authentication state (cart, checkout). Falls back to PageScraper if session scrape produces no elements. |
| `src/journey_scraper.py` (`CartSeedingScraper`) | Journey-aware scraper — seeds the cart with items, then scrapes cart/checkout pages that require session state. |

### 🛠️ Refinement & Post-processing Layer

| Module | Role |
|--------|------|
| `src/placeholder_resolver.py` (`PlaceholderResolver`) | Critical bridge between "plan" and "reality". Matches placeholders to real CSS/XPath selectors using scraped DOM data. Includes text-content validation and confidence thresholds. |
| `src/locator_scorer.py` (`LocatorScorer`) | Scores locators by reliability: `data-testid > id > name > aria-label > css-class > text > xpath`. Applies +10 bonus when element text matches action description. |
| `src/semantic_candidate_ranker.py` (`SemanticCandidateRanker`) | When multiple candidates have similar scores (threshold ±2), uses LLM to choose the best match. |
| `src/page_object_builder.py` (`PageObjectBuilder`) | Generates Page Object Model classes from scraped page data for test maintainability. |
| `src/skeleton_parser.py` (`SkeletonParser`) | Parses LLM-generated skeleton code → extracts `TestJourney[]`, `PlaceholderUse[]`, `PageRequirement[]`. Normalizes placeholder actions. |
| `src/skeleton_parser.py` (`SkeletonValidator`) | Validates skeleton uses ONLY placeholders, not real CSS selectors (prevents hallucination). |
| `src/code_postprocessor.py` (`normalise_generated_code()`) | Final code normalization: consent mode handling, newline fixes (`normalise_code_newlines()`), import ordering. |
| `src/code_validator.py` (`CodeValidator`) | Validates generated Python for syntax errors and common issues. |

### 💾 Persistence & Reporting Layer

| Module | Role |
|--------|------|
| `src/pipeline_writer.py` (`PipelineWriter`) | Physical creation of `.py` files in `generated_tests/`, including package structuring, file normalization, and `manifest.json`. |
| `src/pipeline_run_service.py` | Tracks pipeline run history: run_id, timestamps, artifacts. |
| `src/pipeline_report_service.py` | Aggregates execution results, coverage metrics, and screenshots into HTML/Markdown/Jira reports. |
| `src/report_builder.py` | Builds report dictionaries from test results merged with evidence data. |
| `src/report_formatters.py` | Renders reports in 3 formats: local MD, Jira MD, base64 HTML. Includes failure diagnostics section. |
| `src/evidence_tracker.py` (`EvidenceTracker`) | Captures runtime diagnostics during test execution: failure_note, diagnosis, screenshots. |
| `src/evidence_loader.py` | Loads evidence JSON from test packages for report generation. |
| `src/failure_reporter.py` | Generates "Failure Diagnostics" sections with page URL, failure note, suggested alternatives, available elements, screenshot paths. |

### 📦 Data Models (Shared Layer)

| Module | Data Classes |
|--------|-------------|
| `src/pipeline_models.py` | `PlaceholderUse`, `TestStep`, `PageRequirement`, `TestJourney`, `ScrapedPage`, `GeneratedPageObject`, `ManifestRecord`, `PipelineArtifactSet` |

### 🖥️ UI Layer (Streamlit Support)

| Module | Role |
|--------|------|
| `src/ui_pipeline.py` | Pipeline execution helpers for Streamlit UI — business logic only (no rendering). Contains `run_pipeline()`, `build_test_plan()`, `execute_saved_test()`, `build_report_bundle()`. Extracted from `streamlit_app.py` to enable testing outside Streamlit context. |
| `src/ui_renderers.py` | Streamlit rendering helpers — pure UI, no business logic. Contains `SidebarConfig`, `RequirementsInput`, `ResultsPanel`, `RunResultsDisplay`, `EvidenceViewer`. Extracted from `streamlit_app.py`. |

### 🔧 Utility Modules

| Module | Role |
|--------|------|
| `src/file_utils.py` | `save_generated_test()`, `normalise_code_newlines()` helpers. |
| `src/url_utils.py` | URL helpers: `extract_seed_domain()`, `build_common_path_candidates()`, `heuristic_url_from_description()`, `filter_urls_to_allowed_domain()`. |
| `src/url_inference.py` | URL transition inference for journey-aware placeholder resolution. Extracted from `placeholder_orchestrator.py`. |
| `src/pytest_output_parser.py` | Parses pytest stdout → structured results for reporting. |
| `src/config.py` | Pipeline configuration constants. |
| `src/run_utils.py` | Test execution utilities. |
| `src/report_utils.py` | Shared report formatting helpers. |
| `src/coverage_utils.py` | Coverage calculation helpers. |
| `src/gantt_utils.py` | Gantt chart generation for pipeline visualization. |
| `src/heatmap_utils.py` | Heatmap visualization utilities. |
| `src/evidence_serializer.py` | Evidence JSON serialization (sidecar file writing). Extracted from `evidence_tracker.py`. |
| `src/screenshot_capture.py` | Screenshot capture and annotation utilities. Extracted from `evidence_tracker.py`. |
| `src/state_tracker.py` | DOM state tracking — detects changes and URL transitions. Extracted from `journey_scraper.py`. |
| `src/form_detector.py` | Form detection and element classification (selector constants). Extracted from `journey_scraper.py`. |
| `src/semantic_matcher.py` | Token-based semantic similarity for placeholder matching. Extracted from `placeholder_resolver.py`. |
| `src/intent_matcher.py` | Intent-based element filtering for placeholder resolution. Extracted from `placeholder_resolver.py`. |
| `src/code_normalizer.py` | Deterministic code normalization transforms. Extracted from `code_postprocessor.py`. |
| `src/llm_reasoning_filter.py` | LLM reasoning text detection and stripping. Extracted from `code_postprocessor.py`. |

---

## 3. Pipeline Flow (5 Phases)

```
User Input → Phase 1: Analysis → Phase 2: Skeleton Generation → Phase 3: Context Extraction
                                              ↓
Phase 4: Placeholder Resolution → Phase 5: Post-Processing → Phase 6: Output & Reporting
```

### Phase 1: Analysis
`streamlit_app.py` / `cli/main.py` → `spec_analyzer.py` → `llm_client.py` → `TestCondition[]`

Raw user story text is parsed by the LLM into structured acceptance criteria (`TestCondition` objects).

### Phase 2: Skeleton Generation
`orchestrator.py` → `test_generator.py` → `llm_client.py` → skeleton code with placeholders

The LLM generates pytest test skeletons using `{{ACTION:description}}` placeholder syntax. The LLM never sees real locators, eliminating hallucination. If journey count doesn't match expected criteria count, the orchestrator retries once with a stricter prompt.

### Phase 3: Context Extraction
`placeholder_orchestrator.py` → `scraper.py` (stateless) → `journey_scraper.py` / `stateful_scraper.py` (stateful upgrade)

Pages are scraped statelessly first. Then cart/checkout pages are upgraded with session-aware scraping. Pages with 0 elements get a stateful retry.

### Phase 4: Placeholder Resolution
`placeholder_orchestrator.py` → `placeholder_resolver.py` → `locator_scorer.py` → `semantic_candidate_ranker.py` (LLM tiebreaker)

For each journey step, placeholders are resolved sequentially while tracking the active page. The resolver scopes to the current journey URL first, then falls back to all scraped pages. When multiple candidates have similar scores, the semantic ranker uses the LLM to choose.

### Phase 5: Post-Processing
`orchestrator.py` → `code_postprocessor.py` → `code_validator.py`

Final code normalization: consent mode injection, newline fixes, import ordering, and syntax validation.

### Phase 6: Output & Reporting
`pipeline_writer.py` → `pipeline_run_service.py` → `pipeline_report_service.py` → `report_builder.py` → `report_formatters.py`

Generated test files are written to `generated_tests/` with a `manifest.json`. After pytest execution, evidence is loaded and reports are generated in 3 formats.

---

## 4. Dependency Graph

```mermaid
graph TD
    subgraph "Interface Layer"
        UI[streamlit_app.py]
        UIPipeline[src/ui_pipeline.py]
        UIRender[src/ui_renderers.py]
        CLI[cli/main.py]
        CLIInput[cli/input_parser.py]
        CLIMenu[cli/menu_renderer.py]
        CLIPipeline[cli/pipeline_runner.py]
        CLIRender[cli/report_generator.py]
        CLIEvidence[cli/evidence_generator.py]
        CLISession[cli/session.py]
        CLITestOrch[cli/test_case_orchestrator.py]
        CLIColor[cli/color.py]
        CLIConfig[cli/config.py]
    end

    subgraph "Orchestration Layer"
        Orch[src/orchestrator.py]
        POrc[src/placeholder_orchestrator.py]
    end

    subgraph "Intelligence Layer"
        Spec[src/spec_analyzer.py]
        Gen[src/test_generator.py]
        LLM[src/llm_client.py]
        Providers[src/llm_providers/]
        Prompt[src/prompt_utils.py]
        SParse[src/skeleton_parser.py]
    end

    subgraph "Context Layer"
        Scrape[src/scraper.py]
        Stateful[src/stateful_scraper.py]
        Journey[src/journey_scraper.py]
        FormDetect[src/form_detector.py]
        StateTrack[src/state_tracker.py]
        URLInfer[src/url_inference.py]
    end

    subgraph "Refinement Layer"
        Res[src/placeholder_resolver.py]
        Score[src/locator_scorer.py]
        Rank[src/semantic_candidate_ranker.py]
        SemMatch[src/semantic_matcher.py]
        IntentMatch[src/intent_matcher.py]
        POM[src/page_object_builder.py]
        PostProc[src/code_postprocessor.py]
        CodeNorm[src/code_normalizer.py]
        LLMFilter[src/llm_reasoning_filter.py]
        Val[src/code_validator.py]
    end

    subgraph "Output Layer"
        Writer[src/pipeline_writer.py]
        RunSvc[src/pipeline_run_service.py]
        ReportSvc[src/pipeline_report_service.py]
        RBuild[src/report_builder.py]
        RFormat[src/report_formatters.py]
        ETrack[src/evidence_tracker.py]
        ESerial[src/evidence_serializer.py]
        SScape[src/screenshot_capture.py]
        ELoad[src/evidence_loader.py]
        FReport[src/failure_reporter.py]
    end

    subgraph "Data Models"
        PModel[src/pipeline_models.py]
    end

    %% Flow of Control
    UI --> UIPipeline
    UI --> UIRender
    CLI --> CLIInput
    CLI --> CLIMenu
    CLI --> CLIPipeline
    CLI --> CLISession
    CLI --> CLIColor
    CLI --> CLIConfig
    CLIInput --> CLIConfig
    CLIMenu --> CLIColor
    CLIPipeline --> Orch
    CLIPipeline --> CLITestOrch
    CLIPipeline --> CLIEvidence
    CLIPipeline --> CLIRender
    UIPipeline --> Orch

    Orch --> Spec
    Orch --> Gen
    Orch --> POrc
    Orch --> PostProc
    Spec --> LLM
    Gen --> LLM
    Gen --> Prompt
    Gen --> SParse
    LLM --> Providers
    POrc --> Scrape
    POrc --> Stateful
    POrc --> Journey
    POrc --> Res
    POrc --> POM
    POrc --> URLInfer
    Journey --> FormDetect
    Journey --> StateTrack
    Res --> Score
    Res --> Rank
    Res --> SemMatch
    Res --> IntentMatch
    Rank --> LLM
    PostProc --> CodeNorm
    PostProc --> LLMFilter
    PostProc --> Val
    Orch --> Writer
    Writer --> RunSvc
    Writer --> ReportSvc
    ReportSvc --> RBuild
    RBuild --> ELoad
    RBuild --> FReport
    RFormat --> FReport
    ETrack --> ESerial
    ETrack --> SScape
```

---

## 5. Key Data Flows

### A. Requirement-to-Condition Flow (Analysis)
1. **Input**: Raw text user story from `streamlit_app.py`.
2. **Process**: `TestOrchestrator` passes text to `SpecAnalyzer`.
3. **LLM Action**: `LLMClient` parses the text into structured JSON.
4. **Output**: A list of `TestCondition` objects (Acceptance Criteria).

### B. Skeleton-First Flow (Two-Phase Generation)
1. **Input**: URL/Requirement from `TestOrchestrator`.
2. **Phase 1 - Scraping**: `PageScraper` extracts DOM elements → structured data (`selector`, `text`, `role`). NEVER injected into LLM prompt.
3. **Phase 2 - Skeleton Generation**: `TestGenerator` prompts LLM to write test skeletons using placeholders (`{{CLICK:"checkout button"}}`). LLM never sees locators.
4. **Resolution**: `PlaceholderResolver` matches placeholder descriptions against scraped element metadata → substitutes real Playwright locators.

### C. Generation-to-Artifact Flow (Finalization)
1. **Input**: Resolved Python code string.
2. **Process**: `PipelineWriter` creates a directory for the specific test run.
3. **Output**: A complete, runnable `.py` file saved to `generated_tests/`, accompanied by `manifest.json`.

### D. Execution-to-Evidence Flow (Reporting)
1. **Input**: Command execution via `pytest`.
2. **Process**: `EvidenceTracker` captures runtime diagnostics during test execution.
3. **Aggregation**: `PipelineReportService` collects screenshots, logs, and coverage stats via `EvidenceLoader`.
4. **Output**: Final HTML/Markdown/Jira reports with failure diagnostics presented back to the user.

### E. Journey Scraping Flow (AI-009 Phase B)
1. **Input**: User defines `credential_profile` and `journey_steps` in the Streamlit UI sidebar.
2. **UI Bridge**: `src/ui_pipeline.py` passes `credential_profile`, `journey_steps`, and `scrape_urls` to `TestOrchestrator.run_pipeline()`.
3. **Orchestrator**: `src/orchestrator.py` detects `journey_steps` and calls `execute_journey()` from `src/journey_scraper.py` before static scraping.
4. **Journey Execution**: `execute_journey()` launches a single browser session that follows the user-defined steps (goto, click, fill, capture, wait), capturing DOM metadata at each step.
5. **Auth Detection**: If an auth redirect is detected (e.g., login page URL patterns), the journey scraper logs a warning and continues. SSO/MFA/CAPTCHA trigger explicit errors.
6. **Data Merging**: Journey results merge with static scrape data — journey data supplements (does not overwrite) existing scraped pages. New pages from the journey are added, existing pages are enriched with additional elements.
7. **Resolution**: `PlaceholderOrchestrator` resolves placeholders against the combined scrape data (static + journey).
8. **Data flow**: `UI → ui_pipeline → TestOrchestrator → execute_journey() → merge → PlaceholderOrchestrator → resolution`

---

## 6. Troubleshooting: Error-to-Module Mapping

| Symptom | Likely Module(s) | Phase |
|---------|-----------------|-------|
| "LLM returned empty response" | `llm_client.py`, `.env` (timeout too low) | 2 |
| `SyntaxError` on import lines in generated tests | `code_postprocessor.py` (newline normalization) | 5 |
| `strict mode violation: resolved to 2 elements` | `placeholder_resolver.py` — ambiguous locator | 4 |
| Last criteria get no generated tests | `test_generator.py` — LLM truncation | 2 |
| "pytest.skip: Locator not found" | `placeholder_resolver.py` — no DOM match for description | 4 |
| Wrong element matched for action | `locator_scorer.py`, `semantic_candidate_ranker.py` | 4 |
| Cross-page locator mismatch warning | `placeholder_orchestrator.py` → `_verify_page_context()` | 4 |
| Reports missing failure diagnostics | `evidence_loader.py`, `failure_reporter.py` | 6 |
| Generated test fails: `ERR_CONNECTION_REFUSED` | Target site unreachable (not a tool bug) | Runtime |
| Journey count mismatch | `skeleton_parser.py` — LLM didn't generate enough functions | 2 |
| Import error outside Streamlit context | Never import `streamlit_app.py` — triggers `st.set_page_config()` crash | Entry |

---

*Last updated: 2026-05-11*
