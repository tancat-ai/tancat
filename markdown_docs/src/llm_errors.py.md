# llm_errors.py

## Purpose
Lightweight error structures for LLM-backed test generation. Provides typed error categorization and result wrapping for all LLM interactions.

## Location
`src/llm_errors.py` (29 lines)

## Dependencies
- **Standard library only**: `dataclasses`, `enum`

## Public API

### `class LLMErrorType(StrEnum)`
High-level categories for LLM failures. Inherits from `StrEnum` for serializable values.

| Value | Meaning |
|-------|---------|
| `EMPTY_RESPONSE` | LLM returned an empty or whitespace-only response |
| `UNKNOWN` | Catch-all for unexpected errors |

### `@dataclass LLMError`
Structured error information for callers.

| Field | Type | Description |
|-------|------|-------------|
| `error_type` | `LLMErrorType` | Category of the error |
| `message` | `str` | Human-readable error description |

### `@dataclass LLMResult`
Wrapper for LLM generation results. Allows callers to handle success and failure uniformly.

| Field | Type | Description |
|-------|------|-------------|
| `code` | `str \| None` | Generated code on success, `None` on failure |
| `error` | `LLMError \| None` | Error details on failure, `None` on success |

## Design Notes
- `LLMErrorType` extends `StrEnum` (Python 3.11+) for JSON-serializable enum values
- Simple, focused module — no business logic, just data structures
- Used by `llm_client.py` to return structured results instead of raising exceptions
- Enables graceful error handling in the pipeline without crash-on-failure

## Related Files
- `src/llm_client.py` — primary consumer; wraps LLM responses in `LLMResult`
- `src/orchestrator.py` — handles `LLMResult.error` for fallback behavior