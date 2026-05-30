# `src/code_validator.py`

## High-Level Purpose

Validates generated Python test code before it is saved or executed. Catches syntax errors early via `ast.parse()` and detects known Playwright anti-patterns that LLMs commonly generate.

## Module Metadata

- **Lines:** 174
- **Imports:** `ast`, `re`

## Functions

### `validate_python_syntax(code: str) -> str | None`
Uses `ast.parse()` to validate Python syntax. Returns `None` if valid, or a descriptive error string with line number and message.

### `validate_test_function(code: str) -> str | None`
Extended validation for test functions:
1. Runs `validate_python_syntax()` first
2. Walks AST to detect `async def` (not allowed — must use sync pytest format)
3. Validates test function naming convention (`test_` prefix)

### `validate_generated_locator_quality(code: str) -> str | None`
Detects known flaky/invalid Playwright patterns. Returns `None` if all checks pass, or an error message. Checks for:

| Anti-pattern | Error |
|--------------|-------|
| `.should_be_visible()` | Not valid in Playwright Python — use `expect(locator).to_be_visible()` |
| `get_by_role('link')` without name | Ambiguous in strict mode |
| `page.locator("button")` — bare tag selectors | Too broad — use specific locators |
| `page.wait_for_load_state().status` | Returns `None`, not a response object |
| `to_have_url_containing()` / `to_have_title_containing()` | Invalid assertion methods |
| `expect(...)` without importing `expect` | Missing import |
| `expect(page.title())` / `expect(page.url())` | Not valid — use `expect(page).to_have_title(...)` |
| `expect(page).to_be_connected()` | Not a valid Playwright assertion |
| `re.compile(...)` without `import re` | Missing import |
| `screenshot` custom helpers/marks | Project-specific markers not available |
| Root URL assertion without trailing `/` | Use canonical URL with `/` |
| `sync_playwright()` | Use pytest-playwright fixture style |
| `except: pass` | Hides test failures |
| `not_to_have_url(...)` | Weak negative-only assertions |

## Key Design Decisions
- **AST-based validation** — uses `ast.parse()` for reliable syntax checking
- **Pattern-based quality checks** — regex-based detection of known LLM hallucination patterns
- **Fail-fast** — returns first error found; does not accumulate multiple errors

## Dependencies
- No project-internal dependencies — standalone validation module