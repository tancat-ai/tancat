# tancat-ai/tancat — Documentation Index

> Auto-generated documentation sweep — 135 source files across `src/`, `cli/`, `scripts/`

## Global Architecture

The project generates Playwright Python test scripts from user stories using a local LLM. It has two entry points:

### Streamlit UI (`streamlit_app.py`)

Primary interface. Uses modular UI components from `src/ui/`:

| Module | Role |
|--------|------|
| `src/ui/ui_requirements.py` | Requirements input (paste/upload/baseline) |
| `src/ui/ui_sidebar.py` | LLM provider and POM mode configuration |
| `src/ui/ui_journey.py` | Credential profiles and journey step builder |
| `src/ui/ui_results.py` | Results display and test run buttons |
| `src/ui/ui_run_results.py` | Run results with failure classification and locator repair |
| `src/ui/ui_evidence.py` | Evidence viewer (screenshots, Gantt, heatmaps, run history) |
| `src/ui/ui_downloads.py` | Report download buttons |
| `src/ui/ui_saved_packages.py` | Saved package loader and re-run (AI-026) |
| `src/ui/shared.py` | Session state key whitelisting and report storage helpers |

### CLI (`src/cli/main.py`)

Menu-driven terminal interface with retro CHOICE-style rendering:

| Module | Role |
|--------|------|
| `src/cli/main.py` | Slim orchestrator — menu loop and routing |
| `src/cli/session.py` | Session state dataclass with factory |
| `src/cli/menu_renderer.py` | Retro menu rendering and all input prompts |
| `src/cli/retro_ui.py` | CHOICE-style box-drawing and colour primitives |
| `src/cli/color.py` | ANSI colour helpers (standard + phosphor greens) |
| `src/cli/terminal_adapter.py` | Cross-platform TTY/PTY key reading |
| `src/cli/testing_terminal.py` | Queue-based terminal for headless tests |
| `src/cli/pipeline_runner.py` | Pipeline execution, test running, reports |
| `src/cli/input_parser.py` | Multi-format input parsing (Jira, Gherkin, bullets, plain text) |
| `src/cli/evidence_generator.py` | Screenshot capture and evidence collection |
| `src/cli/report_generator.py` | Jira/Confluence/Markdown report generation |
| `src/cli/test_case_orchestrator.py` | Legacy orchestration pipeline |
| `src/cli/run_results_display.py` | Structured ASCII run results for terminals |
| `src/cli/config.py` | Backwards-compatible config re-exports |
| `src/cli/__init__.py` | UTF-8 encoding fix for Windows Git Bash |

### Core Pipeline (`src/`)

| Layer | Modules | Description |
|-------|---------|-------------|
| **Input** | `user_story_parser.py`, `skeleton_parser.py` | Parse user stories into structured requirements |
| **LLM** | `llm_client.py`, `llm_providers/`, `provider_config.py`, `llm_errors.py`, `llm_reasoning_filter.py` | LLM interaction, provider abstraction, error handling |
| **Prompts** | `prompt_utils.py`, `test_generator.py` | Prompt construction and test generation |
| **Scaffolding** | `skeleton_validator.py`, `code_normalizer.py`, `code_postprocessor.py`, `code_validator.py` | Code quality assurance |
| **Agents (Phase 1c)** | `src/agents/state.py`, `src/agents/planner.py`, `src/agents/generator.py`, `src/agents/validator.py`, `src/agents/graph.py` | LangGraph multi-agent skeleton generation |
| **DOM Scraping** | `scraper.py`, `stateful_scraper.py`, `journey_scraper.py`, `journey_models.py`, `journey_executor.py`, `journey_auth_detector.py`, `page_context_tracker.py` | Page scraping and context capture |
| **Placeholder Resolution** | `placeholder_resolver.py`, `placeholder_orchestrator.py`, `placeholder_scorers.py`, `semantic_matcher.py`, `semantic_candidate_ranker.py`, `intent_matcher.py`, `element_matcher.py`, `element_enricher.py`, `accessibility_enricher.py`, `vision_enricher.py`, `hover_click_utils.py` | Resolving `{{ACTION:description}}` placeholders using scraped DOM |
| **Locators** | `locator_builder.py`, `locator_fallback.py`, `locator_repair.py`, `locator_scorer.py`, `url_resolver.py`, `url_inference.py`, `url_utils.py` | Locator generation, repair, and scoring |
| **Page Objects** | `page_object_builder.py` | POM class generation |
| **Analysis** | `analyzer.py`, `spec_analyzer.py`, `form_detector.py`, `form_login_utils.py` | Test case analysis and pattern detection |
| **Pipeline** | `orchestrator.py`, `pipeline_models.py`, `pipeline_writer.py`, `pipeline_artifact_manager.py`, `pipeline_run_service.py`, `pipeline_report_service.py`, `ui_pipeline.py` | Core pipeline orchestration and artifact management |
| **Execution** | `pytest_output_parser.py`, `run_utils.py`, `screenshot_capture.py`, `evidence_tracker.py`, `evidence_serializer.py`, `evidence_loader.py`, `evidence_report.py`, `state_tracker.py` | Test execution and evidence collection |
| **Failure Handling** | `failure_classifier.py`, `failure_reporter.py` | Failure categorisation and diagnostics |
| **Reports** | `report_builder.py`, `report_formatters.py`, `report_utils.py`, `export_service.py` | Report generation and export |
| **Persistence** | `run_result_persistence.py`, `sqlite_persistence.py`, `run_history_chart.py`, `run_history_cli.py` | SQLite-backed run history and charting |
| **Visualisation** | `gantt_utils.py`, `heatmap_utils.py`, `coverage_utils.py`, `run_history_chart.py` | Gantt charts, heatmaps, coverage analysis |
| **Infrastructure** | `config.py`, `file_utils.py`, `storage.py` | Configuration constants, file utilities, workspace-isolated storage |
| **RAG (Phase 3)** | `rag_store.py`, `rag_retriever.py` | Retrieval-augmented resolution — vector store (Milvus Lite) + golden pattern retrieval for scoring bonus |

### Test Plan (`src/test_plan.py`)

Living test plan with sign-off workflow. Conditions derived from acceptance criteria, reviewed by tester, then signed off before generation is unlocked.

### Test Table (`src/test_table.py`)

AI-034 — LLM expansion of plan conditions into concrete test rows (one row per scenario). Tester reviews/edits/confirms rows before one skeleton function per row is generated. Editors in both Streamlit (🧪 Test Table) and CLI ("Expand into Test Rows").

### Tests (`tests/`)

Unit tests for all core modules — validates the tool itself, not the tests it generates.

### Generated Output (`generated_tests/`)

Test packages produced by the tool. Each package contains:
- `package_manifest.json` — Metadata and artifact listing
- `test_xxx.py` — Generated Playwright test files
- `evidence/*.evidence.json` — Sidecar evidence files with screenshots and step traces

## Documentation Coverage

## Phase 6 — Commercialisation (Part 1)

| Module | Role |
|--------|------|
| `src/licensing/license.py` | Offline ed25519 license sign/verify, 7-day grace, vendored public key, `feature_enabled` |
| `src/licensing/tiers.py` | Data-driven free/self-serve/pro/airgap tier table (claims + limits, env-overridable) |
| `src/usage_meter.py` | 30-day runs/exports meter on run_results.sqlite + ledger; free-tier cap + upgrade prompt |
| `src/llm_health.py` | BYO-LLM first-run health probe (reachability → key → model → capability) |
| `src/llm_cache.py` | Disk TTL cache for expensive deterministic LLM calls (resolution ranking) |
| `src/rag_store_lock.py` | Cross-process advisory write lock for the single-writer Milvus RAG store |

| Directory | Files | Status |
|-----------|-------|--------|
| `src/` (root) | 61 | ✅ Complete |
| `src/agents/` | 5 | ✅ Complete |
| `src/cli/` | 15 | ✅ Complete |
| `src/ui/` | 10 | ✅ Complete |
| `src/llm_providers/` | 1 | ✅ Complete |
| `scripts/` (eval + verify_production + archived debug) | 10 | ✅ Complete |
| `cli/` | 4 | ✅ Complete |
| **Total** | **142** | **✅ Complete** |

> Updated 2026-08-03 (document-manager sweep): 12 `src/` docs refreshed for the
> saucedemo checkout cluster fixes (soft-404, stateful routing, dead-page/
> redirect-duplicate filters, navigation-intent fallback, modal-scoped dismissal,
> B-024g field matching); new docs for `scripts/verify_production.py`,
> `cli/evidence_cli.py`, and 4 archived saucedemo debug scripts.

## Sweep Progress

See `markdown_docs/.sweep_progress.json` for per-file completion status.

---

*Generated: 2026-07-08*  
*Updated: 2026-07-23 — Phase 1c LangGraph agents (state, planner, generator, validator, graph)*

*Updated: 2026-09-05 — Phase 6 Part 1 docs added: licensing (license/tiers/__init__), usage_meter, llm_health, llm_cache, rag_store_lock (document-manager sweep per AGENTS.md §10).*
