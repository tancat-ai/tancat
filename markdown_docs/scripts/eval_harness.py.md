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
