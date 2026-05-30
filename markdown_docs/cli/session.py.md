# cli/session.py

## Purpose

Defines the mutable session state for the interactive CLI flow.
Stores pipeline artifacts, LLM configuration, URLs, authentication, journey steps, reports, and requirements.

## Key dataclass

### `Session`
- Fields include:
  - `pipeline_results`, `pipeline_skeleton`, `pipeline_saved_path`, `pipeline_manifest_path`, `pipeline_error`
  - `pipeline_unresolved`, `pipeline_scraped_pages`, `pipeline_urls`, `pipeline_criteria`, `pipeline_conditions`
  - `pipeline_run_result`, `pipeline_run_output`, `pipeline_run_command`, `pipeline_run_return_code`
  - `pipeline_local_report`, `pipeline_jira_report`, `pipeline_html_report`, `pipeline_local_report_path`, `pipeline_jira_report_path`, `pipeline_html_report_path`
  - `test_plan`, `plan_confirmed`
  - `provider`, `provider_base_url`, `model_name`
  - `starting_url`, `additional_urls`, `consent_mode`, `raw_requirements`
  - `credential_profile`, `journey_steps`

## Factory functions

- `_env_or_default(key: str, default: str) -> str`
- `_session_defaults() -> dict[str, str]`
- `create_session() -> Session`
  - Initializes a `Session` with environment-backed defaults for LLM provider, base URL, and model.

## Notes

- Uses `src.journey_scraper.CredentialProfile` and `JourneyStep` for optional authentication and journey configuration.
- Uses `src.spec_analyzer.TestCondition` and `src.test_plan.TestPlan` for living test plan support.
- Uses `src.pytest_output_parser.RunResult` for pytest execution results.
