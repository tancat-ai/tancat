# Source Module Documentation

This directory contains per-module documentation for all 66 source files in `src/`.

## How to Read These Docs

Each `<module_name>.py.md` file covers:
- **Purpose** — what the module does in one sentence
- **Dependencies** — other modules it imports
- **Module Constants** — top-level enums, Literal types, defaults
- **Public API** — classes, methods, and standalone functions with signatures
- **Design Notes** — patterns, gotchas, and architectural decisions
- **Related Files** — modules that depend on or are depended upon

## Module Index (66 files)

### Pipeline Core (5)
| Doc | Module |
|-----|--------|
| [orchestrator.py.md](./orchestrator.py.md) | Core pipeline orchestration — skeleton-first test generation |
| [pipeline_models.py.md](./pipeline_models.py.md) | Data models for pipeline (JourneyPage, Skeleton, etc.) |
| [pipeline_writer.py.md](./pipeline_writer.py.md) | Writes generated test files to disk |
| [pipeline_run_service.py.md](./pipeline_run_service.py.md) | Pipeline execution service |
| [pipeline_report_service.py.md](./pipeline_report_service.py.md) | Pipeline report generation service |

### Scraper Chain (6)
| Doc | Module |
|-----|--------|
| [scraper.py.md](./scraper.py.md) | DOM metadata scraper — extracts locatable elements |
| [journey_scraper.py.md](./journey_scraper.py.md) | Journey-aware stateful scraping across page navigations |
| [stateful_scraper.py.md](./stateful_scraper.py.md) | State-aware scraping fallback for placeholder orchestrator |
| [state_tracker.py.md](./state_tracker.py.md) | DOM state tracking across page transitions |
| [form_detector.py.md](./form_detector.py.md) | Form detection and selector constants |
| [page_context_tracker.py.md](./page_context_tracker.py.md) | Page-level context tracking for scraper |

### Placeholder System (9)
| Doc | Module |
|-----|--------|
| [placeholder_orchestrator.py.md](./placeholder_orchestrator.py.md) | Per-page placeholder resolution orchestration |
| [placeholder_resolver.py.md](./placeholder_resolver.py.md) | Resolves LLM-generated placeholders to real locators |
| [placeholder_scorers.py.md](./placeholder_scorers.py.md) | Composite scoring engine for placeholder candidates |
| [intent_matcher.py.md](./intent_matcher.py.md) | Intent classification for placeholders |
| [semantic_candidate_ranker.py.md](./semantic_candidate_ranker.py.md) | Context candidate prioritization |
| [semantic_matcher.py.md](./semantic_matcher.py.md) | Token-based semantic similarity |
| [url_inference.py.md](./url_inference.py.md) | URL inference from page context |
| [url_resolver.py.md](./url_resolver.py.md) | Resolves URLs for navigation placeholders |
| [url_utils.py.md](./url_utils.py.md) | URL normalization and comparison utilities |

### Code Pipeline (6)
| Doc | Module |
|-----|--------|
| [test_generator.py.md](./test_generator.py.md) | Working test generation pipeline (PROTECTED) |
| [skeleton_parser.py.md](./skeleton_parser.py.md) | Parses basic skeleton structures from LLM output |
| [code_normalizer.py.md](./code_normalizer.py.md) | Code normalization transforms |
| [code_postprocessor.py.md](./code_postprocessor.py.md) | Post-processing for generated code |
| [code_validator.py.md](./code_validator.py.md) | Validates generated test code structure |
| [page_object_builder.py.md](./page_object_builder.py.md) | Page Object Model generation |

### Evidence / Reports (9)
| Doc | Module |
|-----|--------|
| [evidence_tracker.py.md](./evidence_tracker.py.md) | Captures runtime diagnostics and evidence |
| [evidence_loader.py.md](./evidence_loader.py.md) | Loads evidence JSON from test packages |
| [evidence_serializer.py.md](./evidence_serializer.py.md) | Evidence JSON serialization |
| [evidence_report.py.md](./evidence_report.py.md) | Evidence report generation |
| [failure_classifier.py.md](./failure_classifier.py.md) | Classifies test failure types |
| [failure_reporter.py.md](./failure_reporter.py.md) | Generates failure diagnostic reports |
| [report_builder.py.md](./report_builder.py.md) | Builds report dictionaries merging evidence data |
| [report_formatters.py.md](./report_formatters.py.md) | Renders reports (local MD, Jira MD, HTML) |
| [report_utils.py.md](./report_utils.py.md) | Shared report formatting utilities |

### Locator System (4)
| Doc | Module |
|-----|--------|
| [locator_builder.py.md](./locator_builder.py.md) | Builds Playwright locator strings |
| [locator_fallback.py.md](./locator_fallback.py.md) | Runtime locator fallback chain |
| [locator_repair.py.md](./locator_repair.py.md) | Repairs broken locators after test failures |
| [locator_scorer.py.md](./locator_scorer.py.md) | Scores locators by reliability ranking |

### LLM (4)
| Doc | Module |
|-----|--------|
| [llm_client.py.md](./llm_client.py.md) | Multi-provider LLM client (Ollama, LM Studio, OpenAI) |
| [llm_errors.py.md](./llm_errors.py.md) | LLM-specific error types and handling |
| [llm_reasoning_filter.py.md](./llm_reasoning_filter.py.md) | LLM reasoning text detection and stripping |
| [prompt_utils.py.md](./prompt_utils.py.md) | LLM prompt construction utilities |

### UI (2)
| Doc | Module |
|-----|--------|
| [ui_pipeline.py.md](./ui_pipeline.py.md) | Pipeline execution for Streamlit UI |
| [ui_renderers.py.md](./ui_renderers.py.md) | Streamlit rendering helpers |

### Test Planning (3)
| Doc | Module |
|-----|--------|
| [test_plan.py.md](./test_plan.py.md) | Test plan data structures and generation |
| [spec_analyzer.py.md](./spec_analyzer.py.md) | Derives test conditions from feature specifications |
| [user_story_parser.py.md](./user_story_parser.py.md) | Parses Gherkin-style user stories |

### Utilities (18)
| Doc | Module |
|-----|--------|
| [__init__.py.md](./__init__.py.md) | Package initialization |
| [accessibility_enricher.py.md](./accessibility_enricher.py.md) | Adds ARIA attributes to scraped elements |
| [analyzer.py.md](./analyzer.py.md) | General-purpose code and test analysis |
| [browser_utils.py.md](./browser_utils.py.md) | Browser interaction helpers |
| [config.py.md](./config.py.md) | Configuration loading and defaults |
| [coverage_utils.py.md](./coverage_utils.py.md) | Test coverage analysis utilities |
| [element_enricher.py.md](./element_enricher.py.md) | Enriches scraped elements with additional metadata |
| [failure_classifier.py.md](./failure_classifier.py.md) | Test failure classification |
| [file_utils.py.md](./file_utils.py.md) | File I/O helpers (save, rename, normalize) |
| [form_login_utils.py.md](./form_login_utils.py.md) | Form login detection and handling |
| [gantt_utils.py.md](./gantt_utils.py.md) | Gantt chart generation for test execution |
| [heatmap_utils.py.md](./heatmap_utils.py.md) | Heatmap visualization for test coverage |
| [hover_click_utils.py.md](./hover_click_utils.py.md) | Hover-and-click interaction utilities |
| [journey_auth_detector.py.md](./journey_auth_detector.py.md) | Detects authentication pages in journeys |
| [prerequisite_injector.py.md](./prerequisite_injector.py.md) | Injects prerequisite setup into test code |
| [pytest_output_parser.py.md](./pytest_output_parser.py.md) | Parses pytest CLI output for results |
| [run_utils.py.md](./run_utils.py.md) | Test execution runtime utilities |
| [screenshot_capture.py.md](./screenshot_capture.py.md) | Screenshot capture utilities |
| [skeleton_validator.py.md](./skeleton_validator.py.md) | Validates skeleton structure before resolution |
| [vision_enricher.py.md](./vision_enricher.py.md) | Vision-based element enrichment |

### LLM Providers
| Doc | Module |
|-----|--------|
| [llm_providers/__init__.py.md](./llm_providers/__init__.py.md) | Provider package initialization |

## Generation Info
- **Generated:** 2026-05-30
- **Total modules:** 66
- **Status:** Complete