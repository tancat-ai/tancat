# `src/ui_renderers.py`

## Purpose
Streamlit rendering helpers — pure UI, no business logic. Extracted from streamlit_app for testability.

## Metadata
- **Lines:** 1106
- **Imports:** streamlit, src.coverage_utils, src.failure_classifier, src.gantt_utils, src.heatmap_utils, src.pytest_output_parser, src.report_utils, src.journey_scraper

## Classes
| Class | Description |
|-------|-------------|
| `SidebarConfig` | Renders configuration sidebar, returns provider dict |
| `RequirementsInput` | Renders requirements input with paste/upload modes |
| `ResultsPanel` | Renders pipeline results tabs (Final Code, Skeleton, Scrape) |
| `RunResultsDisplay` | Renders test run results with failure classification and repair buttons |
| `RenderDownloads` | Renders report download buttons (Manifest, Local, Jira, HTML) |
| `EvidenceViewer` | Renders evidence viewer: annotated screenshots, Gantt, heatmap |
| `SavedPackagePanel` | Renders saved package panel: load/reload saved test packages with metadata, run history, and flakiness (AI-026) |

## Functions
| Function | Description |
|----------|-------------|
| `render_credential_profiles()` | Renders auth section, returns active CredentialProfile |
| `render_journey_builder(additional_urls)` | Renders journey builder, returns list[JourneyStep] |
| `_render_single_step(idx, step)` | Renders single journey step row |
| `_urls_to_journey_step_dicts(urls)` | Converts URLs to goto+capture step dicts |
| `_dict_to_journey_step(d)` | Converts dict to JourneyStep dataclass |
| `run_codegen_session(url, timeout)` | Launches headed Playwright codegen, captures locator |
| `_handle_run_tests()` / `_handle_rerun_failed()` | Button handlers for test execution |
| `_render_repair_*` | Locator repair panel rendering (waiting, browser, result) |

## Dependencies
- `streamlit`, `src.coverage_utils`, `src.failure_classifier`, `src.gantt_utils`, `src.heatmap_utils`, `src.locator_repair`, `src.ui_pipeline`, `src.pipeline_artifact_manager`, `src.run_result_persistence`
