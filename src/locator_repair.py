"""Locator repair — surgical replacement of a broken locator in a generated test line.

Provides file-level surgery that replaces only the locator string while
preserving the surrounding action (`.click()`, `.fill()`, etc).

Design-time only — not used at test runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocatorPatch:
    """Describes a single locator replacement.

    Attributes:
        original_locator: The broken locator string extracted from the error.
        repaired_locator: The corrected locator string (e.g., from codegen).
        line_number: 1-based line in the generated test to patch.
        test_file: Path to the generated test file.
    """

    original_locator: str
    repaired_locator: str
    line_number: int
    test_file: str | Path


@dataclass
class LocatorRepairError(Exception):
    """Raised when the target locator could not be found on the expected line."""

    line_number: int
    expected_locator: str
    actual_line: str


# Regex that splits a playwright chained call into the locator part and the
# action part.  It captures the argument inside .locator("...") — supporting
# both single and double quotes, and escaped quotes inside.
_LOCATOR_ACTION_SPLIT = re.compile(
    r'(.+\.locator\()(["\'])(.*?)\2(\)\.(.+))',
    re.DOTALL,
)


def _find_locator_action_line(
    source: str,
    line_number: int,
    original_locator: str,
) -> tuple[int, str]:
    """Return (0-based index, raw_line) for the line containing *original_locator*.

    Searches a window around *line_number* (reported error line) because
    Playwright error line numbers don't always match the locator call line.

    Raises:
        LocatorRepairError: if the locator string is not found nearby.
    """
    lines = source.splitlines()
    # Search +/- 10 lines around the reported line
    start = max(0, line_number - 11)
    end = min(len(lines), line_number + 9)

    for offset in range(start, end):
        # Check the locator string appears in this line
        if original_locator in lines[offset]:
            return (offset, lines[offset])

    # Fallback: search entire file
    for offset, line in enumerate(lines):
        if original_locator in line:
            return (offset, line)

    raise LocatorRepairError(
        line_number=line_number,
        expected_locator=original_locator,
        actual_line="(not found in file)",
    )


def apply_patch(patch: LocatorPatch) -> str:
    """Apply a locator patch to the test source and return the patched source.

    The function finds the line containing *original_locator*, replaces only the
    locator string inside `.locator("...")`, and preserves the action (`.click()`,
    `.fill()`, etc.).

    Args:
        patch: The locator patch to apply.

    Returns:
        The full source with the locator replaced.

    Raises:
        LocatorRepairError: if the original locator cannot be found.
    """
    test_path = Path(patch.test_file)
    source = test_path.read_text(encoding="utf-8")

    (line_idx, raw_line) = _find_locator_action_line(
        source,
        patch.line_number,
        patch.original_locator,
    )

    # Try to match the .locator(...) pattern and replace only the locator string
    match = _LOCATOR_ACTION_SPLIT.search(raw_line)
    if match:
        before_quote = match.group(1)  # e.g. 'page.locator('
        quote_char = match.group(2)  # '"' or "'"
        _old_locator = match.group(3)  # discarded — we trust the patch
        after_quote = match.group(4)  # e.g. ').click()'
        # Reconstruct with the repaired locator
        new_line = f"{before_quote}{quote_char}{patch.repaired_locator}{quote_char}{after_quote}"
    else:
        # Fallback: simple string replace for the original_locator on this line
        new_line = raw_line.replace(patch.original_locator, patch.repaired_locator)

    lines = source.splitlines()
    lines[line_idx] = new_line
    return "\n".join(lines)


def apply_patch_to_file(patch: LocatorPatch) -> None:
    """Apply a locator patch and write the result back to disk."""
    patched_source = apply_patch(patch)
    test_path = Path(patch.test_file)
    test_path.write_text(patched_source, encoding="utf-8")


def extract_locator_from_line(line: str) -> str | None:
    """Extract the locator string from a single line of test code.

    Looks for `.locator("...")` and returns the locator string.

    Args:
        line: A single line of Python/test code.

    Returns:
        The locator string (e.g., ``"get_by_role('heading', name='Products')")``)
        or ``None`` if no locator pattern is found.
    """
    match = _LOCATOR_ACTION_SPLIT.search(line)
    if match:
        return match.group(3)
    return None
