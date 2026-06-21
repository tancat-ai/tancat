# `src/code_normalizer.py`

## High-Level Purpose

`code_normalizer.py` provides deterministic post-processing transforms for LLM-generated Playwright pytest code. It normalizes whitespace, repairs common indentation defects, converts unresolved placeholder syntax into executable `pytest.skip(...)` statements, removes skeleton metadata, deduplicates skip calls, replaces incomplete ellipsis bodies, and injects missing navigation steps when enough URL context is available.

The module is designed as an independently testable normalization layer extracted from a larger post-processing pipeline. Its functions accept Python source code as plain strings and return transformed source code as strings, making the module easy to compose into ordered pipelines.

## Public API

The module defines `__all__` to export the following functions:

- `normalize_whitespace`
- `convert_standalone_placeholders`
- `replace_remaining_placeholders`
- `strip_pages_needed_block`
- `fix_module_scope_indentation`
- `fix_indentation`
- `dedent_indented_test_blocks`
- `deduplicate_skip_calls`
- `replace_bare_ellipsis`
- `ensure_test_navigation`

## Imports

```python
from __future__ import annotations

import re
```

The module depends only on Python's standard `re` module. Future annotations are enabled so modern type syntax can be used consistently.

## Constants

### `_STANDALONE_PLACEHOLDER_RE`

```python
_STANDALONE_PLACEHOLDER_RE = re.compile(
    r"^(\s*)\{\{(CLICK|FILL|GOTO|URL|ASSERT):([^}]+)\}\}\s*$",
    re.MULTILINE,
)
```

Matches lines containing only a supported placeholder token, preserving leading indentation and extracting the action plus description.

### `_CONTROL_FLOW_RE`

```python
_CONTROL_FLOW_RE = re.compile(r"^(if |for |while |with |try:|async with |async for )")
```

Identifies control-flow statements that can legitimately introduce nested indentation inside a function body.

## Functions

### `normalize_whitespace`

```python
def normalize_whitespace(code: str) -> str:
```

Parameters:

- `code: str` - Python source code that may contain tabs or mixed line endings.

Returns:

- `str` - Code with Windows and old-Mac line endings normalized to `\n`, and tabs expanded to four spaces.

Purpose:

This is intended as an early pipeline step. It standardizes indentation and line endings before later transforms reason about column counts or inject additional lines.

### `convert_standalone_placeholders`

```python
def convert_standalone_placeholders(code: str) -> str:
```

Parameters:

- `code: str` - Generated Python source code that may contain placeholder tokens.

Returns:

- `str` - Code where standalone placeholders and evidence-tracker-wrapped placeholders are unwrapped into raw placeholder lines.

Purpose:

Normalizes placeholder representation before later resolution or fallback conversion. It handles both bare standalone tokens such as `{{CLICK:...}}` and malformed calls such as `evidence_tracker.click({{CLICK:...}}...)`, emitting a single placeholder token at the original indentation level.

Key behavior:

- Preserves indentation.
- Recognizes `CLICK`, `FILL`, `GOTO`, `URL`, and `ASSERT` placeholders.
- Handles wrapper methods `click`, `fill`, `navigate`, and `assert_visible`.

### `replace_remaining_placeholders`

```python
def replace_remaining_placeholders(code: str) -> str:
```

Parameters:

- `code: str` - Generated Python source code that may still contain unresolved `{{ACTION:description}}` placeholders.

Returns:

- `str` - Code where unresolved placeholders are replaced by `pytest.skip(...)` calls.

Purpose:

Converts unresolved placeholder syntax into valid pytest code so generated tests remain syntactically executable and explicitly skipped rather than crashing at parse time.

Key behavior:

- Finds placeholders with `re.compile(r"\{\{[A-Z_]+:(.+?)\}\}", re.DOTALL)`.
- If a placeholder appears inside a function call, replaces the whole affected line with one `pytest.skip(...)`.
- If placeholders appear outside a function call, replaces each placeholder token with `pytest.skip('<placeholder>')`.
- Preserves leading indentation for generated skip lines.

Nested helper:

```python
def _handle_match(m: re.Match) -> str:
```

Parameters:

- `m: re.Match` - Placeholder regex match.

Returns:

- `str` - A `pytest.skip(...)` expression containing the placeholder text.

### `strip_pages_needed_block`

```python
def strip_pages_needed_block(code: str) -> str:
```

Parameters:

- `code: str` - Generated Python source code that may include skeleton metadata comments.

Returns:

- `str` - Code with a trailing `# PAGES_NEEDED:` metadata block removed.

Purpose:

Removes skeleton-generation metadata from final emitted code while preserving normal code that follows the metadata block.

Key behavior:

- Starts removal when a line exactly matches `# PAGES_NEEDED:`.
- Skips blank lines and `# -` entries while inside the block.
- Resumes preserving lines once a non-metadata line appears.

### `fix_module_scope_indentation`

```python
def fix_module_scope_indentation(code: str) -> str:
```

Parameters:

- `code: str` - Python source code that may have module-level declarations indented by mistake.

Returns:

- `str` - Code where imports, classes, test functions, and `@pytest.mark` decorators are forced to module scope.

Purpose:

Repairs common LLM output where top-level declarations are accidentally shifted right.

Module-level patterns:

- `import `
- `from `
- `def test_`
- `class `
- `@pytest.mark`

### `_is_control_flow_line`

```python
def _is_control_flow_line(line: str) -> bool:
```

Parameters:

- `line: str` - A stripped or unstripped source line.

Returns:

- `bool` - `True` when the line ends with `:` and matches a recognized control-flow opener.

Purpose:

Private indentation helper used by `fix_indentation` to distinguish legitimate nested blocks from accidental over-indentation.

### `fix_indentation`

```python
def fix_indentation(code: str) -> str:
```

Parameters:

- `code: str` - Python source code with potentially inconsistent indentation inside functions or methods.

Returns:

- `str` - Code with repaired indentation in function bodies.

Purpose:

Normalizes common indentation mistakes within test functions and class methods while preserving legitimate nested blocks.

Key behavior:

- Tracks whether iteration is inside a function.
- Computes expected function-body indentation from the `def` line.
- Forces under-indented non-declaration body lines up to the expected body indent.
- Normalizes comments to at least the function-body indent.
- Detects accidental extra indentation after non-control-flow lines and dedents those lines back to function-body indent.
- Resets function context on class definitions.

Architectural note:

This function is stateful over lines. It maintains `inside_function`, `func_indent`, `previous_significant_indent`, and `previous_significant_line` to make local indentation decisions without parsing the Python AST.

### `dedent_indented_test_blocks`

```python
def dedent_indented_test_blocks(code: str) -> str:
```

Parameters:

- `code: str` - Python source code where entire top-level test blocks may be shifted right.

Returns:

- `str` - Code where malformed test blocks starting with an indented evidence marker or `def test_` are dedented as a unit.

Purpose:

Repairs generated tests where a whole top-level test block is incorrectly nested.

Key behavior:

- Scans line-by-line using an index-based loop.
- Detects an indented block beginning with `@pytest.mark.evidence` or `def test_`.
- Removes the shared block indentation until the block ends.
- Preserves blank lines inside the dedented block.

### `deduplicate_skip_calls`

```python
def deduplicate_skip_calls(code: str) -> str:
```

Parameters:

- `code: str` - Python source code that may contain repeated `pytest.skip(...)` calls.

Returns:

- `str` - Code with consecutive skip calls reduced to one and navigation steps preserved before skip emission.

Purpose:

Prevents generated tests from being cluttered with duplicate skip calls and avoids skipping before an initial navigation line has executed.

Key behavior:

- Tracks when it is inside a `def test_` block.
- Buffers skip calls in `pending_skips`.
- Flushes only the first pending skip when a non-skip line is reached.
- Defers skip flushing across `navigate(...)` or `goto(...)` lines so navigation remains before the skip.

Nested helper:

```python
def _flush_skips() -> None:
```

Parameters:

- None.

Returns:

- `None`

Purpose:

Appends the first pending skip call to the output and clears the pending skip buffer.

### `replace_bare_ellipsis`

```python
def replace_bare_ellipsis(code: str) -> str:
```

Parameters:

- `code: str` - Python source code that may contain bare `...` statements in generated test bodies.

Returns:

- `str` - Code where incomplete test-body ellipses are replaced by `pytest.skip(...)`.

Purpose:

Converts placeholder ellipsis bodies into explicit skipped tests so the generated output remains meaningful and executable.

Key behavior:

- Applies only while inside a `def test_*` function.
- Replaces a line whose stripped content is exactly `...` unless the following line is a comment.
- Adds `import pytest` if a skip call was introduced and no existing exact `import pytest` line exists.
- Inserts `import pytest` before the first import line it finds.

### `ensure_test_navigation`

```python
def ensure_test_navigation(code: str, target_url: str | None = None) -> str:
```

Parameters:

- `code: str` - Python source code containing generated test functions.
- `target_url: str | None = None` - Optional URL to inject. If omitted, the function attempts to extract the first URL from a `# PAGES_NEEDED:` block.

Returns:

- `str` - Code where test functions that accept `evidence_tracker` receive an initial navigation sequence if they do not already navigate.

Purpose:

Ensures generated tests start from a known page when either a direct target URL or skeleton metadata provides one.

Key behavior:

- Uses `target_url` when provided.
- Otherwise searches for a `# PAGES_NEEDED:` block containing comment URLs.
- Returns the original code unchanged if no URL can be found.
- Matches test functions containing `evidence_tracker` in the signature.
- Skips injection when a matched test body already contains `navigate(` or `goto(`.
- Injects:

```python
evidence_tracker.navigate("<url>")
dismiss_consent_overlays(page)
```

Nested helper:

```python
def _detect_body_indent(body: str) -> str:
```

Parameters:

- `body: str` - Captured test function body text.

Returns:

- `str` - The indentation string from the first significant body line, or four spaces by default.

Purpose:

Mirrors the existing function body's indentation style when injecting navigation.

Nested helper:

```python
def _inject_nav(match: re.Match[str]) -> str:
```

Parameters:

- `match: re.Match[str]` - Regex match containing the test function signature and body.

Returns:

- `str` - The original matched test function if navigation exists, otherwise the signature plus injected navigation lines and original body.

Purpose:

Per-test replacement callback used by `re.sub`.

## Architectural Patterns

### String-In, String-Out Normalization Pipeline

Every public function accepts source text and returns source text. This keeps the normalizer simple to compose and allows callers to run only the transforms they need in a deliberate order.

### Regex-Based Repair Instead Of AST Rewriting

The module uses regular expressions and line scanning instead of `ast` parsing because it is intended to repair code that may be temporarily invalid Python. This lets it normalize malformed LLM output before stricter syntax-dependent tooling runs.

### Conservative Local State Machines

Several transforms use lightweight state while scanning lines:

- `fix_indentation` tracks function context and previous significant lines.
- `dedent_indented_test_blocks` tracks block boundaries with an explicit index.
- `deduplicate_skip_calls` tracks test context and pending skip lines.
- `replace_bare_ellipsis` tracks whether the current line is inside a test function.

These state machines are intentionally local and deterministic.

### Graceful Degradation For Unresolved Generation Artifacts

Unresolved placeholders and incomplete ellipses are not allowed to remain as invalid or misleading code. They are converted into `pytest.skip(...)` statements, preserving test executability while surfacing incomplete generated behavior.

### Playwright/Pytest Sync Assumptions

The module assumes generated tests are pytest-style synchronous tests. Navigation injection uses `evidence_tracker.navigate(...)` and `dismiss_consent_overlays(page)`, and test detection is centered on `def test_*` functions rather than async Playwright code.

### Metadata-Aware Generation Cleanup

`strip_pages_needed_block` and `ensure_test_navigation` both understand the `# PAGES_NEEDED:` skeleton metadata convention. One removes it from final code, while the other can use it as a fallback source for the initial navigation URL.

## Expected Usage

A typical caller would apply these transforms as an ordered post-processing pipeline after LLM generation and placeholder resolution. `normalize_whitespace` should run early because later indentation logic assumes spaces and normalized line endings. Placeholder and ellipsis cleanup should run before final syntax validation so unresolved generation artifacts become valid pytest code.

## Side Effects

The module itself has no filesystem, network, subprocess, or runtime test side effects. All transformations operate on in-memory strings.
