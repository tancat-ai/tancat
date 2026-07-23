# src/agents/state.py — WorkflowState

## Overview

Pydantic `BaseModel` defining the serialisable workflow state passed between LangGraph agent nodes. Supports JSON serialisation for checkpoint persistence.

## Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `user_story` | `str` | `""` | User story text |
| `conditions` | `str` | `""` | Numbered acceptance criteria |
| `target_urls` | `list[str]` | `[]` | Known target URLs |
| `expected_test_count` | `int` | `0` | Expected number of test functions |
| `raw_dom_snapshot` | `str` | `""` | Optional pre-scraped DOM |
| `test_plan` | `str` | `""` | Planner output (Markdown) |
| `skeleton_code` | `str` | `""` | Generator output |
| `validation_errors` | `list[str]` | `[]` | Validator error messages |
| `retry_count` | `int` | `0` | Number of retries attempted |
| `max_retries` | `int` | `2` | Retry ceiling |

## Design Notes

- **Serialisable:** No non-trivial objects — only primitives, strings, and lists. LLMClient is injected at the graph level, not in state.
- **Retry semantics:** `retry_count` is incremented by the Validator on failure and preserved on success (never reset). The conditional edge routes to END when `retry_count > max_retries`.
- **Fallback fields:** `raw_dom_snapshot` reserved for future vision model input (Phase 1d synergy).
