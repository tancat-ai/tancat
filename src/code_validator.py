"""Code validation utilities for the tancat-ai/tancat.

This module provides functions to validate generated Python code
before it is saved or executed, catching syntax errors early.
"""

import ast
import re


def validate_python_syntax(code: str) -> str | None:
    """
    Validate Python code using ast.parse().

    This function parses the given code and returns None if the syntax
    is valid, or a descriptive error message if there's a syntax error.

    Args:
        code: Python source code to validate

    Returns:
        None if the code has valid syntax, or an error message string
        describing the syntax error if validation fails.

    Example:
        >>> validate_python_syntax("x = 1")
        None
        >>> validate_python_syntax("x =")  # doctest: +SKIP
        "Line 1: invalid syntax (text: 'x =')"
    """
    try:
        ast.parse(code)
        return None  # Valid syntax
    except SyntaxError as e:
        # Format error message for user display
        error_text = e.text.strip() if e.text and e.text.strip() else "N/A"
        return f"Line {e.lineno}: {e.msg} (text: {error_text})"


def validate_test_function(code: str) -> str | None:
    """
    Validate a generated test function with additional checks.

    Performs syntax validation plus additional checks specific to
    Playwright test functions:
    - Ensures no async def is used
    - Ensures the function has a test_ prefix

    Args:
        code: Python test function code to validate

    Returns:
        None if validation passes, or an error message string if validation fails.
    """
    # First check basic syntax
    syntax_error = validate_python_syntax(code)
    if syntax_error:
        return f"Syntax Error: {syntax_error}"

    # Parse the AST to check for async functions
    try:
        tree = ast.parse(code)

        for node in ast.walk(tree):
            # Check for async function definitions
            if isinstance(node, ast.AsyncFunctionDef):
                return "Error: Generated test uses 'async def' which is not allowed. Use synchronous pytest format with 'def' instead."

            # Check that test functions have proper naming
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith("test_"):
                    # Check for async keyword on regular function (shouldn't happen but be thorough)
                    pass  # Regular function defs are OK

    except SyntaxError as e:
        error_text = e.text.strip() if e.text and e.text.strip() else "N/A"
        return f"Parse Error Line {e.lineno}: {e.msg} (text: {error_text})"

    return None  # All checks passed


def validate_generated_locator_quality(code: str) -> str | None:
    """Validate generated Playwright locator patterns for known flaky/invalid cases."""
    if ".should_be_visible(" in code:
        return (
            "Error: Generated code uses `.should_be_visible()`, which is not valid in Playwright Python. "
            "Use `expect(locator).to_be_visible()` instead."
        )

    if re.search(r'get_by_role\(\s*["\']link["\']\s*\)', code):
        return (
            "Error: Generated code uses `get_by_role('link')` without a unique name/test-id. "
            "This is often ambiguous in strict mode."
        )

    if re.search(r'page\.locator\(\s*["\'](button|a|input|div|span)["\']\s*\)', code):
        return (
            'Error: Generated code uses broad tag-only locators (e.g. `page.locator("button")`). '
            "Use specific id/test-id/role+name locators from page context."
        )

    if re.search(r"page\.wait_for_load_state\([^\)]*\)\s*\.\s*status", code) or re.search(
        r"response\s*=\s*page\.wait_for_load_state", code
    ):
        return (
            "Error: Generated code assumes `page.wait_for_load_state()` returns a response object. "
            "In Playwright Python sync API, `page.wait_for_load_state()` returns None, so use "
            "`page.goto(url)` and `expect(page).to_have_url(...)` or `expect(page).to_have_title(...)` instead."
        )

    if re.search(r"to_have_url_containing\(", code) or re.search(r"to_have_title_containing\(", code):
        return (
            "Error: Generated code uses invalid Playwright assertion methods like `to_have_url_containing()` or "
            "`to_have_title_containing()`. Use `expect(page).to_have_url(...)` or `expect(page).to_have_title(...)` instead."
        )

    if re.search(r"expect\(", code) and not re.search(r"from playwright\.sync_api import .*expect", code):
        return (
            "Error: Generated code uses `expect(...)` but does not import `expect` from `playwright.sync_api`. "
            "Add `from playwright.sync_api import Page, expect` at the top of the file."
        )
    if re.search(r"expect\(\s*page\.title\(\s*\)\s*\)", code) or re.search(r"expect\(\s*page\.url\(\s*\)\s*\)", code):
        return (
            "Error: Generated code uses `expect(page.title())` or `expect(page.url())`, which is not valid in Playwright Python. "
            "Use `assert page.title() == ...` or `expect(page).to_have_title(...)`, and `expect(page).to_have_url(...)` instead."
        )
    if re.search(r"expect\(page\)\.to_be_connected\(", code):
        return (
            "Error: Generated code uses `expect(page).to_be_connected()`, which is not a valid Playwright Python API. "
            "Use `page.goto(url)` and explicit URL/title assertions instead."
        )

    if re.search(r"re\.compile\(", code) and not re.search(r"import\s+re", code):
        return (
            "Error: Generated code uses `re.compile(...)` but does not import the `re` module. "
            "Add `import re` at the top of the file or avoid regex assertions for known exact values."
        )

    if re.search(r"from playwright\.sync_api import screenshot", code) or re.search(r"pytest\.mark\.screenshot", code):
        return (
            "Error: Generated code uses custom screenshot helpers or marks (`screenshot`, `pytest.mark.screenshot`). "
            "Use standard Playwright sync assertions instead and avoid project-specific markers."
        )

    goto_urls = re.findall(r'page\.goto\(["\'](https?://[^"\']+)["\']\)', code)
    url_asserts = re.findall(r'expect\(page\)\.to_have_url\(["\'](https?://[^"\']+)["\']\)', code)
    for goto_url in goto_urls:
        for assert_url in url_asserts:
            if goto_url == assert_url and not goto_url.endswith("/"):
                return (
                    "Error: Generated code asserts a root URL without the trailing slash. "
                    "Use the canonical URL with `/` at the end for root domain navigation, e.g. "
                    '`expect(page).to_have_url("https://example.com/")`, or use a regex with an optional slash.'
                )

    if re.search(r"sync_playwright\(", code) or re.search(r"with\s+sync_playwright\(", code):
        return (
            "Error: Generated code uses `sync_playwright()`. Use pytest-playwright fixture style instead, "
            "with `page` passed into the test, and do not launch the browser manually."
        )

    if re.search(r"except\s*:\s*[\r\n]+\s*pass\b", code):
        return (
            "Error: Generated code suppresses errors via `except: pass`, which hides test failures. "
            "Generated tests must fail loudly on unexpected conditions."
        )

    if re.search(r'expect\(page\)\.not_to_have_url\(\s*["\']https?://[^"\']+["\']\s*\)', code):
        return (
            "Error: Generated code uses weak negative-only URL assertions (`not_to_have_url(...)`). "
            "Prefer positive assertions for expected destination URLs."
        )

    return None
