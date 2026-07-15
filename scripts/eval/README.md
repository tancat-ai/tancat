# Evaluation Harness — Usage Guide

## Overview

Automated evaluation of test generation quality. Measures placeholder resolution accuracy, test pass rate, and false positive rate against golden answer keys.

## Quick Start

```bash
# Static mode — resolution accuracy only (fast, no browser)
python scripts/eval/eval_harness.py run --mode static

# Full mode — resolution + test execution (needs browser)
python scripts/eval/eval_harness.py run --mode full

# Save baseline
python scripts/eval/eval_harness.py baseline --save

# Compare current vs baseline
python scripts/eval/eval_harness.py compare

# Validate golden keys
python scripts/eval/eval_harness.py dataset --validate
```

## Commands

### `run`

Execute evaluation against golden keys.

| Flag | Description |
|------|-------------|
| `--mode static` | Resolution accuracy only (default, no browser needed) |
| `--mode full` | Resolution + test execution against live sites |
| `--min-accuracy N` | Exit code 2 if accuracy < N% (CI quality gate) |
| `--no-persist` | Skip saving results to SQLite |
| `--pytest-timeout S` | Timeout per pytest run (default: 120s) |

### `baseline`

Manage the reference baseline.

| Flag | Description |
|------|-------------|
| `--save` | Run evaluation and save results to `baseline.json` |
| (no flags) | Display current baseline |

### `compare`

Compare current evaluation against saved baseline. Shows per-metric deltas (accuracy, pass rate, etc.).

### `dataset`

Validate golden key JSON files.

| Flag | Description |
|------|-------------|
| `--validate` | Deep-validate all placeholder fields |

## Architecture

```
eval_harness.py (CLI)
  └── eval_runner.py (orchestration)
        ├── golden_validator.py (parse code, match locators)
        ├── eval_metrics.py (compute metrics, render reports)
        └── SQLite eval_runs table (persistence)
```

## Golden Answer Keys

Stored in `scripts/eval/dataset/*.json`. Each file contains:
- User story and conditions
- Golden resolutions (expected locators with tolerance selectors)

**Adding a new story:**
1. Run the pipeline against the target site
2. Capture generated code in `scripts/eval/captures/`
3. Hand-validate each locator against the live site
4. Write golden key JSON in `scripts/eval/dataset/`
5. Run `python scripts/eval/eval_harness.py dataset --validate`

## Metrics

| Metric | Formula |
|--------|---------|
| Resolution accuracy | correct_placeholders / total_placeholders × 100 |
| Test pass rate | tests_passed / tests_executed × 100 |
| False positive rate | wrong_locator_passes / tests_executed × 100 |
| Skeleton completeness | criteria_with_skeletons / total_criteria × 100 |

## CI Integration

The workflow `.github/workflows/eval-harness.yml` runs on `workflow_dispatch` (manual trigger only).

- **Gate, not break** — warns on low accuracy but doesn't fail the pipeline
- **Inputs**: mode (`static` or `full`), min_accuracy threshold
- **Outputs**: markdown summary as artifact, PR comment on pull requests

## Current Baseline

| Metric | Value |
|--------|-------|
| Stories | 4 |
| Resolution accuracy | 79.1% |
| Skeleton completeness | 100.0% |

Baseline file: `scripts/eval/baseline.json`
