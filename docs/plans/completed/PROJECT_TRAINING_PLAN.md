# Project Training Plan — AI-Playwright-Test-Generator

This document is your primary reference for understanding what the project does, what each file does, and how files interact. Work through it phase by phase. Cross-reference with `docs/ARCHITECTURE.md` (module responsibilities and dependency graph), `AGENTS.md` (project rules), and `BACKLOG.md` (decisions and history).

## Table of Contents

1. [What This Project Does](#what-this-project-does)
2. [How to Read This Document](#how-to-read-this-document)
3. [Directory Map](#directory-map)
4. [src/ — Module Reference](#src---module-reference)
5. [cli/ — Module Reference](#cli---module-reference)
6. [tests/ — Test Coverage Map](#tests---test-coverage-map)
7. [The Pipeline — Step by Step](#the-pipeline---step-by-step)
8. [How Files Interact](#how-files-interact)
9. [Data Models — The Shared Language](#data-models---the-shared-language)
10. [Learning Phases](#learning-phases)
   - [Phase 0 — Setup and Orientation](#phase-0---setup-and-orientation)
   - [Phase 1 — Python and Tooling Foundations](#phase-1---python-and-tooling-foundations)
   - [Phase 2 — Playwright and Pytest Foundations](#phase-2---playwright-and-pytest-foundations)
   - [Phase 3 — Understand the Pipeline End-to-End](#phase-3---understand-the-pipeline-end-to-end)
   - [Phase 4 — UI, CLI, Reporting, and CI/CD](#phase-4---ui-cli-reporting-and-cicd)
   - [Phase 5 — Explain the Project Clearly](#phase-5---explain-the-project-clearly)
   - [Phase 6 — Build Smaller Versions from Scratch](#phase-6---build-smaller-versions-from-scratch)
   - [Phase 7 — Rewrite Readiness](#phase-7---rewrite-readiness)
11. [Progress Scorecard](#progress-scorecard)

---

## What This Project Does

Generates **executable Playwright Python test scripts** from **natural language user stories** using a local LLM (Ollama/LM Studio).

**The problem it solves:** Writing end-to-end browser tests is tedious. A tester writes a user story like *"As a customer, I want to add items to my shopping cart"* — the tool produces runnable pytest files with real locators scraped from the actual website.

**The key insight:** The LLM never sees real DOM selectors. Instead, the tool uses a **two-phase skeleton-first pipeline**:
1. **Phase 1 (LLM):** Generates test skeletons with placeholders like `{{CLICK:checkout button}}`
2. **Phase 2 (Resolver):** Replaces placeholders with real locators scraped from the live website

This prevents selector hallucination — the #1 problem with AI-generated browser tests.

**Primary interface:** Streamlit web UI (`streamlit_app.py`)
**Secondary interface:** CLI (`cli/main.py`, launched via `bash launch_cli.sh`)

---

## How to Read This Document

- **Module Reference** sections tell you what each file does and its key classes/functions
- **The Pipeline** section walks through execution from user input to generated test files
- **How Files Interact** shows dependency chains between modules
- **Learning Phases** are ordered study steps — work through them sequentially
- Cross-reference `docs/ARCHITECTURE.md` §2 for the full module responsibility table and Mermaid dependency graph

---

## Directory Map

| Directory/File | Purpose | Read This First |
|---|---|---|
| `streamlit_app.py` | Streamlit UI entry point (362 lines after refactor) | Phase 4 |
| `main.py` | **DEPRECATED** — forwards to `cli/main.py` | Don't study |
| `launch_ui.sh` | Starts the Streamlit UI | Phase 0 |
| `launch_dev.sh` | UI + mock insurance site (development only) | Phase 0 |
| `launch_cli.sh` | Starts the CLI via `python -m cli.main` | Phase 4 |
| `src/` | Core pipeline modules — the heart of the project | Phase 3 |
| `cli/` | Command-line interface module | Phase 4 |
| `tests/` | Unit tests for the tool itself (NOT generated tests) | Phase 1 |
| `generated_tests/` | Output directory — tests produced by the tool | Phase 2 |
| `scripts/` | UAT scripts, debug tools, 3D map generator | Phase 6 |
| `docs/` | Architecture, specs, plans, session notes | Phase 0 |
| `.env` | **NEVER COMMIT** — LLM model, timeout, base URL | Phase 0 |
| `pyproject.toml` | Dependencies (managed by `uv`), tool config | Phase 1 |
| `pytest.ini` | Test configuration (`testpaths = tests`) | Phase 1 |
| `.pre-commit-config.yaml` | ruff + ruff-format + mypy hooks | Phase 1 |

---

## src/ — Module Reference

Every module below has full type annotations. Type hints are mandatory — this is enforced by `mypy`.

### Orchestration Layer

#### `orchestrator.py` — `TestOrchestrator`
**The brain of the system.** Coordinates the entire pipeline via `run_pipeline()`.
- **Key method:** `async run_pipeline()` — executes all 5 phases in sequence
- **Owns instances of:** `TestGenerator`, `PlaceholderOrchestrator`, `PageScraper`, `PageObjectBuilder`, `SemanticCandidateRanker`
- **Returns:** `PipelineRunResult` with generated code, journeys, scraped pages, artifacts
- **Interacts with:** `spec_analyzer.py` (analysis), `test_generator.py` (skeleton generation), `placeholder_orchestrator.py` (resolution), `code_postprocessor.py` (post-processing)
- **Called by:** `ui_pipeline.py` (Streamlit), `pipeline_runner.py` (CLI)

#### `placeholder_orchestrator.py` — `PlaceholderOrchestrator`
**Resolution coordinator.** Manages scraping and placeholder replacement.
- **Key method:** `async _ensure_scraped()` — scrapes pages, upgrades to stateful scraping for cart/checkout
- **Key method:** `async _replace_placeholders_sequentially()` — resolves placeholders one-by-one while tracking the active page
- **Key method:** `async _find_best_element_for_current_page()` — global-best resolution across ALL scraped pages (not first-match)
- **Owns instances of:** `PageScraper`, `StatefulPageScraper`, `PlaceholderResolver`, `LocatorScorer`, `SemanticCandidateRanker`
- **Interacts with:** `scraper.py`, `stateful_scraper.py`, `placeholder_resolver.py`, `page_object_builder.py`, `url_inference.py`
- **Critical fix (2026-05-08):** Changed from first-match-per-page to global-best-match across all pages

### Intelligence and Analysis Layer

#### `spec_analyzer.py` — `SpecAnalyzer`
**Parses raw user stories into structured test conditions.**
- **Key class:** `TestCondition` — represents a single acceptance criterion with `id`, `text`, `intent`, `source_ref`
- **Key method:** `analyze(spec_text: str) -> list[TestCondition]` — calls LLM to extract structured criteria
- **Key method:** `_extract_json_array_text()` — extracts JSON from LLM responses
- **Key method:** `_repair_common_json_issues()` — fixes common LLM JSON output problems
- **Interacts with:** `llm_client.py` (LLM calls)
- **Called by:** `orchestrator.py`

#### `user_story_parser.py`
**Breaks down raw user stories into structured components.** Supports Gherkin, Jira AC bullets, numbered lists, and free-form text.
- **Called by:** `cli/input_parser.py` (CLI path), `spec_analyzer.py` (UI path)

#### `test_generator.py` — `TestGenerator`
**Core engine that generates skeleton Playwright tests with placeholders.**
- **Key method:** `async generate_skeleton()` — prompts LLM to write pytest skeletons using `{{ACTION:description}}` syntax
- **Key method:** `async generate_resolved_test()` — legacy path that generates and resolves in one step
- **Key method:** `generate_and_save()` — convenience method for simple workflows
- **CRITICAL RULE:** Generated tests use **pytest sync format** with `playwright` fixtures. NEVER `async def test_`.
- **Interacts with:** `llm_client.py`, `prompt_utils.py`, `skeleton_parser.py`
- **Called by:** `orchestrator.py`

#### `llm_client.py` — `LLMClient`
**Unified interface for LLM providers (Ollama, LM Studio, OpenRouter, etc.).**
- **Key method:** `async generate(prompt, timeout, system_prompt) -> str` — primary generation method
- **Key method:** `generate_test(prompt, timeout, system_prompt) -> str` — synchronous wrapper
- **Key method:** `set_session_provider()` — switches provider at runtime (used by UAT scripts)
- **Key method:** `_complete_sync()` — synchronous completion call
- **Key method:** `_extract_code()` — extracts code blocks from LLM responses
- **Factory function:** `create_llm_provider()` — creates client from environment config
- **Interacts with:** `src/llm_providers/` (provider implementations), `llm_errors.py` (error types)
- **Called by:** `test_generator.py`, `spec_analyzer.py`, `semantic_candidate_ranker.py`

#### `llm_errors.py`
**LLM error types and retry logic helpers.**
- **Key class:** `LLMErrorType` — enumerates error categories (timeout, empty, connection, etc.)
- **Key class:** `LLMError` — structured error with type, message, and retry suggestion
- **Key class:** `LLMResult` — wraps LLM output with metadata

#### `prompt_utils.py`
**Prompt construction for skeleton generation.**
- **Key function:** `build_single_condition_skeleton_prompt()` — builds the main skeleton generation prompt
- **Key function:** `prepare_conditions_for_generation()` — formats conditions for the LLM
- **Key function:** `build_retry_conditions()` — stricter prompt when journey count doesn't match
- **Key function:** `get_skeleton_prompt_template()` — the full system prompt template
- **Key function:** `get_streamlit_system_prompt_template()` — system prompt for Streamlit context
- **CRITICAL:** Prompts use numbered requirements, NOT XML tags (LLMs ignore XML)
- **Interacts with:** `test_generator.py` (consumes prompts)

### Context Extraction Layer

#### `scraper.py` — `PageScraper`
**Stateless HTTP scraper using httpx + BeautifulSoup (or Playwright subprocess).**
- **Key method:** `async scrape_url(url) -> (elements, metadata, error)` — extracts DOM metadata
- **Key method:** `_extract_elements_from_html()` — parses HTML to extract interactive elements
- **Key method:** `_build_selector()` — creates CSS selectors from DOM elements
- **Key method:** `_remove_consent_overlays()` — strips cookie consent banners before parsing
- **Output:** List of element dicts with `selector`, `text`, `role`, `tag`, `attributes`
- **IMPORTANT:** Locators are NEVER injected into LLM prompts. They're only used for placeholder resolution.
- **Interacts with:** `placeholder_orchestrator.py` (consumes scraped data)

#### `stateful_scraper.py` — `StatefulPageScraper`
**Session-aware browser automation for authenticated pages.**
- **Key method:** `async scrape_url(url)` — scrapes pages that require session state (cart, checkout)
- **Key method:** `_seed_cart_session()` — adds items to cart before scraping checkout pages
- **Falls back to:** `PageScraper` if session scrape produces no elements
- **Interacts with:** `placeholder_orchestrator.py`

#### `journey_scraper.py` — `JourneyScraper`, `CartSeedingScraper`
**Journey-aware scraper — follows multi-step user flows.**
- **Key class:** `JourneyStep` — represents a single step in a user journey
- **Key class:** `ScrapedStep` — scraped data for a single journey step
- **Key method:** `async scrape_journey(steps)` — navigates through journey steps, scraping each page
- **Key class:** `CartSeedingScraper(JourneyScraper)` — specialized scraper for e-commerce cart/checkout flows
- **Key method:** `_discover_selector()` — finds selectors for actions like "add to cart"
- **Interacts with:** `form_detector.py`, `state_tracker.py`

### Refinement and Post-processing Layer

#### `placeholder_resolver.py` — `PlaceholderResolver`
**Critical bridge between "plan" and "reality".** Matches placeholders to real CSS/XPath selectors.
- **Key method:** `find_best_element(action, description, page_elements) -> selector | None`
- **Key method:** `text_matches_description(element_text, action_description) -> bool` — text-content validation
- **Key method:** `rank_candidates()` — scores and ranks candidate elements
- **Key method:** `resolve_all()` — resolves all placeholders in a code string
- **Key method:** `resolve_url()` — resolves URL placeholders from page descriptions
- **Text validation:** Checks element text matches action description before accepting a match
- **Confidence threshold:** `PLACEHOLDER_MIN_CONFIDENCE` env var (default 0.3)
- **Interacts with:** `locator_scorer.py`, `semantic_matcher.py`, `intent_matcher.py`
- **Called by:** `placeholder_orchestrator.py`

#### `locator_scorer.py` — `LocatorScorer`
**Scores locators by reliability.**
- **Scoring priority:** `data-testid > id > name > aria-label > css-class > text > xpath`
- **Key method:** `score_locator(element, action, description) -> int` — scores a single element
- **Key method:** `score_candidates()` — scores multiple candidates
- **Key method:** `get_fallback_candidates()` — returns alternatives when primary fails
- **+10 bonus:** Applied when element text matches action description
- **Interacts with:** `placeholder_resolver.py`

#### `semantic_candidate_ranker.py` — `SemanticCandidateRanker`
**LLM tiebreaker when multiple candidates have similar scores.**
- **Key method:** `async choose_best_candidate()` — uses LLM to pick the best match when scores are within ±2
- **Interacts with:** `llm_client.py` (for LLM calls)
- **Called by:** `placeholder_orchestrator.py`

#### `page_object_builder.py` — `PageObjectBuilder`
**Generates Page Object Model classes from scraped page data.**
- **Key method:** `build_page_object(scraped_page)` — creates a POM class for a single page
- **Key method:** `_derive_class_name(url)` — generates class name from URL
- **Key method:** `_build_methods()` — generates interaction methods from scraped elements
- **Output:** Python module with class, locator attributes, and interaction methods
- **Interacts with:** `pipeline_writer.py` (writes POM files)

#### `skeleton_parser.py` — `SkeletonParser`, `SkeletonValidator`
**Parses LLM-generated skeleton code into structured data.**
- **Key class:** `SkeletonParser`
  - `parse_test_journeys(code) -> list[TestJourney]` — extracts journey functions
  - `parse_placeholder_uses(code) -> list[PlaceholderUse]` — finds all placeholders
  - `parse_page_requirements(code) -> list[PageRequirement]` — identifies needed pages
  - `normalise_placeholder_actions(code)` — normalizes placeholder action syntax
  - `validate_skeleton(code) -> str | None` — validates no real selectors in skeleton
- **Key class:** `SkeletonValidator`
  - `validate(skeleton_code) -> SkeletonValidationResult` — ensures skeleton uses ONLY placeholders
- **Interacts with:** `test_generator.py` (parses its output), `placeholder_orchestrator.py`

#### `code_postprocessor.py`
**Final code normalization.**
- **Key function:** `normalise_generated_code(code, consent_mode, target_url)` — main normalization entry point
- **Handles:** consent mode injection, newline fixes, import ordering, evidence tracker fixture injection
- **Interacts with:** `code_normalizer.py`, `llm_reasoning_filter.py`, `code_validator.py`

#### `code_normalizer.py`
**Deterministic code normalization transforms.**
- **Key functions:** `convert_standalone_placeholders()`, `replace_remaining_placeholders()`, `fix_indentation()`, `deduplicate_skip_calls()`, `ensure_test_navigation()`
- **Extracted from:** `code_postprocessor.py` (2026-05-10 refactor)

#### `llm_reasoning_filter.py`
**Strips LLM reasoning text from generated code.**
- **Key function:** `strip_llm_reasoning(code)` — removes "thinking" text that LLMs sometimes include
- **Extracted from:** `code_postprocessor.py` (2026-05-10 refactor)

#### `code_validator.py` — `CodeValidator`
**Validates generated Python code.**
- **Key function:** `validate_python_syntax(code) -> str | None` — uses `ast.parse()` to check syntax
- **Key function:** `validate_test_function(code) -> str | None` — checks for required test patterns
- **Key function:** `validate_generated_locator_quality(code) -> str | None` — checks locator quality
- **Interacts with:** `file_utils.py` (called before saving)

### Persistence and Reporting Layer

#### `pipeline_writer.py` — `PipelineWriter`
**Physical creation of test files in `generated_tests/`.**
- **Key method:** `write_run_artifacts(run_result)` — writes test files, POM files, and `manifest.json`
- **Key method:** `_build_package_dir(story_text)` — creates timestamped output directory
- **Key method:** `_build_manifest_dict()` — creates `manifest.json` with metadata
- **Output:** Complete test package with `.py` files, `manifest.json`, `conftest.py`
- **Interacts with:** `file_utils.py`, `pipeline_run_service.py`

#### `pipeline_run_service.py` — `PipelineRunService`
**Tracks pipeline run history and executes saved tests.**
- **Key class:** `PipelineExecutionResult` — structured result from a test run
- **Key method:** `run_saved_test()` — executes a previously generated test
- **Interacts with:** `pytest_output_parser.py` (parses pytest output)

#### `pipeline_report_service.py` — `PipelineReportService`
**Aggregates execution results into reports.**
- **Key class:** `PipelineReportBundle` — contains all report formats
- **Key method:** `build_reports()` — generates HTML, Markdown, and Jira reports
- **Interacts with:** `report_builder.py`, `report_formatters.py`, `evidence_loader.py`

#### `report_builder.py`
**Builds report dictionaries from test results merged with evidence data.**
- **Key function:** `build_report_dicts()` — merges coverage analysis with run results and evidence
- **Interacts with:** `evidence_loader.py`, `failure_reporter.py`

#### `report_formatters.py`
**Renders reports in 3 formats.**
- **Key function:** `generate_local_report()` — Markdown with relative screenshot paths
- **Key function:** `generate_jira_report()` — Jira-compatible Markdown (`!filename.png|thumbnail!`)
- **Key function:** `generate_html_report()` — Self-contained HTML with base64-embedded screenshots
- **All formats include:** "Failure Diagnostics" section with page URL, failure note, suggested alternatives

#### `evidence_tracker.py` — `EvidenceTracker`
**Captures runtime diagnostics during test execution.**
- **Key methods:** `navigate()`, `fill()`, `click()`, `assert_visible()`, `write()`
- **Records:** element bounding boxes, interaction types, step sequence, run history, failure notes
- **Writes:** `.evidence.json` sidecar file alongside screenshots
- **Public API:** Generated tests call these methods instead of raw Playwright calls
- **Interacts with:** `evidence_serializer.py`, `screenshot_capture.py`, `failure_reporter.py`

#### `evidence_loader.py`
**Loads evidence JSON from test packages for report generation.**
- **Key function:** `load_evidence_for_package(package_dir)` — reads all `.evidence.json` files
- **Key function:** `get_failure_diagnostics(evidence)` — extracts failure info
- **Key function:** `match_evidence_to_test()` — matches evidence to test function names
- **Interacts with:** `report_builder.py`

#### `evidence_serializer.py` — `EvidenceSerializer`
**Evidence JSON serialization (sidecar file writing).**
- **Key method:** `serialize()` — writes evidence dict to JSON sidecar
- **Key method:** `load(sidecar_path)` — reads evidence from sidecar
- **Key method:** `validate(payload)` — validates evidence structure
- **Extracted from:** `evidence_tracker.py` (2026-05-10 refactor)

#### `failure_reporter.py` — `FailureReporter`
**Generates "Failure Diagnostics" sections.**
- **Key method:** `diagnose_failure()` — analyzes why a step failed
- **Key method:** `suggest_locators()` — recommends higher-confidence alternatives
- **Key method:** `generate_failure_note()` — creates human-readable failure explanation
- **Output:** Page URL, failure note, suggested alternatives, available elements, screenshot paths
- **Interacts with:** `locator_scorer.py`

#### `screenshot_capture.py`
**Screenshot capture and annotation utilities.**
- **Key function:** `capture_screenshot()` — takes a screenshot with labeling
- **Key function:** `capture_element_screenshot()` — captures a specific element
- **Key function:** `capture_on_failure()` — captures screenshot when a step fails
- **Extracted from:** `evidence_tracker.py` (2026-05-10 refactor)

#### `pytest_output_parser.py`
**Parses pytest stdout into structured results.**
- **Key class:** `TestResult` — individual test result with status, duration, error
- **Key class:** `RunResult` — aggregate run result with pass/fail counts
- **Key function:** `parse_pytest_output(raw) -> RunResult` — main parsing entry point
- **Key function:** `format_pytest_output_for_display()` — truncates for UI display
- **Interacts with:** `pipeline_run_service.py`, `report_builder.py`

### UI Layer (Streamlit Support)

#### `ui_pipeline.py`
**Pipeline execution helpers for Streamlit UI — business logic only (no rendering).**
- **Key function:** `run_pipeline()` — executes the full pipeline from Streamlit context
- **Key function:** `build_test_plan()` — creates test plan from user input
- **Key function:** `execute_saved_test()` — runs a previously generated test
- **Key function:** `build_report_bundle()` — assembles reports for display
- **Extracted from:** `streamlit_app.py` (2026-05-10 refactor) — enables testing outside Streamlit context
- **CRITICAL:** Never import `streamlit_app.py` outside Streamlit — triggers `st.set_page_config()` crash

#### `ui_renderers.py`
**Streamlit rendering helpers — pure UI, no business logic.**
- **Key classes:** `SidebarConfig`, `RequirementsInput`, `ResultsPanel`, `RunResultsDisplay`, `EvidenceViewer`
- **Extracted from:** `streamlit_app.py` (2026-05-10 refactor)

### Utility Modules

#### `file_utils.py`
**File I/O helpers.**
- **Key function:** `save_generated_test()` — saves test code with syntax validation
- **Key function:** `normalise_code_newlines()` — fixes newline issues in generated code
- **Key function:** `slugify(text)` — creates URL-safe slugs
- **Key function:** `rename_test_file()` — renames generated test files

#### `url_utils.py`
**URL helpers.**
- **Key functions:** `extract_seed_domain()`, `build_common_path_candidates()`, `heuristic_url_from_description()`, `filter_urls_to_allowed_domain()`

#### `url_inference.py`
**URL transition inference for journey-aware placeholder resolution.**
- **Extracted from:** `placeholder_orchestrator.py` (2026-05-10 refactor)

#### `coverage_utils.py`
**Coverage calculation helpers.**
- **Key class:** `RequirementCoverage` — maps a requirement to its test coverage
- **Key function:** `build_coverage_analysis()` — matches requirements to generated tests
- **Key function:** `build_coverage_display_rows()` — prepares coverage data for UI display
- **Matching algorithm:** Number-based first (`test_01_*` → criterion 1), then keyword fallback

#### `config.py`
**Pipeline configuration constants and enums.**
- **Key enums:** `AnalysisMode`, `ReportFormat`, `DetectionMode`, `CaptureLevel`, `ScreenshotNaming`

#### `run_utils.py`
**Test execution utilities.**
- **Key function:** `build_pytest_run_command()` — constructs pytest CLI command
- **Key function:** `get_failed_nodeids()` — extracts failed test IDs from run results

#### `report_utils.py` / `report_formatters.py`
**Shared report formatting helpers.** `report_utils.py` contains legacy helpers; `report_formatters.py` is the current report rendering module.

#### `gantt_utils.py` / `heatmap_utils.py`
**Visualization utilities.** Gantt charts for pipeline timing, heatmaps for coverage confidence.

#### `state_tracker.py`
**DOM state tracking — detects changes and URL transitions.**
- **Key class:** `DOMState` — snapshot of DOM at a point in time
- **Key class:** `StateChange` — records what changed between snapshots
- **Key class:** `StateTracker` — tracks state changes across navigation
- **Extracted from:** `journey_scraper.py` (2026-05-10 refactor)

#### `form_detector.py`
**Form detection and element classification.**
- **Key class:** `FormField` — represents a detected form field
- **Key class:** `FormDetector` — identifies forms, submit buttons, input types
- **Extracted from:** `journey_scraper.py` (2026-05-10 refactor)

#### `semantic_matcher.py`
**Token-based semantic similarity for placeholder matching.**
- **Key class:** `SemanticMatcher` — computes word-overlap similarity between description and element text
- **Key method:** `semantic_similarity(description, text) -> float`
- **Extracted from:** `placeholder_resolver.py` (2026-05-10 refactor)

#### `intent_matcher.py`
**Intent-based element filtering for placeholder resolution.**
- **Key class:** `IntentMatcher` — filters elements by action intent (CLICK needs clickable, FILL needs fillable, etc.)
- **Key method:** `matches(element, action, description)` — checks if element matches the intended action
- **Extracted from:** `placeholder_resolver.py` (2026-05-10 refactor)

#### `accessibility_enricher.py`
**Enriches scraped elements with accessibility tree data.**
- **Key class:** `AccessibilityEnricher` — merges `page.accessibility.snapshot()` data into scraped elements
- **Interacts with:** `scraper.py` (enriches its output)

#### `element_enricher.py`
**Detects icons, decorative elements, hover-reveal patterns.**
- **Key class:** `ElementEnricher` — adds visual metadata to scraped elements

#### `browser_utils.py`
**Browser utility functions.**
- **Key function:** `dismiss_consent_overlays(page)` — handles cookie consent banners

#### `locator_fallback.py`
**Fallback locator strategies when primary locator fails.**
- **Key class:** `LocatorFallback` — builds and tries alternative locators

#### `prerequisite_injector.py`
**Injects prerequisite test steps (e.g., login before checkout test).**
- **Key class:** `PrerequisiteInjector` — analyzes test dependencies and injects navigation/auth steps

### Data Models

#### `pipeline_models.py`
**Core data structures shared across the pipeline.**

| Class | Purpose |
|---|---|
| `PlaceholderUse` | A single placeholder in the skeleton: action type, description, line number |
| `TestStep` | A single step in a test journey |
| `PageRequirement` | A page that needs to be scraped |
| `TestJourney` | A complete test journey with steps, placeholders, and page requirements |
| `ScrapedPage` | Scraped data for a single page: URL, elements, metadata |
| `GeneratedPageObject` | A generated POM class with file path and source code |
| `ManifestRecord` | Record for `manifest.json`: test name, status, timestamps |
| `PipelineArtifactSet` | Complete set of artifacts from one pipeline run |

#### `test_plan.py` — `TestPlan`
**Test planning and coverage tracking model.**
- **Key methods:** `from_conditions()`, `confirm()`, `add_condition()`, `remove_condition()`, `sign_off()`
- **Used by:** `ui_pipeline.py` (test plan UI), `spec_analyzer.py`

---

## cli/ — Module Reference

The CLI is an **argparse-based** alternative to the Streamlit UI. It provides the same pipeline functionality in a terminal context.

#### `main.py`
**CLI entry point.** Run via `python -m cli.main` or `bash launch_cli.sh`.
- **Key function:** `main() -> int` — argparse argument parser, dispatches to subcommands
- **Key function:** `cmd_generate()` — generates tests from command-line arguments
- **Key function:** `interactive_session()` — launches interactive menu mode
- **Interacts with:** `pipeline_runner.py`, `menu_renderer.py`, `session.py`

#### `session.py` — `Session`
**CLI session state dataclass.** Stores provider config, user story, URLs, and pipeline results.
- **Key function:** `create_session()` — creates a Session with defaults from `.env`

#### `input_parser.py`
**Parses user story input from various formats.**
- **Key class:** `InputParser` — detects format (Gherkin, Jira, bullets, plain text) and parses
- **Key class:** `ParsedInput` — structured result with test cases
- **Key class:** `FormatDetector` — auto-detects input format
- **Parsers:** `PlainTextParser`, `JiraParser`, `GherkinParser`, `BulletParser`
- **Interacts with:** `pipeline_runner.py`

#### `menu_renderer.py`
**Menu rendering functions for interactive mode.**
- **Key functions:** `print_header()`, `print_menu()`, `read_non_empty()`, `collect_user_story()`, `collect_urls()`
- **Interacts with:** `color.py` (ANSI colors), `main.py`

#### `color.py`
**ANSI color helpers for terminal output.**
- **Key functions:** `cyan()`, `green()`, `red()`, `yellow()`, `bold()`

#### `config.py`
**CLI configuration enums.**
- **Key enums:** `AnalysisMode`, `ReportFormat`

#### `pipeline_runner.py`
**Pipeline execution from CLI context.**
- **Key function:** `async run_pipeline(session)` — runs the full generation pipeline
- **Key function:** `run_generated_tests(session, rerun_failed)` — executes generated tests
- **Key function:** `display_run_results(session)` — shows test results in terminal
- **Key function:** `generate_reports(session)` — creates reports
- **Key function:** `view_failure_diagnostics(session)` — shows failure details
- **Interacts with:** `src/orchestrator.py`, `src/pipeline_run_service.py`, `src/pipeline_report_service.py`

#### `test_case_orchestrator.py` — `TestCaseOrchestrator`
**CLI-specific test orchestration wrapper.**
- **Key method:** `process()` — analyzes input, orders test cases, generates files
- **Key method:** `_generate_test_files()` — creates test files from analysis
- **Interacts with:** `analyzer.py` (analysis), `input_parser.py`

#### `evidence_generator.py`
**CLI evidence collection and export.**
- **Key class:** `EvidenceGenerator` — captures screenshots and generates evidence summaries
- **Key class:** `ScreenshotCapturer` — takes screenshots at key stages
- **Key method:** `create_visual_report()` — generates HTML evidence report
- **Key method:** `create_evidence_zip()` — packages evidence for export

#### `report_generator.py` — `JiraReportGenerator`
**CLI report generation (HTML/Markdown/Jira).**
- **Key method:** `create_test_case()` — creates a Jira-compatible test case
- **Key method:** `generate_confluence_html()` — Confluence-compatible HTML
- **Key method:** `generate_jira_xml()` — Jira XML import format
- **Key method:** `save_test_cases(format)` — saves in the specified format

---

## tests/ — Test Coverage Map

The `tests/` directory contains unit tests for the **tool itself** — NOT the generated tests. Generated tests live in `generated_tests/` and are run explicitly.

**Critical rule from `pytest.ini`:** `testpaths = tests` — this means `pytest -v` only runs the tool's own tests, never the generated ones.

### Test Coverage by Module

| src/ Module | Test File | Status |
|---|---|---|
| `placeholder_resolver.py` | `test_placeholder_resolver.py`, `test_placeholder_resolver_text_validation.py`, `test_placeholder_resolution_guardrails.py` | ✅ Well covered |
| `orchestrator.py` | `test_orchestrator.py`, `test_orchestrator_dynamic_scraping.py` | ✅ Covered |
| `journey_scraper.py` | `test_journey_scraper.py`, `test_stateful_scrape_switch.py` | ✅ Covered |
| `scraper.py` | `test_scraper.py` | ✅ Covered |
| `stateful_scraper.py` | `test_stateful_scraper.py` | ✅ Covered |
| `locator_scorer.py` | `test_locator_scorer.py` | ✅ Covered (15 tests) |
| `evidence_tracker.py` | `test_evidence_tracker.py` | ✅ Covered |
| `evidence_loader.py` | `test_evidence_loader.py` | ✅ Covered |
| `failure_reporter.py` | `test_failure_reporter.py` | ✅ Covered (10 tests) |
| `pytest_output_parser.py` | `test_pytest_output_parser.py` | ✅ Covered |
| `skeleton_parser.py` | `test_skeleton_parser.py`, `test_skeleton_validator.py`, `test_skeleton_prompt_template.py` | ✅ Covered |
| `spec_analyzer.py` | `test_spec_analyzer.py` | ✅ Covered |
| `page_object_builder.py` | `test_page_object_builder.py` | ✅ Covered |
| `pipeline_writer.py` | `test_pipeline_writer.py` | ✅ Covered |
| `pipeline_run_service.py` | `test_pipeline_run_service.py` | ✅ Covered |
| `pipeline_report_service.py` | `test_pipeline_report_service.py` | ✅ Covered |
| `pipeline_models.py` | `test_pipeline_models.py` | ✅ Covered |
| `semantic_candidate_ranker.py` | `test_semantic_candidate_ranker.py` | ✅ Covered |
| `coverage_utils.py` | `test_coverage_utils.py` | ✅ Covered |
| `gantt_utils.py` | `test_gantt_utils.py` | ✅ Covered |
| `heatmap_utils.py` | `test_heatmap_utils.py` | ✅ Covered (8 tests) |
| `test_plan.py` | `test_test_plan.py` | ✅ Covered |
| `spec_analyzer.py` | `test_spec_analyzer.py` | ✅ Covered |
| `user_story_parser.py` | `test_user_story_parser.py` | ✅ Covered |
| `url_resolver.py` | `test_url_resolver.py` | ✅ Covered |
| `code_validator.py` | `test_code_validator.py` | ✅ Covered |
| `prerequisite_injector.py` | `test_prerequisite_injector.py` | ✅ Covered |
| `global_best_resolution` | `test_global_best_resolution.py` | ✅ Covered (5 tests) |
| `e2e placeholder` | `test_e2e_placeholder_quoting.py`, `test_e2e_placeholder_resolution_valid_python.py` | ✅ Covered |
| `cli/` | `tests/cli/test_orchestrator.py`, `test_cli_smoke.py`, `test_cli_report_generator.py`, `test_cli_test_orchestrator.py` | ✅ Covered |
| `llm_client.py` | `test_llm_client.py` | ✅ Covered |
| `llm_errors.py` | `test_llm_errors.py` | ✅ Covered |
| `prompt_utils.py` | `test_prompt_utils.py` | ✅ Covered |
| `run_utils.py` | `test_run_utils.py` | ✅ Covered |
| `report_utils.py` | `test_report_utils.py` | ⚠️ Partial |
| `report_builder.py` | — | ⚠️ Partially covered by `test_report_utils.py` |
| `report_formatters.py` | — | ⚠️ Partially covered by `test_report_utils.py` |
| `url_utils.py` | — | ❌ Missing (pure functions, easy to add) |
| `analyzer.py` | — | ⚠️ Only indirectly tested via CLI |
| `config.py` | — | ❌ Missing (trivial constants) |

---

## The Pipeline — Step by Step

This is the core flow from user input to generated test files. Read this alongside the module reference above.

### Phase 1: Analysis
```
User Input → spec_analyzer.py → llm_client.py → TestCondition[]
```
1. User pastes a user story (or selects from a file)
2. `SpecAnalyzer.analyze()` sends the story text to the LLM
3. LLM returns structured JSON with acceptance criteria
4. Parser extracts `TestCondition` objects (id, text, intent, source_ref)
5. Tester reviews and confirms conditions in the UI

### Phase 2: Skeleton Generation
```
orchestrator.py → test_generator.py → llm_client.py → skeleton code with placeholders
```
1. `TestOrchestrator` calls `TestGenerator.generate_skeleton()`
2. `prompt_utils.py` builds the skeleton prompt with enumerated criteria
3. LLM generates pytest skeletons using `{{ACTION:description}}` placeholders
4. LLM **never sees real locators** — only placeholder descriptions
5. `SkeletonParser.parse_test_journeys()` extracts structured journeys
6. If journey count doesn't match expected criteria count, retry with stricter prompt

### Phase 3: Context Extraction
```
placeholder_orchestrator.py → scraper.py (stateless) → stateful_scraper.py (stateful upgrade)
```
1. `PlaceholderOrchestrator._ensure_scraped()` scrapes all required pages
2. `PageScraper` extracts DOM metadata (selectors, text, role, attributes)
3. Cart/checkout pages are upgraded with `StatefulPageScraper`
4. Pages with 0 elements get a stateful retry
5. `PageObjectBuilder` generates POM classes from scraped data

### Phase 4: Placeholder Resolution
```
placeholder_orchestrator.py → placeholder_resolver.py → locator_scorer.py → semantic_candidate_ranker.py
```
1. Placeholders are resolved **sequentially** while tracking the active page
2. Resolver scopes to the current journey URL first, then falls back to all pages
3. `LocatorScorer` scores each candidate (data-testid > id > name > aria-label > ...)
4. `IntentMatcher` filters by action type (CLICK needs clickable, FILL needs fillable)
5. `SemanticMatcher` computes word-overlap similarity
6. When top candidates are within ±2 score, `SemanticCandidateRanker` uses LLM as tiebreaker
7. **Global best match:** ALL candidates from ALL pages are collected, sorted by score, best is selected

### Phase 5: Post-Processing
```
orchestrator.py → code_postprocessor.py → code_normalizer.py → llm_reasoning_filter.py → code_validator.py
```
1. `normalise_generated_code()` applies all normalization transforms
2. `strip_llm_reasoning()` removes LLM "thinking" text
3. `fix_indentation()`, `deduplicate_skip_calls()`, `ensure_test_navigation()`
4. `validate_python_syntax()` checks code compiles
5. Consent mode handling and import ordering

### Phase 6: Output and Reporting
```
pipeline_writer.py → pipeline_run_service.py → pipeline_report_service.py → report_builder.py → report_formatters.py
```
1. `PipelineWriter.write_run_artifacts()` creates test package directory
2. Test files, POM files, `conftest.py`, and `manifest.json` are written
3. `PipelineRunService.run_saved_test()` executes the tests via pytest
4. `EvidenceTracker` captures runtime diagnostics (failure notes, screenshots)
5. `pytest_output_parser.py` parses pytest stdout
6. `EvidenceLoader` loads `.evidence.json` sidecars
7. `ReportBuilder` merges coverage + run results + evidence
8. `ReportFormatters` generate 3 report formats (local MD, Jira MD, HTML)

---

## How Files Interact

### Entry Points
```
streamlit_app.py
  └── ui_pipeline.py (business logic)
        └── orchestrator.py (pipeline coordination)
  └── ui_renderers.py (UI only)

cli/main.py
  └── pipeline_runner.py (CLI pipeline execution)
        └── orchestrator.py (pipeline coordination)
  └── menu_renderer.py (terminal menus)
  └── session.py (state management)
```

### Pipeline Core Dependencies
```
orchestrator.py
  ├── spec_analyzer.py → llm_client.py → llm_providers/
  ├── test_generator.py → llm_client.py → prompt_utils.py
  ├── placeholder_orchestrator.py
  │   ├── scraper.py
  │   ├── stateful_scraper.py
  │   ├── journey_scraper.py → form_detector.py, state_tracker.py
  │   ├── placeholder_resolver.py → locator_scorer.py, semantic_matcher.py, intent_matcher.py
  │   ├── semantic_candidate_ranker.py → llm_client.py
  │   ├── page_object_builder.py
  │   └── url_inference.py
  ├── code_postprocessor.py → code_normalizer.py, llm_reasoning_filter.py, code_validator.py
  └── pipeline_writer.py → file_utils.py
```

### Reporting Dependencies
```
pipeline_run_service.py → pytest_output_parser.py
pipeline_report_service.py
  ├── report_builder.py → evidence_loader.py, failure_reporter.py
  └── report_formatters.py
evidence_tracker.py → evidence_serializer.py, screenshot_capture.py
```

---

## Data Models — The Shared Language

These are the core data structures that flow through the pipeline. Understanding them is key to understanding how the system works.

### `TestCondition` (from `spec_analyzer.py`)
```python
class TestCondition:
    id: str           # "AC01", "AC02", etc.
    text: str         # The acceptance criterion text
    intent: str       # "happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"
    source_ref: str   # Reference to the original spec line
```

### `TestJourney` (from `pipeline_models.py`)
```python
class TestJourney:
    name: str                    # "test_01_add_item_to_cart"
    steps: list[TestStep]        # Individual steps in the journey
    page_requirements: list[PageRequirement]  # Pages that need scraping
    def placeholders(self) -> list[PlaceholderUse]  # All placeholders in this journey
```

### `PlaceholderUse` (from `pipeline_models.py`)
```python
class PlaceholderUse:
    action: str       # "GOTO", "CLICK", "FILL", "ASSERT"
    description: str  # "checkout button", "email field"
    line_number: int  # Where in the skeleton code
```

### `ScrapedPage` (from `pipeline_models.py`)
```python
class ScrapedPage:
    url: str
    elements: list[dict]  # Each dict has: selector, text, role, tag, attributes
    metadata: dict        # Page title, timestamp, etc.
```

---

## Learning Phases

### Phase 0 — Setup and Orientation

**Goal:** Get the project running and know where things are.

**Checklist:**
- [ ] Read `README.md` — what the project does at a high level
- [ ] Read `docs/ARCHITECTURE.md` — module responsibilities and dependency graph
- [ ] Read `AGENTS.md` — project rules, constraints, and conventions
- [ ] Read `BACKLOG.md` — decision history and bug tracking
- [ ] Run `uv sync` — install dependencies
- [ ] Activate the virtual environment (`.venv\Scripts\activate` on Windows)
- [ ] Run `playwright install chromium` — install browser
- [ ] Confirm `.env` exists with `OLLAMA_TIMEOUT=300`
- [ ] Run `pytest -v` — verify all tests pass
- [ ] Run `bash launch_ui.sh` — start the Streamlit UI once
- [ ] Write a one-paragraph summary: "What does this project do, who is it for, what problem does it solve?"

**Key files to locate:**
- Entry points: `streamlit_app.py`, `cli/main.py`
- Pipeline brain: `src/orchestrator.py`
- Data models: `src/pipeline_models.py`
- Output: `generated_tests/`
- Tests: `tests/`

---

### Phase 1 — Python and Tooling Foundations

**Goal:** Understand the language features and tooling this repo depends on.

**Topics:**
- Python type hints (enforced by `mypy`)
- Dataclasses (`dataclass`, `field`)
- Async/await (used in pipeline, NOT in generated tests)
- Virtual environments and `uv` package manager
- `pytest` test structure and fixtures
- `ruff` linting and formatting
- `mypy` type checking

**Checklist:**
- [ ] Read `pyproject.toml` — understand dependencies and tool configuration
- [ ] Read `.pre-commit-config.yaml` — understand quality hooks
- [ ] Read `pytest.ini` — understand `testpaths = tests` (NOT `generated_tests`)
- [ ] Run `ruff check src/` — verify linting passes
- [ ] Run `mypy src/` — verify type checking passes
- [ ] Open 3 test files in `tests/` and match them to their source modules
- [ ] Explain the difference between `ruff` (linting), `mypy` (types), `pytest` (testing)
- [ ] Understand why `uv` is used instead of `pip`

**Exercises:**
- [ ] Pick one small module (e.g., `src/file_utils.py`) and explain every function
- [ ] Trace one import chain from `streamlit_app.py` → `ui_pipeline.py` → `orchestrator.py`
- [ ] Explain why testable logic lives in `src/`, not `streamlit_app.py`

---

### Phase 2 — Playwright and Pytest Foundations

**Goal:** Understand the kind of tests this project generates.

**Topics:**
- Playwright sync API for Python (NOT async)
- `pytest` test structure with `page` fixture
- Locator patterns: `get_by_role()`, `get_by_label()`, `locator()`, `text()`
- Assertions: `expect().to_be_visible()`, `expect().to_have_text()`
- Why this project forbids `async def test_` in generated output

**Checklist:**
- [ ] Read `generated_tests/conftest.py` — understand the `page` fixture and `EvidenceTracker` fixture
- [ ] Read 2-3 generated test files in `generated_tests/`
- [ ] Compare generated tests to the rules in `AGENTS.md` §2
- [ ] Understand the `EvidenceTracker` wrapper pattern (generated tests call `tracker.click()` not `page.click()`)

**Exercises:**
- [ ] Hand-write a simple Playwright pytest sync test against any page
- [ ] Explain why `data-testid` locators are more reliable than text locators
- [ ] Explain why "real selectors from the DOM" matter more than LLM-guessed selectors

---

### Phase 3 — Understand the Pipeline End-to-End

**Goal:** Understand the full pipeline from user story to generated test.

**Recommended reading order:**
1. `src/pipeline_models.py` — data structures
2. `src/orchestrator.py` — pipeline coordination
3. `src/spec_analyzer.py` — story analysis
4. `src/test_generator.py` — skeleton generation
5. `src/skeleton_parser.py` — parsing skeletons
6. `src/scraper.py` — DOM scraping
7. `src/placeholder_resolver.py` — placeholder matching
8. `src/placeholder_orchestrator.py` — resolution coordination
9. `src/page_object_builder.py` — POM generation
10. `src/pipeline_writer.py` — file output

**Understanding Tasks:**
- [ ] Identify where raw user story text first enters the system (`streamlit_app.py` → `ui_pipeline.py` → `orchestrator.py`)
- [ ] Identify where acceptance criteria become structured data (`spec_analyzer.py`)
- [ ] Identify where the LLM is called (`llm_client.py`, from `test_generator.py` and `spec_analyzer.py`)
- [ ] Identify where placeholders are created (`test_generator.py` → LLM output)
- [ ] Identify where placeholders are resolved (`placeholder_orchestrator.py` → `placeholder_resolver.py`)
- [ ] Identify where page objects are created (`page_object_builder.py`)
- [ ] Identify where test files are written (`pipeline_writer.py`)
- [ ] Identify where run results are parsed (`pytest_output_parser.py`)
- [ ] Identify where reports are built (`report_builder.py` → `report_formatters.py`)

**Exercises:**
- [ ] Draw the pipeline from memory (5 phases: Analysis → Skeleton → Scrape → Resolve → Output)
- [ ] Trace one story through the full system: input → `TestCondition[]` → skeleton → scraped pages → resolved code → `.py` file
- [ ] Write a plain-English explanation of the "skeleton-first" pipeline
- [ ] Explain why selector data is NOT injected into LLM prompts (prevents hallucination)

---

### Phase 4 — UI, CLI, Reporting, and CI/CD

**Goal:** Understand how the project is operated and validated.

**UI and CLI:**
- [ ] Read `streamlit_app.py` — understand the UI flow
- [ ] Read `src/ui_pipeline.py` — business logic extracted from UI
- [ ] Read `src/ui_renderers.py` — rendering helpers extracted from UI
- [ ] Read `cli/main.py` — CLI entry point
- [ ] Read `cli/pipeline_runner.py` — CLI pipeline execution
- [ ] Explain how Streamlit reruns affect state handling (`st.session_state`)
- [ ] Explain why `ui_pipeline.py` exists (enables testing outside Streamlit context)

**Reporting and Evidence:**
- [ ] Read `src/evidence_tracker.py` — runtime diagnostics capture
- [ ] Read `src/pytest_output_parser.py` — pytest output parsing
- [ ] Read `src/pipeline_report_service.py` — report aggregation
- [ ] Read `src/report_builder.py` — report dictionary building
- [ ] Read `src/report_formatters.py` — 3-format report rendering
- [ ] Read `src/evidence_loader.py` — loading evidence from test packages
- [ ] Read `src/failure_reporter.py` — failure diagnosis

**CI/CD and Quality:**
- [ ] Read `.github/workflows/ci.yml` — CI pipeline
- [ ] Read `pyproject.toml` again with CI in mind
- [ ] Explain what happens on a pull request (ruff → mypy → pytest)
- [ ] Explain why CI needs linting + typing + testing, not just testing

---

### Phase 5 — Explain the Project Clearly

**Goal:** Turn understanding into clear communication.

**Exercises:**
- [ ] Write a 10-sentence summary for a non-technical person
- [ ] Write a 10-sentence summary for a developer
- [ ] Explain the pipeline aloud as if teaching a teammate

**Self-test questions:**
- [ ] "Why does this project need both scraping AND an LLM?"
  - Answer: LLM understands natural language and generates test structure. Scraping provides real DOM data. Neither alone produces reliable tests.
- [ ] "Why not ask the LLM to generate final selectors directly?"
  - Answer: LLMs hallucinate selectors. They generate plausible-looking CSS/XPath that doesn't match the actual DOM. The skeleton-first approach separates reasoning (LLM) from data (scraper).
- [ ] "Why are generated tests separated from the tool's own test suite?"
  - Answer: `pytest.ini` sets `testpaths = tests`. Generated tests in `generated_tests/` are only run explicitly. Mixing them would cause the tool's tests to run against random websites.
- [ ] "Why both a Streamlit app AND a CLI?"
  - Answer: Streamlit for interactive use with visual feedback. CLI for CI/CD integration and automated workflows.
- [ ] "Why are `ruff`, `mypy`, and `pytest` all important?"
  - Answer: `ruff` catches style and common bugs. `mypy` catches type errors. `pytest` catches logic errors. Each catches different classes of problems.

---

### Phase 6 — Build Smaller Versions from Scratch

**Goal:** Prove understanding by rebuilding key ideas in simpler form.

**Mini Project 1 — Static Test Writer**
- [ ] Build a script that takes a text prompt and writes a fixed pytest file
- [ ] No scraping, no LLM, no UI — just template substitution

**Mini Project 2 — Story to Skeleton**
- [ ] Take a small user story and generate test skeleton functions
- [ ] Use placeholder text instead of real selectors
- [ ] Mirrors the real project's Phase 2

**Mini Project 3 — Placeholder Resolver**
- [ ] Create a fake set of scraped elements
- [ ] Resolve placeholders against that fake element data
- [ ] Mirrors the real project's Phase 4

**Mini Project 4 — Simple CLI**
- [ ] Add a command-line wrapper for the mini pipeline
- [ ] Accept input story text, output a test file

**Mini Project 5 — Simple UI**
- [ ] Add a tiny Streamlit UI
- [ ] Keep logic outside the UI file

**Mini Project 6 — Reporting**
- [ ] Parse test output or fake a result model
- [ ] Show pass/fail information in a simple report

---

### Phase 7 — Rewrite Readiness

**Goal:** Prepare for a full rewrite without jumping in blindly.

**Analysis Checklist:**
- [ ] List the modules you would keep as-is (e.g., `pipeline_models.py`, `scraper.py`)
- [ ] List the modules you would simplify (e.g., `orchestrator.py` — too many responsibilities)
- [ ] List the modules you would redesign (e.g., `placeholder_orchestrator.py` — complex resolution logic)
- [ ] Identify technical debt, duplication, and confusing boundaries
- [ ] Identify what the absolute minimum viable rewrite would include
- [ ] Identify what should stay out of version 1 of a rewrite

**Final Readiness Questions:**
- [ ] Can I explain the current architecture without notes?
- [ ] Can I build a smaller clone from scratch?
- [ ] Can I say what I would change and why?
- [ ] Can I rewrite one slice safely without breaking the rest?

---

## Progress Scorecard

### Level 1 — Orientation
- [ ] I know what the project does
- [ ] I can run it locally
- [ ] I know where the major files are

### Level 2 — Code Reading
- [ ] I can trace behavior across multiple modules
- [ ] I understand the role of `orchestrator.py`
- [ ] I understand the skeleton-first pipeline (2 phases)

### Level 3 — Testing and Tooling
- [ ] I can write Playwright pytest sync tests
- [ ] I can run and interpret `ruff`, `mypy`, and `pytest`
- [ ] I understand why CI/CD has 3 quality gates

### Level 4 — Ownership
- [ ] I can explain the system clearly
- [ ] I can make safe changes to it
- [ ] I can debug issues by following the pipeline

### Level 5 — Rewrite Readiness
- [ ] I can build a smaller version of the project myself
- [ ] I can propose a rewrite plan with clear phases
- [ ] I would be comfortable rewriting the project slice by slice

---

*Last updated: 2026-05-11*
*Cross-reference: `docs/ARCHITECTURE.md` (full module table + dependency graph), `AGENTS.md` (rules), `BACKLOG.md` (decisions and history)*