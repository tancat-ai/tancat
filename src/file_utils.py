"""Helper functions for file operations in the Playwright test generator."""

import re
from datetime import datetime
from pathlib import Path

from src.code_validator import validate_python_syntax


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe filename segment.

    Examples:
        >>> slugify("Add Driver Flow")
        'add_driver_flow'
        >>> slugify("User Story #123 (Login)")
        'user_story_123_login'
        >>> slugify("Special!@#Chars")
        'special_chars'
        >>> slugify("")
        'unnamed'
        >>> slugify("!!!")
        'unnamed'
        >>> slugify("__Test__")
        'test'
        >>> slugify("Test   String")
        'test_string'
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9_]", "_", text)
    text = text.strip("_")
    text = re.sub(r"_+", "_", text)
    if not text:
        text = "unnamed"
    return text


def save_generated_test(
    test_code: str,
    story_text: str = "",
    base_url: str = "",
    output_dir: str = "generated_tests",
) -> str:
    """
    Save test code to <output_dir>/test_YYYYMMDD_HHMMSS_<slug>.py

    Args:
        test_code:  The generated test code as a string
        story_text: User story text — used for the filename slug
        base_url:   Recorded in file header comment only
        output_dir: Output directory (default: generated_tests)

    Returns:
        Absolute path to the saved file
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    story_slug = slugify(story_text[:50]) if story_text else "test"
    filename = f"test_{timestamp}_{story_slug}.py"
    file_path = output_path / filename
    validation_error = validate_python_syntax(test_code)
    if validation_error:
        raise ValueError(f"Generated code failed syntax validation: {validation_error}")

    header = f'''"""
Auto-generated Playwright test
Generated: {datetime.now().isoformat()}
Base URL:  {base_url or "Not specified"}
"""

'''
    file_path.write_text(header + test_code, encoding="utf-8")
    return str(file_path.absolute())


def normalise_code_newlines(code: str) -> str:
    """Restore missing newlines in LLM-generated code.

    Occasionally the LLM response has newlines stripped between import
    statements, producing unparseable output like:
        from playwright.sync_api import Pageimport pytestimport os

    This function inserts a newline before any ``import`` or ``from``
    keyword that is not already at the start of a line.

    Args:
        code: Raw code string from the LLM

    Returns:
        Code string with newlines restored before import statements

    Examples:
        >>> normalise_code_newlines("import osimport re")
        'import os\\nimport re'
        >>> normalise_code_newlines("from pathlib import Pathimport os")
        'from pathlib import Path\\nimport os'
        >>> normalise_code_newlines("import os\\nimport re")
        'import os\\nimport re'
    """
    # Insert a newline before `import ` or `from ` when preceded by a character
    # that indicates it was merged (like a letter, number, or closing punctuation).
    # We use a lookbehind to ensure we don't split inside string literals if possible,
    # but the primary goal is to catch the 'merged' boundary.
    code = re.sub(r"([a-zA-Z0-9_)'\"\]\}])(?=import |from )", r"\1\n", code)
    return code
