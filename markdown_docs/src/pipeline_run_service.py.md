# `src/pipeline_run_service.py`

## High-Level Purpose

Execute saved generated test packages via pytest and parse their output. Handles subprocess invocation, PYTHONPATH setup, timeout enforcement, and failed-test rerun.

## Module Metadata

- **Lines:** 71
- **Imports:** `os`, `subprocess`, `sys`, `dataclasses.dataclass`, `pathlib.Path`, `src.pytest_output_parser`, `src.run_utils`

## Data Classes

### `PipelineExecutionResult` (frozen)
Structured result for one generated-package pytest execution.
- `command: list[str]` — Full command executed
- `run_result: RunResult` — Parsed pytest results (pass/fail/skip per test)
- `display_output: str` — Formatted pytest output for display
- `return_code: int` — Process exit code

## Class: `PipelineRunService`

### `run_saved_test(saved_path, rerun_failed_only=False, previous_run=None, cwd=None) -> PipelineExecutionResult`
1. Extract failed nodeids from `previous_run` if `rerun_failed_only`
2. Build pytest command via `build_pytest_run_command`
3. Set PYTHONPATH to include project root + package directory
4. Run `subprocess.run` with hard timeout (default 300s, configurable via `PIPELINE_TEST_TIMEOUT`)
5. Parse stdout/stderr via `parse_pytest_output`
6. Return `PipelineExecutionResult`

## Dependencies

- `src.pytest_output_parser.parse_pytest_output`, `format_pytest_output_for_display`, `RunResult`
- `src.run_utils.build_pytest_run_command`, `get_failed_nodeids`

## Depended On By

`orchestrator.py`, `ui_pipeline.py`, `cli/pipeline_runner.py`