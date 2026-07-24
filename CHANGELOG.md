# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Semantic scraper (B-032)**: Three-layer hybrid extraction — BS4 (structure) + CDP AX tree (accessible_name) + `page.aria_snapshot(boxes=True)` (placeholder, value, bbox, groups). Enabled by default; `SCRAPER_BACKEND=bs4` to disable.
- `src/aria_parser.py` — Parse Playwright's `aria_snapshot()` YAML output into standard element dicts (33 tests, all ARIA roles).
- `src/element_matcher.py` — Resolver accuracy improvements (B-024/B-025):
  - Pass1 word-ratio relax for short descriptions matching long element text
  - Pass1 heading skip for CLICK actions (headings are display elements, not click targets)
  - Pass1 id/name prefix match for FILL actions (e.g. "overnight" → `id="overnightLocation"`)
  - Pass1 word-boundary check for single-word containment (prevents "year" ⊆ "(years)" false positives)
- `src/placeholder_scorers.py` — Heading penalty (-20) for CLICK on elements without ID + container bonus (+10) for generic/div elements with ID (B-025)
- `scripts/eval/golden_validator.py` — Locator normalization: `#foo` ≡ `[id="foo"]`, `[data-test="bar"]` ≡ `.class[data-test="bar"]` (B-026)
- `docs/specs/FEATURE_SPEC_semantic_scraper.md` — Full design document for the semantic scraper transition
- `CONTEXT.md` — Updated architecture section with three-layer scraping + resolver pipeline
- `README.md` — Added "Semantic Scraper" feature bullet
- `docs/ARCHITECTURE.md` — Updated `PageScraper` description + added `aria_parser.py`

### Changed
- Resolver accuracy: **46.3% → 55.2%** (+8.9pp, RAG off), **53.7% → 64.2%** (+10.5pp, RAG on)
- lv_insurance eval-005: **54.2% → 79.2%** (+25.0pp)
- Static eval harness: **79.1% → 88.1%** (+9.0pp vs baseline)
- `SCRAPER_BACKEND` env var now defaults to ARIA-hybrid; set to `bs4` for old behavior
- **Refactor 2026-07-11 — Journey scraper split:** `journey_scraper.py` (896→617 lines) split into 3 focused modules:
  - `src/journey_enrichment.py` — `capture_element_visibility_sync`, `capture_a11y_snapshot_sync` (deduplicated from `journey_executor.py`)
  - `src/cart_seeding_scraper.py` — `CartSeedingScraper` class (resolved circular import with `journey_scraper.py`)
  - `src/journey_subprocess.py` — `run_journey_subprocess_entry` subprocess entry point
- **Refactor 2026-07-11 — Placeholder orchestrator split:** `placeholder_orchestrator.py` (2,047→862 lines) split into 4 focused modules:
  - `src/role_mapper.py` — `DISPLAY_ROLES`, `_TAG_TO_ROLE`, `is_display_role`, `normalise_element_text`
  - `src/element_matcher.py` — Pass 0–3 matching engine, `ElementMatcher` class, B-020 semantic ASSERT resolution
  - `src/skip_manager.py` — consolidated skip insertion, placeholder line removal
  - `src/pom_helpers.py` — POM artifact generation, imports, instantiation, method calls

### Added
- CI/CD: parallelised quality gates — lint, type-check, sanitizer, and graph-freshness now run concurrently instead of sequentially (~15s saved per push)
- CI/CD: `graph-freshness` gate — warns when `graphify-out/graph.json` commit hash diverges from `HEAD`
- CI/CD: `docs-coverage` gate — warns when `markdown_docs/.sweep_progress.json` has pending files
- README.md: linked interactive call-flow diagram (`graphify-out/callflow.html`)
- README.md: added "Self-Documenting" feature bullet
- CONTRIBUTING.md: added Security section linking to SECURITY.md
- `scripts/maintenance/project_sanitizer.py`: replaced dead `links.csv` orphan audit with knowledge graph freshness check (reads `graphify-out/graph.json` `built_at_commit` vs `git HEAD`)
- `normalize_whitespace()` in `src/code_normalizer.py` — converts tabs to spaces and normalizes line endings (\r\n → \n) before other normalization transforms, preventing SyntaxError when LLMs emit tab-indented code
- `tests/test_code_normalizer.py` — 9 unit tests for `normalize_whitespace`, pipeline integration, and `ensure_test_navigation`
- AI-027 Session 2 screenshot capture during scraping: `ScrapeResult`, in-memory screenshot bytes, and interactive element bounding boxes for later vision enrichment.
- AI-027 Session 3 vision enrichment service: element crop, vision LLM call path, structured response parsing, and scraper enrichment bridge.
- **Refactor 2026-05-10 (Parts 1-7)** — Modular extraction reducing `streamlit_app.py` from 918 → 362 lines (60% reduction) per REFACTOR_PLAN_2026-05-10.md
  - `src/ui_pipeline.py` — Pipeline execution helpers extracted from `streamlit_app.py` (business logic, no rendering)
  - `src/ui_renderers.py` — Streamlit rendering helpers extracted from `streamlit_app.py` (pure UI, no business logic)
  - `src/evidence_serializer.py` — Evidence JSON serialization extracted from `evidence_tracker.py`
  - `src/screenshot_capture.py` — Screenshot capture utilities extracted from `evidence_tracker.py`
  - `src/state_tracker.py` — DOM state tracking extracted from `journey_scraper.py`
  - `src/form_detector.py` — Form detection and selector constants extracted from `journey_scraper.py`
  - `src/semantic_matcher.py` — Token-based semantic similarity extracted from `placeholder_resolver.py`
  - `src/intent_matcher.py` — Intent-based element filtering extracted from `placeholder_resolver.py`
  - `src/code_normalizer.py` — Code normalization transforms extracted from `code_postprocessor.py`
  - `src/llm_reasoning_filter.py` — LLM reasoning text detection extracted from `code_postprocessor.py`
  - `src/url_inference.py` — URL transition inference extracted from `placeholder_orchestrator.py`
- `CONTRIBUTING.md` — contributor guide with dev setup and coding standards
- `SECURITY.md` — private vulnerability reporting policy
- `CHANGELOG.md` — this file
- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1
- GitHub issue templates for bug reports and feature requests
- `src/analyzer.py` — CLI analysis module (replaces `cli/story_analyzer.py`)
- `src/config.py` — `AnalysisMode` and `ReportFormat` enums for CLI
- `src/code_postprocessor.py` — code string transformation helpers (extracted from `orchestrator.py`)
- `src/url_utils.py` — pure URL manipulation helpers (extracted from `orchestrator.py`)
- `src/report_builder.py` — report data preparation (extracted from `report_utils.py`)
- `src/report_formatters.py` — standard report renderers (extracted from `report_utils.py`)
- `src/evidence_report.py` — annotated screenshot/heatmap/journey generators (extracted from `report_utils.py`)

### Changed
- `cli/story_analyzer.py` → `cli/analyzer.py` — renamed for clarity
- `src/orchestrator.py` — extracted URL helpers to `src/url_utils.py` and code postprocessors to `src/code_postprocessor.py`
- `src/report_utils.py` — replaced with backwards-compatible re-export shim; logic moved to `report_builder.py`, `report_formatters.py`, and `evidence_report.py`

### Removed
- `cli/story_analyzer.py` — replaced by `cli/analyzer.py` + `src/config.py`
- `src/page_context_scraper.py` — deleted (deprecated, caused selector hallucination)
- Deprecated test files: `tests/src/`, `tests/example_test.py`, `tests/uat_pipeline_test.py`

### Fixed
- **Tab indentation SyntaxError** — LLMs emitting tab-indented code now normalized to spaces via `normalize_whitespace()` before `ensure_test_navigation()` injects 4-space indented navigation lines, preventing "unindent does not match" SyntaxErrors
- Pass 1 text match added to `PlaceholderOrchestrator._find_best_element_for_current_page()` — resolves nav links by element text before scoring, eliminating Products link tie bug
- Pass 1 text match added to `JourneyScraper._find_selector_for_step()` — journey discovery now navigates to correct pages (e.g. /products not /brand_products/*)  
- `resolve_all()` diagnostic replaced with regex scan of final_code — eliminates 25+ LLM timeout calls post-pipeline (runtime: 1263s → 165s)
- `src/journey_scraper_clean.py` dead file deleted (0% coverage, not imported)
- Punctuation stripping added to Pass 1 description normalisation — handles LLM-generated tokens like `'Products' link` with embedded quotes
- UAT saucedemo: 5/6 tests passing against real site with browser automation
- mypy `import-untyped` for pandas via `pandas-stubs` dev dependency
- mypy `import-untyped` for plotly via per-module override in `pyproject.toml`
- pre-commit hook failures from variable shadowing in `generate_3d_map.py` via mypy override
- Fix skeleton prompt generation to inject the exact expected test count into the LLM prompt.
- Improve placeholder postprocessing to unwrap `evidence_tracker.xxx({{...}})` wrappers with optional whitespace.
- Placeholder resolution now collects candidates across ALL scraped pages before selecting the global best match, preventing low-quality matches from early pages when a much better match exists on a later page (e.g., finding a cart page element for "username input" instead of the login page element). Added `tests/test_global_best_resolution.py` with 5 regression tests.

---

## [0.3.0] — 2026-04-10

### Added
- Multi-provider LLM support (`src/llm_providers/`) — Ollama, OpenAI, Anthropic, OpenRouter
- Pipeline architecture (`src/orchestrator.py`, `src/pipeline_models.py`, `src/pipeline_writer.py`)
- Anchor link extraction in page context scraper
- `src/coverage_utils.py` — coverage display-mapping logic extracted from `streamlit_app.py`
- `src/run_utils.py` — test command construction with re-run-failed-only support
- `src/semantic_candidate_ranker.py` — context candidate prioritisation
- `src/placeholder_resolver.py` — resolves LLM-generated placeholders in test output
- `src/skeleton_parser.py` — handles skeleton test scripts
- Credential profile selection persistence in Streamlit session state

### Fixed
- Migration from `pip` to `uv` as the sole package manager
- Coverage map now correctly reflects run outcomes (B-008)
- Structured failure tracking (`failed_pages`) with backward compatibility

---

## [0.2.0] — 2026-03-29

### Added
- `src/user_story_parser.py` — parses Gherkin, Jira AC bullets, numbered, and free-form stories
- `src/code_validator.py` — `ast.parse()` validation guard before saving generated tests (B-009)
- Multi-page scraping Phase A — `scrape_multiple_pages()`, `MultiPageContext`, `ScraperState`
- `.env.example` updated with correct `OLLAMA_TIMEOUT=300` default

### Fixed
- Parser banner incorrect on mixed pass/fail runs (B-006) — added 2 regression tests
- Duplicate error panels in run results UI (B-007)
- `src/pytest_output_parser.py` missing from repo (BREAK-1)
- Session state wipe blanking run results panel (BREAK-2)

---

## [0.1.0] — 2026-03-13

### Added
- Streamlit UI (`streamlit_app.py`) as primary entry point
- `src/page_context_scraper.py` — subprocess-based Playwright DOM scraper
- `src/pytest_output_parser.py` — parses pytest stdout into structured `RunResult`
- `src/report_utils.py` — generates local, Jira, and standalone HTML evidence bundles
- `src/file_utils.py` — test file save, rename, and newline normalisation helpers
- `src/llm_client.py` — Ollama API client with configurable timeout
- `src/test_generator.py` — core test generation pipeline
- Three report download formats: `local.md`, `jira.md`, `standalone.html`
- Ollama model selector in sidebar (live fetch via `ollama list`)
- Auto-save generated tests to `generated_tests/`
- Coverage tab with number-based test-to-criterion matching
- Run Now flow with pytest subprocess execution
- `pytest.ini` with `testpaths = tests` (generated tests excluded from default run)
- `launch_ui.sh` and `launch_dev.sh` startup scripts

### Fixed
- LLM generates async tests instead of pytest sync format (B-001)
- LLM output occasionally has all imports on one line (B-002) — `normalise_code_newlines()`
- Generated tests not saved automatically (B-003)
- Mock server startup incorrectly bundled into general launch script (B-005)

---

[Unreleased]: https://github.com/lacattano/AI-Playwright-Test-Generator/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/lacattano/AI-Playwright-Test-Generator/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/lacattano/AI-Playwright-Test-Generator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lacattano/AI-Playwright-Test-Generator/releases/tag/v0.1.0
