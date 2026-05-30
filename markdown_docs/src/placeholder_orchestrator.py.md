# `src/placeholder_orchestrator.py`

## High-Level Purpose
Orchestrates the placeholder resolution workflow by coordinating scorers, resolvers, and prerequisite injection to transform AI-generated test code with placeholders into complete, runnable tests.

## Module Metadata
- **Lines:** ~650
- **Imports:** `re`, `copy`, `logging`, `enum`, `dataclasses`, `typing`, `src.placeholder_resolver`, `src.placeholder_scorers`, `src.prerequisite_injector`, `src.prompt_utils`, `src.coverage_utils`, `src.evidence_loader`

## Classes

### `PlaceholderAction` (Enum)
Values: `REWRITE`, `OPTIMISE`, `NONE`

### `OrchestratorConfig` (dataclass)
Configuration with LLM ratios for rewrite/optimise thresholds.

### `OrchestratorResult` (dataclass)
Result with coverage analysis, score, action, file path, and evidence data.

## Functions

### `orchestrate_resolution(code: str, pages: list[PageData], config: OrchestratorConfig) -> OrchestratorResult`
Main entry point — runs resolution, scoring, action decision, and prerequisite injection pipeline.

### `_decide_action(score: float, config: OrchestratorConfig) -> PlaceholderAction`
Maps aggregate score to action using LLM ratio thresholds.

### `_load_evidence(file_path: str) -> dict | None`
Loads evidence JSON from test sidecar file.

## Key Design Decisions
- Score-driven action selection (rewrite vs optimise vs none)
- Evidence loading integrated for failure diagnostics
- Prerequisite injection runs after resolution

## Dependencies
- `src.placeholder_resolver`, `src.placeholder_scorers`, `src.prerequisite_injector`, `src.prompt_utils`, `src.coverage_utils`, `src.evidence_loader`