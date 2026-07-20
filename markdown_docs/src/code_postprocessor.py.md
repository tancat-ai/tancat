# `src/code_postprocessor.py`

## High-Level Purpose

`code_postprocessor.py` contains pure string-transformation helpers for generated Playwright Python code. It normalizes LLM-produced test code into the project's expected pytest sync format, repairs common hallucinations, injects required imports and fixtures, converts placeholder tokens into executable evidence-tracker calls, and can strip evidence-tracking instrumentation back out for export.

The module is intentionally stateless: every function accepts a source-code string or single code line and returns a transformed string. It performs no filesystem I/O, subprocess work, or network access.

## Module Dependencies

- `re`: regular-expression engine used for most repairs and rewrites.
- `.code_normalizer`: supplies deterministic normalization utilities used by `normalise_generated_code()`, including whitespace normalization, indentation repair, placeholder cleanup, navigation injection, and skip-call deduplication.
- `.llm_reasoning_filter.strip_llm_reasoning`: removes leaked reasoning text before the rest of the post-processing pipeline runs.

## Classes

This module defines no classes.

## Public Functions

### `normalise_generated_code(code: str, consent_mode: str = "auto-dismiss", target_url: str = "") -> str`

Applies the main post-processing pipeline to generated test code.

Parameters:

- `code: str`: Raw generated Python code.
- `consent_mode: str`: Consent overlay behavior. When set to `"auto-dismiss"`, the function injects consent-helper imports and calls after navigation.
- `target_url: str`: Optional URL used by `ensure_test_navigation()` when inserting missing test navigation.

Returns:

- `str`: Normalized, repaired Python code.

Key behavior:

- Normalizes whitespace before other transforms.
- Strips leaked LLM reasoning text.
- Converts standalone placeholders and evidence-tracker-wrapped placeholders.
- Repairs malformed pytest evidence decorators.
- Injects `pytest` and `playwright.sync_api` imports when needed.
- Renames hallucinated `evidence_launcher` fixture references to `evidence_tracker`.
- Ensures test functions include required `page: Page` and `evidence_tracker` fixtures.
- Rewrites direct `page.goto()` calls to `evidence_tracker.navigate()`.
- Repairs hallucinated marker syntax, constructor names, page-object constructor arguments, and invalid decorator assignment lines.
- Normalizes several hallucinated type annotations to `Page`.
- Optionally injects consent-overlay dismissal support.
- Rewrites bare `page.` references inside non-test class instance methods to `self.page.`.
- Removes unsupported `evidence_tracker.record_condition(...)` calls.
- Ensures tests contain navigation, strips unresolved placeholders, fixes module/test indentation, deduplicates skips, and replaces bare ellipses.

Architectural note: ordering is important. Early cleanup prepares the code for import and fixture inference; late indentation and placeholder passes act as safety nets after regex rewrites have potentially changed structure.

### `replace_token_in_line(line: str, action: str, token: str, resolved_value: str, duplicate_selectors: set[str], description: str = "", fill_value: str = "") -> str`

Replaces one placeholder token within a single line of generated code.

Parameters:

- `line: str`: Source line containing, or potentially containing, a placeholder token.
- `action: str`: Placeholder action type. Recognized actions are `"CLICK"`, `"ASSERT"`, `"FILL"`, `"GOTO"`, and `"URL"`.
- `token: str`: Placeholder token to replace.
- `resolved_value: str`: Selector, URL, or replacement expression resolved for the token.
- `duplicate_selectors: set[str]`: Accepted by the signature but not used in the current function body.
- `description: str`: Optional human-readable label for evidence tracker calls. Falls back to `token`.
- `fill_value: str`: Value used when rewriting `"FILL"` actions.

Returns:

- `str`: The rewritten line, preserving original indentation where a whole-line replacement is emitted.

Key behavior:

- Converts `CLICK` placeholders to `evidence_tracker.click(...)`.
- Converts `ASSERT` placeholders and matching `expect(page.locator(...))` assertions to `evidence_tracker.assert_visible(...)`.
- Converts `FILL` placeholders to `evidence_tracker.fill(...)`, including repair of evidence-tracker calls missing the fill value.
- Converts `GOTO` and `URL` placeholders to `evidence_tracker.navigate(...)` or replaces quoted token references.
- Preserves `pytest.skip(...)` replacements as whole-line returns.

### `inject_import(code: str, import_line: str) -> str`

Injects an import line near the top of a Python code string.

Parameters:

- `code: str`: Python source text.
- `import_line: str`: Import statement to add.

Returns:

- `str`: Source text with the import added once.

Key behavior:

- Inserts after an opening module docstring when present.
- Uses normalized whitespace comparison to avoid duplicate imports.

### `strip_evidence_from_test_code(code: str) -> str`

Converts evidence-aware test code back into plain Playwright test code.

Parameters:

- `code: str`: Generated test code that may use `evidence_tracker`.

Returns:

- `str`: Test code using direct Playwright `page` and `expect` calls.

Key behavior:

- Rewrites evidence-tracker actions to Playwright equivalents:
  - `click()` -> `page.locator(...).click()`
  - `fill()` -> `page.locator(...).fill(...)`
  - `navigate()` -> `page.goto(...)`
  - `assert_visible()` -> `expect(page.locator(...)).to_be_visible()`
  - `select()` -> `page.locator(...).select_option(...)`
  - `get_text()` -> `page.locator(...).text_content()`
- Removes `evidence_tracker` parameters from test signatures.
- Removes `EvidenceTracker` and consent-helper imports.
- Removes `@pytest.mark.evidence` decorators.
- Ensures the Playwright import includes `expect` when assertions are present.
- Removes consent-helper calls and collapses excessive blank lines.

### `strip_evidence_from_pom(code: str) -> str`

Converts evidence-aware page-object-model code back into plain Playwright POM code.

Parameters:

- `code: str`: Page-object code that may use `self.tracker`.

Returns:

- `str`: Page-object code using direct `self.page` and `expect` calls.

Key behavior:

- Removes `EvidenceTracker` imports and constructor parameters.
- Removes `self.tracker = tracker` assignments.
- Rewrites tracker calls to direct Playwright calls on `self.page`.
- Ensures `expect` is imported when assertion rewrites require it.
- Collapses excessive blank lines.

### `flatten_inner_functions(code: str) -> str`

Removes nested function wrappers inside top-level test functions.

Parameters:

- `code: str`: Python source text that may contain nested helper/test functions.

Returns:

- `str`: Source text with nested function bodies lifted into the enclosing test block.

Key behavior:

- Scans line by line for top-level `def test_...` functions.
- Detects nested `def ...` blocks inside tests.
- Preserves nearby `@pytest.mark.evidence` decorators by moving them to the enclosing test indentation.
- Drops self-calls to the nested function when lifting the body.

### `rewrite_page_references_in_class_methods(code: str) -> str`

Rewrites bare page references inside non-test class instance methods.

Parameters:

- `code: str`: Python source text.

Returns:

- `str`: Source text with selected instance-method references rewritten.

Key behavior:

- Tracks whether the scan is inside a class and whether that class appears to be a test class.
- For non-test classes, detects instance methods whose first parameter is `self`.
- Replaces bare `page.` with `self.page.` inside those methods.
- Rewrites `evidence_tracker.` to `self.evidence_tracker.` when the method signature does not have an `evidence_tracker` parameter.
- Rewrites `dismiss_consent_overlays(page)` to `dismiss_consent_overlays(self.page)`.
- Replaces `(page)` and `Page(` patterns inside instance methods with self-page equivalents.

## Internal Helpers

### `_ensure_evidence_tracker_fixture(code: str) -> str`

Adds `page: Page` and `evidence_tracker` fixture parameters to test functions that need them.

Parameters:

- `code: str`: Python source text.

Returns:

- `str`: Source text with updated test function signatures.

Key behavior:

- Finds `def test_...(...)` signatures using regex.
- Reads each test body by scanning until the next top-level decorator, function, class, or import.
- Infers `evidence_tracker` need from `evidence_tracker.` usage and page-object instantiation.
- Infers `page` need from POM construction, bare `page.` usage, consent-helper usage, or evidence-tracker usage.
- Ensures `page: Page` appears first when required.
- Appends `evidence_tracker` when required and absent.

### `_inject_consent_helper(code: str) -> str`

Injects consent overlay dismissal support.

Parameters:

- `code: str`: Python source text.

Returns:

- `str`: Source text with the consent-helper import and calls inserted.

Key behavior:

- Adds `from src.browser_utils import dismiss_consent_overlays` after the Playwright import when possible, otherwise prepends it.
- Adds `dismiss_consent_overlays(page)` after lines that call `page.goto(...)` or `evidence_tracker.navigate(...)`.
- Avoids adding duplicate calls on lines already mentioning the helper.

## Architectural Patterns

- Functional pipeline: transformations are composed as string-in/string-out functions.
- Regex-first repair strategy: most changes are targeted text rewrites for recurring LLM output patterns.
- Late safety nets: indentation repair, unresolved-placeholder replacement, skip deduplication, and ellipsis replacement run after broader rewrites.
- Evidence instrumentation boundary: generated tests can be instrumented with `evidence_tracker`, then converted back to plain Playwright for export.
- Fixture inference by body scan: `_ensure_evidence_tracker_fixture()` uses local function-body text to infer required pytest fixtures without parsing the AST.
- Lightweight import management: `inject_import()` inserts imports idempotently and respects a leading module docstring.
- POM/test distinction: class-method rewriting deliberately skips classes whose names start with `Test` or end with `Test`.

## Side Effects and State

- No module-level mutable state.
- No classes or stored configuration.
- No direct file, network, subprocess, or test-run side effects.
- All transformations are deterministic for a given input string and argument set.

## B-021 + B-022 Changes (2026-07-20)

- `_normalize_test_function_names(code)` — renames purely descriptive test names to include condition_ref number (e.g., `test_view_cart` → `test_tc01_05_view_cart`). Tests already numbered are left unchanged.
- `replace_token_in_line()` — passes through `expect(...)` expressions as-is (URL assertions from B-021) instead of wrapping in `evidence_tracker.*()` calls.
