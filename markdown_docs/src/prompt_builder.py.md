# prompt_builder.py

## Purpose
PEP 750 t-string (Python 3.14) based prompt assembly for LLM calls. Separates trusted static prompt structure from untrusted interpolated values so rendering can apply per-field safety transforms (truncation, sanitation) and record exactly what was sent to the LLM as a structured audit entry. LangChain-parallel: templates are declared in code at compile time (no runtime template parsing); `PromptBuilder.render()` is the `.format()` step with transforms and metadata instead of blind substitution.

## Location
`src/prompt_builder.py`

## Dependencies
- `string.templatelib` (stdlib, Python 3.14+) — `Template`, `Interpolation`
- `dataclasses`, `collections.abc`, `typing` (stdlib)

## Module Constants
- `TRUNCATION_LIMITS: dict[str, int]` — per-expression character limits (e.g. `user_story` 8000, `conditions` 15000, `known_urls_block` 4000). Keys are the source expression of each interpolation.

## Public API

### `truncate(text: str, limit: int) -> str`
Truncate text to `limit` chars with a `\n... (truncated)` suffix marker.

### `class PromptBuilder`
Renders a `Template` with per-field transforms.
- `__init__(template: Template, *, transforms: Mapping[str, Callable[[Any], str]] | None = None)` — optional caller-supplied transform overrides keyed by expression name.
- `render() -> RenderedPrompt` — iterates the template; `str` parts pass through (trusted static), `Interpolation` parts are transformed by expression name (unknown expressions fall back to `str()`).

### `@dataclass RenderedPrompt`
- `text: str` — final prompt string for the LLM.
- `fields: dict[str, Any]` — raw (pre-transform) values by expression.
- `truncated: list[str]` — expressions truncated during render.
- `parts: list[tuple[str, Any]]` — ordered `("static" | "field", value)` split for audit/debug.
- `to_log_entry() -> dict` — JSON-serialisable audit entry (prompt length, fields, truncated, static parts, field order).

### `build_skeleton_prompt(*, user_story, conditions, known_urls_block, expected_count=None) -> Template`
Phase 1 skeleton-generation prompt as a t-string. Rendered output is byte-identical to legacy `get_skeleton_prompt_template(expected_count=...).format(...)`. Double-brace `{{CLICK:...}}` placeholders render as literal `{CLICK:...}` (t-strings escape `{{` like f-strings).

### `build_single_condition_prompt(*, user_story, conditions_block, known_urls_block, target_condition_ref, target_condition_text, target_condition_expected) -> Template`
Per-condition skeleton-fragment prompt. `conditions_block` is pre-joined by the caller. Normalises placeholder examples to single-brace `{CLICK:...}` (the legacy function sent literal double braces — parser accepts both).

## Design Notes
- Interpolations are eagerly evaluated (like f-strings) but kept structurally separate from static text — the renderer decides how to combine them.
- Transforms are keyed by `Interpolation.expression` — the source expression string is the field name, free of charge.
- No `Template.__str__` — rendering is always explicit via `PromptBuilder` (feature, not friction).
- Do NOT mix `t"" f""` implicit concatenation (known PEP 750 footgun — silently reintroduces injection risk).
- Callers log `logger.debug("llm_call=... fields=%s", rendered.to_log_entry())` — the LLM gets the text, the audit store gets the metadata.

## Related Files
- `src/test_generator.py` — `_generate_skeleton_single_call` renders via `build_skeleton_prompt` + `PromptBuilder`
- `src/orchestrator.py` — `_generate_single_condition_fragment` renders via `build_single_condition_prompt` + `PromptBuilder`
- `src/prompt_utils.py` — legacy prompt builders (kept for back-compat + equivalence tests)
- `tests/test_prompt_builder.py` — 13 tests (byte-identity, brace survival, truncation, audit metadata)
- `scripts/eval/uat_tstring_prototype.py` — repeatable A/B UAT (legacy vs t-string paths)
