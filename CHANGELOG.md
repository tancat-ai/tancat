# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
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
- mypy `import-untyped` for pandas via `pandas-stubs` dev dependency
- mypy `import-untyped` for plotly via per-module override in `pyproject.toml`
- pre-commit hook failures from variable shadowing in `generate_3d_map.py` via mypy override

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
