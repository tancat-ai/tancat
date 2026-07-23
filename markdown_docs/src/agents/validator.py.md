# src/agents/validator.py — ValidatorAgent

## Overview

LangGraph node: inspects the Generator's skeleton output and reports violations. Synchronous (no LLM calls). Three checks:

1. **Forbidden locators:** Reuses `SkeletonValidator` — catches CSS selectors, XPath, `page.locator()` with real selectors.
2. **Placeholder count:** Ensures skeleton contains at least one placeholder.
3. **Journey count match:** Parses test functions and compares count against `expected_test_count`.

## API

```python
class ValidatorAgent:
    def __init__(self, parser: SkeletonParser | None = None) -> None: ...
    def __call__(self, state: WorkflowState) -> dict[str, list[str] | int]: ...
```

Returns:
- On failure: `{"validation_errors": [...], "retry_count": state.retry_count + 1}`
- On success: `{"validation_errors": [], "retry_count": state.retry_count}` (preserved, not reset)

## Retry Semantics

- `retry_count` is **incremented** on each failure, **preserved** on success.
- The graph's conditional edge (`_should_retry`) routes back to Generator when `validation_errors` is non-empty and `retry_count <= max_retries`.
- On success, `retry_count` reflects the total number of retries used — useful for monitoring.

## Dependencies

- `SkeletonValidator` from `src.skeleton_validator`
- `SkeletonParser` from `src.skeleton_parser`
- No LLM — purely deterministic pattern matching
