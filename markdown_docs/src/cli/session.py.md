# `src/cli/session.py` — CLI Session State Management

## Purpose

Holds all mutable state across interactive prompts so the main menu loop and pipeline handlers share a single, well-typed context.

## Data Class: `Session`

### Pipeline Artifacts

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_results` | `str \| None` | Generated test code |
| `pipeline_skeleton` | `str` | Pre-resolution skeleton |
| `pipeline_saved_path` | `str \| Path` | Output directory path |
| `pipeline_manifest_path` | `str` | Package manifest path |
| `pipeline_error` | `str` | Last error message |
| `pipeline_unresolved` | `list[str]` | Unresolved placeholders |
| `pipeline_scraped_pages` | `dict[str, list[dict]]` | Scraped DOM per URL |
| `pipeline_urls` | `list[str]` | URLs that were scraped |
| `pipeline_criteria` | `str` | Acceptance criteria text |
| `pipeline_conditions` | `list[TestCondition]` | Derived test conditions |
| `pipeline_run_result` | `RunResult \| None` | Latest pytest results |
| `pipeline_run_output` | `str` | Raw pytest output |
| `pipeline_run_command` | `str` | pytest command string |
| `pipeline_run_return_code` | `int \| None` | Exit code |

### Reports

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_local_report` | `str` | Local report content |
| `pipeline_jira_report` | `str` | Jira report content |
| `pipeline_html_report` | `str` | HTML report content |
| `pipeline_local_report_path` | `str` | File path |
| `pipeline_jira_report_path` | `str` | File path |
| `pipeline_html_report_path` | `str` | File path |

### Test Plan

| Field | Type | Description |
|-------|------|-------------|
| `test_plan` | `TestPlan \| None` | Living test plan |
| `plan_confirmed` | `bool` | Signed-off flag |

### LLM Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `str` | `""` | Provider key (`ollama`, `lm-studio`, etc.) |
| `provider_base_url` | `str` | `""` | Base URL |
| `model_name` | `str` | `""` | Model identifier |

### Target Site

| Field | Type | Default |
|-------|------|---------|
| `starting_url` | `str` | `""` |
| `additional_urls` | `str` | `""` |

### Pipeline Settings

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `consent_mode` | `str` | `"auto-dismiss"` | Consent banner handling |
| `pom_mode` | `bool` | `False` | Page Object Model generation |

### Requirements

| Field | Type | Default |
|-------|------|---------|
| `raw_requirements` | `str` | `""` | Raw user story text |

### Authentication / Journey (AI-009 Phase B)

| Field | Type | Default |
|-------|------|---------|
| `credential_profile` | `CredentialProfile \| None` | `None` |
| `journey_steps` | `list[JourneyStep]` | `[]` |

### Persisted Package State (AI-026)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `loaded_package_manifest` | `PackageManifest \| None` | `None` | Loaded package metadata |
| `loaded_package_run_results` | `list[PersistedRunResult] \| None` | `None` | Run history for loaded package |
| `loaded_package_flaky_tests` | `list[tuple[str, dict]]` | `[]` | Flaky tests in loaded package |

## Factory Functions

### `_env_or_default(key: str, default: str) -> str`

Returns env var value or `default` when empty/missing.

### `_session_defaults() -> dict[str, str]`

Computes defaults from environment variables:

| Env Var | Maps To |
|---------|---------|
| `LLM_PROVIDER` | `session.provider` |
| `OLLAMA_BASE_URL` / `LM_STUDIO_BASE_URL` / `OPENAI_BASE_URL` | `session.provider_base_url` |
| `OLLAMA_MODEL` / `LM_STUDIO_MODEL` / `OPENAI_MODEL` | `session.model_name` |

Falls back to `get_provider_defaults(provider)` from `src.provider_config`.

### `create_session() -> Session`

Factory that creates a `Session` populated with environment-based defaults.
