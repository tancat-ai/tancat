# Test Suite Audit - 2026-04-08

## Summary

The repo currently has three different categories of "tests":

1. Real maintained product tests under `tests/`
2. Generated output artifacts under `generated_tests/`
3. Exploratory/manual UAT-style checks mixed into `tests/`

The main clutter problem is `generated_tests/`, not the core unit suite.

## Keep

These protect the current intelligent pipeline and shared product behavior:

- `tests/test_orchestrator.py`
- `tests/test_skeleton_parser.py`
- `tests/test_placeholder_resolver.py`
- `tests/test_scraper.py`
- `tests/test_page_object_builder.py`
- `tests/test_pipeline_models.py`
- `tests/test_pipeline_writer.py`
- `tests/test_pipeline_run_service.py`
- `tests/test_pipeline_report_service.py`
- `tests/test_pytest_output_parser.py`
- `tests/test_run_utils.py`
- `tests/test_coverage_utils.py`
- `tests/test_user_story_parser.py`
- `tests/test_code_validator.py`

These still protect adjacent tool behavior and should stay for now:

- `tests/test_test_generator.py`
- `tests/test_llm_client.py`
- `tests/test_llm_errors.py`
- `tests/test_cli_smoke.py`
- `tests/test_cli_test_orchestrator.py`

## Review / Possibly Slim Down

These are not obviously wrong, but they reflect older or alternate architecture paths and should be reviewed rather than deleted blindly:

- `tests/test_page_context_scraper.py`

Reason:
- This file covers the older page-context scraper architecture.
- The current Streamlit path uses the new intelligent pipeline modules instead.
- The module still exists and may still matter for CLI or future browser-backed scraping.
- Recommendation: trim to behavior we still support, rather than removing it immediately.

## Move Out Of The Main Test Suite

- `tests/uat_pipeline_test.py`

Reason:
- This behaves more like a manual or exploratory UAT script than a stable unit/integration test.
- Recommendation: move to `scripts/`, `docs/uat/`, or a dedicated `manual_checks/` folder.

## Remove From `tests/`

- `tests/coverage.xml`

Reason:
- This is a generated artifact, not a test source file.

## Generated Output Cleanup

`generated_tests/` currently contains both sample files and many historical generated runs.

Examples:

- old flat generated files like `generated_tests/test_20260405_221034_PAGE_CONTEXT__use_these_locato.py`
- old package folders from multiple UAT attempts
- sample/demo files such as `tests/example_test.py` and `generated_tests/test_happy_path.py`

These are not part of the maintained unit suite because `pytest.ini` points test discovery at `tests/` only.

Recommendation:

1. Keep only a minimal set of intentional examples in `generated_tests/`
2. Delete old generated run folders after successful UAT cycles
3. Consider adding a retention rule, for example:
   - keep latest N generated run folders
   - delete older generated package directories automatically or via a cleanup command

## Suggested Next Cleanup Pass

1. Remove `tests/coverage.xml`
2. Move `tests/uat_pipeline_test.py` out of `tests/`
3. Review `tests/test_page_context_scraper.py` and trim unsupported legacy coverage
4. Clean historical folders in `generated_tests/`, keeping only:
   - one or two representative examples
   - the latest active debugging package
