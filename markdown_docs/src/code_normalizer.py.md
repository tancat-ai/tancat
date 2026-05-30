# `src/code_normalizer.py`

## High-Level Purpose

Deterministic normalization transforms for LLM-generated test code. Extracted from `code_postprocessor.py` to separate normalization logic into an independently testable module. All functions are pure string transformations with no LLM dependency.

## Module Metadata

- **Lines:** 353
- **Imports:** `re`

## Exported Functions (`__all__`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `convert_standalone_placeholders` | `(code: str) -> str` | Converts standalone placeholder lines and unwraps evidence_tracker-wrapped placeholders to `{{ACTION:description}}` token format |
| `replace_remaining_placeholders` | `(code: str) -> str` | Replaces unresolved `{{ACTION:description}}` placeholders with `pytest.skip()` — preserves placeholders inside string quotes |
| `strip_pages_needed_block` | `(code: str) -> str` | Removes trailing `# PAGES_NEEDED:` metadata comments from final generated code |
| `fix_module_scope_indentation` | `(code: str) -> str` | Ensures imports, class definitions, and test functions are at module scope (no indent) |
| `fix_indentation` | `(code: str) -> str` | Fixes inconsistent indentation inside test functions and class methods |
| `dedent_indented_test_blocks` | `(code: str) -> str` | Dedents malformed top-level test blocks that were shifted right as a unit |
| `deduplicate_skip_calls` | `(code: str) -> str` | Removes duplicate consecutive `pytest.skip()` calls in test blocks |
| `replace_bare_ellipsis` | `(code: str) -> str` | Replaces bare `...` (ellipsis) in test functions with `pytest.skip()`, ensures `import pytest` present |
| `ensure_test_navigation` | `(code: str, target_url: str \| None = None) -> str` | Injects initial `page.goto()` + `dismiss_consent_overlays(page)` if a test lacks navigation |

## Internal Constants

| Constant | Type | Description |
|----------|------|-------------|
| `_STANDALONE_PLACEHOLDER_RE` | `re.Pattern` | Matches standalone placeholder lines: `{{ACTION:description}}` with optional indent |

## Key Design Decisions
- **Pure functions** — all transforms take `str` input, return `str` output; no side effects
- **Quote-aware** — `replace_remaining_placeholders` uses `_is_inside_quotes()` to skip placeholders in string literals
- **Context-aware** — `replace_bare_ellipsis` tracks `inside_test` state to only replace ellipsis within test functions
- **Auto-import** — `replace_bare_ellipsis` inserts `import pytest` when skip calls are injected

## Dependencies
- No external library dependencies — pure `re`-based string transforms