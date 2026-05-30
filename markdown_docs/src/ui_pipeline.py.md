# `src/ui_pipeline.py`

## Purpose
Pipeline execution helpers for Streamlit UI — business logic only (no rendering). Extracted from streamlit_app for testability.

## Metadata
- **Lines:** 341
- **Imports:** pathlib, src.code_validator, src.journey_scraper, src.llm_client, src.orchestrator, src.pipeline_report_service, src.pipeline_run_service, src.pipeline_writer, src.pytest_output_parser, src.spec_analyzer, src.test_generator, src.test_plan

## Classes
- **`PipelineSessionState`**: Thin wrapper around Streamlit session state for testability

## Functions
| Function | Description |
|----------|-------------|
| `_get_provider_defaults(provider)` | Returns (base_url, model) defaults per provider |
| `parse_requirements_text(raw_text)` | Parses raw text into (user_story, criteria) |
| `parse_target_urls(base_url, urls_input)` | Deduplicates and orders target URLs |
| `build_test_plan(...)` | Analyzes requirements, returns TestPlan for review |
| `plan_rows_from_plan(plan)` | Returns editable table rows from plan |
| `run_pipeline(...)` | Async: executes full skeleton-first pipeline |
| `execute_saved_test(saved_path)` | Runs saved test file, returns result |
| `execute_failed_only(saved_path, previous_run)` | Re-runs only failed tests |
| `build_report_bundle(...)` | Builds report artifacts for pipeline run |
| `store_report_bundle(bundle, session)` | Persists reports in session state |
| `safe_read_text(path)` | Reads text file safely |
| `find_evidence_sidecars(base_dir)` | Finds all evidence JSON sidecars |
| `find_all_evidence_dirs(base_dir)` | Returns all evidence directories |
| `find_sidecar_for_test(base_dir, test_name)` | Finds sidecar by test name |

## Dependencies
- `src.code_validator`, `src.orchestrator`, `src.spec_analyzer`, `src.test_generator`, `src.test_plan`, `src.pipeline_*` services