"""Locator repair — surgical replacement of a broken locator in a generated test line.

Provides file-level surgery that replaces only the locator string while
preserving the surrounding action (`.click()`, `.fill()`, etc).
Also launches headed Playwright codegen for interactive locator capture.

Design-time only — not used at test runtime.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
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
class SetupScriptResult:
    """Result of running prerequisite steps before a codegen session."""

    state_file: str | None
    page_url: str | None


def translate_setup_step_to_python(step: str) -> list[str]:
    """Translate a generated test step line into Playwright setup script lines."""
    stripped = step.strip()
    lines: list[str] = []

    pom_click = re.match(
        r"(?:home_page|category_product_page|cart_page|products_page|generated_page)\.click\(['\"]([^'\"]+)['\"]\)",
        stripped,
    )
    if pom_click:
        text = pom_click.group(1).replace("'", "\\'")
        lines.extend(
            [
                "        try:",
                f"            link = page.get_by_role('link', name='{text}').first",
                "            href = link.get_attribute('href')",
                "            if href:",
                "                from urllib.parse import urljoin",
                "                page.goto(urljoin(page.url, href))",
                "            else:",
                "                link.click(timeout=5000)",
                "        except Exception:",
                "            try:",
                f"                page.get_by_role('button', name='{text}').click(timeout=5000)",
                "            except Exception:",
                f"                hidden = page.locator('a').filter(has_text='{text}').first",
                "                href = hidden.get_attribute('href')",
                "                if href:",
                "                    from urllib.parse import urljoin",
                "                    page.goto(urljoin(page.url, href))",
                "                else:",
                f"                    page.locator('text={text}').first.click(force=True, timeout=5000)",
            ]
        )
        return lines

    pom_fill = re.match(
        r"(?:home_page|category_product_page|cart_page|products_page|generated_page)"
        r"\.fill\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]\)",
        stripped,
    )
    if pom_fill:
        field = pom_fill.group(1).replace("'", "\\'")
        value = pom_fill.group(2).replace("'", "\\'")
        lines.extend(
            [
                "        try:",
                f"            page.get_by_label('{field}').fill('{value}', timeout=5000)",
                "        except Exception:",
                f"            page.get_by_placeholder('{field}').fill('{value}', timeout=5000)",
            ]
        )
        return lines

    # Handle evidence_tracker.navigate('url') — translate to page.goto
    navigate_match = re.match(
        r"(?:evidence_tracker\.navigate|page\.goto)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        stripped,
    )
    if navigate_match:
        url = navigate_match.group(1).replace("'", "\\'")
        lines.append(f"        page.goto('{url}')")
        return lines

    label_match = re.search(r"label=['\"]([^'\"]+)['\"]", stripped)
    if label_match and "evidence_tracker" in stripped:
        label = label_match.group(1).replace("'", "\\'")
        lines.append(f"        try: page.get_by_text('{label}').click(timeout=5000)")
        lines.append("        except Exception as e: print('Label click failed:', e)")
        return lines

    role_match = re.search(
        r"\.get_by_role\(\s*['\"]([^'\"]+)['\"].*?name=\s*['\"]([^'\"]+)['\"]",
        stripped,
    )
    if role_match:
        role = role_match.group(1)
        name = role_match.group(2).replace("'", "\\'")
        if ".fill(" in stripped:
            val_match = re.search(r"\.fill\(['\"]([^'\"]+)['\"]", stripped)
            val = val_match.group(1).replace("'", "\\'") if val_match else "test"
            lines.append(f"        page.get_by_role('{role}', name='{name}').fill('{val}', timeout=5000)")
        else:
            lines.append(f"        page.get_by_role('{role}', name='{name}').click(timeout=5000)")
        return lines

    loc_match = re.search(r"locator\(['\"]([^'\"]+)['\"]", stripped)
    if loc_match:
        val = loc_match.group(1).replace("'", "\\'")
        if ".fill(" in stripped:
            fill_val_match = re.search(r"\.fill\(['\"]([^'\"]+)['\"]", stripped)
            fill_val = fill_val_match.group(1).replace("'", "\\'") if fill_val_match else "test"
            lines.append(f"        try: page.locator('{val}').fill('{fill_val}', timeout=5000)")
        else:
            lines.append(f"        try: page.locator('{val}').click(timeout=5000)")
        lines.append("        except Exception as e: print('Locator action failed:', e)")
        return lines

    return lines


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


def run_codegen_session(url: str, timeout_seconds: int = 120, state_file: str | None = None) -> str | None:
    """Launch headed Playwright codegen and capture the first locator from the recorded script.

    Args:
        url: URL to navigate to.
        timeout_seconds: Maximum time to wait for a click.
        state_file: Optional path to a storage state JSON file to load.

    Returns:
        The locator string captured from the clicked element, or None.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp_dir = tempfile.gettempdir()
    output_file = str(Path(tmp_dir) / f"repair_locator_{timestamp}.py")

    cmd = ["playwright", "codegen", "--output", output_file]
    if state_file:
        cmd.extend(["--load-storage", state_file])
    cmd.append(url)

    # Use DEVNULL to avoid pipe deadlocks with headed browser GUI process on Windows.
    # The browser writes to output_file directly, we don't need its stdout/stderr.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        return None

    if not Path(output_file).exists():
        return None

    content = Path(output_file).read_text(encoding="utf-8")
    try:
        Path(output_file).unlink(missing_ok=True)
    except OSError:
        pass

    locator_pattern = re.compile(
        r'\.(?:locator|get_by_test_id|get_by_label|get_by_text|get_by_title|get_by_placeholder)\(\s*["\']([^"\']+)["\']',
    )
    match = locator_pattern.search(content)
    if match:
        return match.group(1)

    role_pattern = re.compile(r'\.get_by_role\(\s*["\']([^"\']+)["\'].*?name=\s*["\']([^"\']+)["\']')
    role_match = role_pattern.search(content)
    if role_match:
        role = role_match.group(1)
        name = role_match.group(2)
        return f"get_by_role('{role}', name='{name}')"

    return None


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
