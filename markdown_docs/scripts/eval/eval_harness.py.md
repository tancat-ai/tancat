# scripts/eval/eval_harness.py

The CLI entry point for the Automated Evaluation Harness.

## Overview
This module provides a command-line interface to execute the evaluation pipeline, manage baselines, and validate the golden dataset.

## Subcommands

### `run`
Executes the evaluation against golden keys.
- `--mode`: `static` (resolution only) or `full` (resolution + test execution).
- `--regenerate`: **(New)** When set, the harness bypasses static captures and runs the actual `TestOrchestrator` pipeline to generate fresh code. This is essential for measuring the impact of RAG or prompt changes.
- `--min-accuracy`: Sets a threshold for the resolution accuracy.

### `baseline`
- `--save`: Captures the current run results and saves them as `baseline.json` for future comparison.

### `compare`
Compares the current run results against the saved baseline, calculating delta (pp) for key metrics.

### `dataset`
- `--validate`: Validates the JSON schema and content of the golden keys in `scripts/eval/dataset/`.

## Workflow for RAG Evaluation
To measure RAG improvements:
1. **Baseline**: `RAG_ENABLED=0 python scripts/eval/eval_harness.py run --mode static --regenerate`
2. **RAG Test**: `RAG_ENABLED=1 python scripts/eval/eval_harness.py run --mode static --regenerate`
3. **Analysis**: `python scripts/eval/eval_harness.py compare`

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `main` (function): `main(argv: list[str] | None = None) -> int`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (7 items). Grouped under the public function that calls them.

### `main(argv: list[str] | None = None) -> int` - function

- `_setup_logging(verbose: bool = False) -> None` (function): Setup logging; calls `basicConfig`; returns None.

### Internal utilities

- `_cmd_run(args: argparse.Namespace) -> int` (function): Execute the evaluation harness.
- `_cmd_baseline(args: argparse.Namespace) -> int` (function): Save or display the reference baseline.
- `_cmd_compare(args: argparse.Namespace) -> int` (function): Compare current results against the baseline, or two runs' criteria.
- `_cmd_report(args: argparse.Namespace) -> int` (function): Print the eval rollup: per story, per site, over time, plus miss classes.
- `_cmd_rebuild(args: argparse.Namespace) -> int` (function): Rebuild an eval_runs row + criteria from a run's kept evidence (no model).
- `_cmd_dataset(args: argparse.Namespace) -> int` (function): Validate golden key files.
