# run_utils.py

## Purpose
Pytest command utilities — builds pytest CLI commands, parses raw pytest output to extract failed test node IDs, and defines the `RunTestRecord` protocol for test execution results.

## Location
`src/run_utils.py`

## Dependencies
- `re` (standard library)
- `typing.Protocol, runtime_checkable` (standard library)

## Public API

### `RunTestRecord` (Protocol)
Protocol defining the shape of a test execution result record. Fields: `test_path`, `passed`, `duration`, `error_message`.

### `get_failed_nodeids(output: str) -> list[str]`
Parse pytest terminal output and extract failed test node IDs (e.g., `test_file.py::test_function`).

### `extract_failed_nodeids_from_raw_output(output: str) -> list[str]`
Legacy name for `get_failed_nodeids`. Parses raw pytest output using regex to find failed test identifiers.

### `build_pytest_run_command(test_paths: list[str], failed_ids: list[str] | None = None, verbose: bool = False, parallel: bool = True) -> list[str]`
Build a pytest CLI command list suitable for `subprocess.run()`. Supports parallel execution (`-n auto`), verbose mode, and test selection via failed node IDs.

## Design Notes
- All functions are pure — no side effects
- Regex-based parsing for pytest output is fragile but sufficient for controlled CI environments
- `build_pytest_run_command` returns a list for safe subprocess invocation (no shell injection)
- Used by pipeline runner and CLI to execute generated tests

## Related Files
- `src/orchestrator.py` — uses run utilities for test execution
- `cli/pipeline_runner.py` — builds pytest commands for CLI runs
- `src/pytest_output_parser.py` — sibling output parsing module