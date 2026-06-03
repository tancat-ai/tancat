# `src/pipeline_writer.py`

## High-Level Purpose

Writes intelligent-pipeline outputs as a structured artifact package. Persists final test code, page objects, manifest, and coverage summary into a timestamped package directory under `generated_tests/`.

## Module Metadata

- **Lines:** ~270
- **Imports:** `json`, `re`, `datetime`, `pathlib.Path`, `typing.TYPE_CHECKING`, `src.code_validator`, `src.file_utils.slugify`, `src.pipeline_models.ManifestRecord`, `src.pipeline_models.PipelineArtifactSet`, `src.pipeline_artifact_manager.PackageManifest`, `src.pipeline_artifact_manager.save_package_manifest`

## Class: `PipelineArtifactWriter`

### `__init__(output_dir="generated_tests")`
Sets output directory for artifact packages.

### `write_run_artifacts(run_result, story_text, base_url="", provider_name="", model_name="", additional_urls=[]) -> PipelineArtifactSet`
Main entry point. Writes one structured artifact package:
1. Validates generated code syntax — raises `ValueError` if invalid
2. Creates package directory with timestamp + story slug
3. Creates `pages/` subdirectory with `__init__.py`
4. Writes page object modules to `pages/`
5. Builds packaged test code (rewrites inline page object classes to imports from `pages/`)
6. Writes test file with header comment
7. Writes `coverage_summary.json`
8. Writes `scrape_manifest.json` with full run metadata
9. **Writes `package_manifest.json`** via `save_package_manifest()` (AI-026)
10. Returns `PipelineArtifactSet` with paths and records

### `_build_package_dir(story_text) -> Path`
Creates `test_{timestamp}_{story_slug}` directory.

### `_build_test_file_content(test_code, base_url) -> str`
Wraps test code with docstring header (generation timestamp, base URL).

### `_build_packaged_test_code(test_code, generated_page_objects) -> str`
Rewrites test code to import page objects from `pages/` package instead of inline class definitions. Removes inline class blocks, inserts `from pages.<module> import <Class>` imports.

### `_remove_class_definition(code, class_name) -> str`
Regex-based removal of top-level class block.

### `_build_manifest_records(run_result) -> list[ManifestRecord]`
Builds manifest records from unresolved placeholders.

### `_build_manifest_dict(...) -> dict`
Builds full JSON-serializable manifest: generation timestamp, URLs, page records, journeys, page objects, unresolved records.

### `_build_coverage_summary_dict(run_result) -> dict`
Lightweight coverage summary: journey count, page count, page object count, unresolved placeholders, test names.

## Package Manifest Persistence (AI-026, added 2026-06-02)

After writing all artifact files, `write_run_artifacts()` calls `save_package_manifest()` to persist a `package_manifest.json` inside the package directory. This manifest captures:

- **Package metadata:** name, created timestamp, source story text
- **Pipeline context:** starting URL, additional URLs scraped, provider name, model name
- **Artifact inventory:** generated test files, page object files, scrape manifest path
- **Extensibility points:** reports list, evidence paths, run results count, last run timestamp

The manifest is loaded by `pipeline_artifact_manager.load_package_manifest()` to enable "Load Existing Generated Tests" in both CLI and Streamlit UI.

### New Parameters (AI-026)

| Parameter | Type | Default | Source |
|-----------|------|---------|--------|
| `provider_name` | `str` | `""` | `session.provider` (CLI) or UI provider selection |
| `model_name` | `str` | `""` | `session.model_name` (CLI) or UI model selection |
| `additional_urls` | `list[str]` | `[]` | `session.additional_urls` (CLI) or UI URL inputs |

## Dependencies

- `src.code_validator.validate_python_syntax`
- `src.file_utils.slugify`
- `src.pipeline_models.ManifestRecord`, `PipelineArtifactSet`
- `src.pipeline_artifact_manager.PackageManifest`, `save_package_manifest` (AI-026)
- `src.orchestrator.PipelineRunResult` (TYPE_CHECKING)

## Depended On By

`orchestrator.py`, `ui_pipeline.py`