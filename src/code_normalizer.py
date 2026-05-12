"""Deterministic normalization transforms for LLM-generated test code.

Extracted from code_postprocessor.py to separate normalization logic
into its own independently testable module.
"""

from __future__ import annotations

import re

__all__ = [
    "convert_standalone_placeholders",
    "replace_remaining_placeholders",
    "strip_pages_needed_block",
    "fix_module_scope_indentation",
    "fix_indentation",
    "dedent_indented_test_blocks",
    "deduplicate_skip_calls",
    "replace_bare_ellipsis",
    "ensure_test_navigation",
]

# Regex to match standalone placeholder lines
_STANDALONE_PLACEHOLDER_RE = re.compile(
    r"^(\s*)\{\{(CLICK|FILL|GOTO|URL|ASSERT):([^}]+)\}\}\s*$",
    re.MULTILINE,
)


def convert_standalone_placeholders(code: str) -> str:
    """Convert standalone placeholder lines and unwrap evidence_tracker-wrapped placeholders."""
    lines = code.splitlines()
    output_lines: list[str] = []

    for line in lines:
        m = _STANDALONE_PLACEHOLDER_RE.match(line)
        if m:
            indent, action, description = m.group(1), m.group(2), m.group(3)
            token = f"{{{{{action}:{description}}}}}"
            output_lines.append(f"{indent}{token}")
            continue

        wrapped_pattern = re.match(
            r"^(\s*)evidence_tracker\.(click|fill|navigate|assert_visible)\(\s*\{\{(CLICK|FILL|GOTO|URL|ASSERT):([^}]+)\}\}",
            line,
        )
        if wrapped_pattern:
            indent = wrapped_pattern.group(1)
            action = wrapped_pattern.group(3)
            description = wrapped_pattern.group(4)
            token = f"{{{{{action}:{description}}}}}"
            output_lines.append(f"{indent}{token}")
            continue

        output_lines.append(line)

    return "\n".join(output_lines)


def replace_remaining_placeholders(code: str) -> str:
    """Replace any unresolved {{ACTION:description}} placeholders with pytest.skip()."""
    placeholder_pattern = re.compile(r"\{\{[A-Z_]+:(.+?)\}\}", re.DOTALL)

    def _is_inside_quotes(text_before: str) -> bool:
        in_single = False
        in_double = False
        for ch in text_before:
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
        return in_single or in_double

    output_lines: list[str] = []
    for line in code.splitlines():
        if "{{" not in line:
            output_lines.append(line)
            continue

        indent = line[: len(line) - len(line.lstrip())]
        the_content = line.strip()

        matches = list(placeholder_pattern.finditer(the_content))
        if not matches:
            output_lines.append(line)
            continue

        all_inside_quotes = all(_is_inside_quotes(the_content[: match.start()]) for match in matches)
        if all_inside_quotes:
            output_lines.append(line)
            continue

        has_function_call = any(
            not _is_inside_quotes(the_content[: match.start()])
            and re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", the_content[: match.start()])
            and ")" in the_content[match.end() :]
            for match in matches
        )

        if has_function_call:
            preview = ", ".join(match.group(0) for match in matches[:3])
            reason = f"Unresolved placeholder in this step. {preview}"
            output_lines.append(f"{indent}pytest.skip({reason!r})")
        else:

            def _handle_match(m: re.Match) -> str:
                text = m.group(0)
                return f'pytest.skip("Unresolved placeholder: {text}")'

            new_content = placeholder_pattern.sub(_handle_match, the_content)
            output_lines.append(f"{indent}{new_content}")
    return "\n".join(output_lines)


def strip_pages_needed_block(code: str) -> str:
    """Remove trailing skeleton metadata comments from final generated code."""
    cleaned_lines: list[str] = []
    inside_pages_needed = False

    for line in code.splitlines():
        stripped = line.strip()
        if stripped == "# PAGES_NEEDED:":
            inside_pages_needed = True
            continue
        if inside_pages_needed:
            if not stripped or stripped.startswith("# -"):
                continue
            inside_pages_needed = False

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def fix_module_scope_indentation(code: str) -> str:
    """Ensure imports, class definitions, and test functions are at module scope."""
    module_level_keywords = ("import ", "from ", "def test_", "class ", "@pytest.mark")
    lines = code.splitlines()
    fixed: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if any(stripped.startswith(kw) for kw in module_level_keywords):
            fixed.append(stripped)
        else:
            fixed.append(line)
    return "\n".join(fixed)


def fix_indentation(code: str) -> str:
    """Fix inconsistent indentation inside test functions and class methods."""
    lines = code.splitlines()
    updated_lines: list[str] = []
    inside_function = False
    func_indent = 0
    previous_significant_indent = 0
    previous_significant_line = ""

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if re.match(r"^\s*def\s+", line):
            inside_function = True
            func_indent = indent + 4
            previous_significant_indent = indent
            previous_significant_line = stripped
            updated_lines.append(line)
            continue

        if re.match(r"^\s*class\s+", line):
            inside_function = False
            previous_significant_indent = indent
            previous_significant_line = stripped
            updated_lines.append(line)
            continue

        if inside_function and stripped:
            if stripped.startswith("#"):
                comment_indent = func_indent if indent <= func_indent else indent
                updated_lines.append(" " * comment_indent + stripped)
                previous_significant_indent = comment_indent
                previous_significant_line = stripped
                continue

            if indent < func_indent and not re.match(r"^\s*(def |class |@|import |from )", line):
                updated_lines.append(" " * func_indent + stripped)
                previous_significant_indent = func_indent
                previous_significant_line = stripped
                continue

            accidental_extra_indent = (
                indent > func_indent
                and previous_significant_indent == func_indent
                and not previous_significant_line.rstrip().endswith(":")
                and not re.match(r"^(elif |else:|except\b|finally:)", stripped)
            )
            if accidental_extra_indent:
                updated_lines.append(" " * func_indent + stripped)
                previous_significant_indent = func_indent
                previous_significant_line = stripped
                continue

        if stripped:
            previous_significant_indent = indent
            previous_significant_line = stripped

        updated_lines.append(line)

    return "\n".join(updated_lines)


def dedent_indented_test_blocks(code: str) -> str:
    """Dedent malformed top-level test blocks that were shifted right as a unit."""
    lines = code.splitlines()
    updated_lines: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if indent > 0 and re.match(r"^(?:@pytest\.mark\.evidence|def\s+test_)", stripped):
            block_indent = indent
            while index < len(lines):
                current = lines[index]
                current_stripped = current.lstrip()
                current_indent = len(current) - len(current_stripped)

                if not current_stripped:
                    updated_lines.append("")
                    index += 1
                    continue

                if current_indent < block_indent:
                    break

                updated_lines.append(current[block_indent:])
                index += 1
            continue

        updated_lines.append(line)
        index += 1

    return "\n".join(updated_lines)


def deduplicate_skip_calls(code: str) -> str:
    """Remove duplicate consecutive pytest.skip() calls in test blocks."""
    lines = code.splitlines()
    updated_lines: list[str] = []
    pending_skips: list[str] = []
    in_test = False

    def _flush_skips() -> None:
        if pending_skips:
            updated_lines.append(pending_skips[0])
            pending_skips.clear()

    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(line.lstrip())]

        if stripped.startswith("def test_"):
            _flush_skips()
            in_test = True
            updated_lines.append(line)
            continue

        if in_test and stripped and indent == 0:
            _flush_skips()
            if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("@"):
                in_test = False

        if in_test and stripped.startswith("pytest.skip("):
            pending_skips.append(line)
            continue

        _flush_skips()
        updated_lines.append(line)

    _flush_skips()
    return "\n".join(updated_lines)


def replace_bare_ellipsis(code: str) -> str:
    """Replace bare `...` (ellipsis) statements in test functions with pytest.skip()."""
    lines = code.splitlines()
    updated_lines: list[str] = []
    inside_test = False

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if re.match(r"^def\s+test_\w+\(", stripped):
            inside_test = True
            updated_lines.append(line)
            continue

        if inside_test and indent == 0 and stripped:
            if re.match(r"^(def |class |@)", stripped):
                inside_test = False

        if inside_test and stripped == "...":
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if not next_line.startswith("#"):
                updated_lines.append(f"{' ' * indent}pytest.skip('Test body not generated (unresolved placeholders)')")
                continue

        updated_lines.append(line)

    if "pytest.skip(" in "\n".join(updated_lines):
        target = "import pytest"
        if not any(line_item.strip() == target for line_item in updated_lines):
            for idx, line in enumerate(updated_lines):
                if line.startswith("from ") or line.startswith("import "):
                    updated_lines.insert(idx, target)
                    break

    return "\n".join(updated_lines)


def ensure_test_navigation(code: str, target_url: str | None = None) -> str:
    """Inject an initial navigation to the given URL if a test lacks navigation."""
    if target_url:
        url = target_url
    else:
        pages_block = re.search(r"# PAGES_NEEDED:\n((?:# https?://.*\n?)+)", code)
        if not pages_block:
            return code

        first_url = re.search(r"https?://[^\s\n]+", pages_block.group(1))
        if not first_url:
            return code

        url = first_url.group(0)

    def _inject_nav(match: re.Match[str]) -> str:
        body = match.group(2)
        if "navigate(" in body or "goto(" in body:
            return match.group(0)

        indent = "    "
        nav_line = f'\n{indent}evidence_tracker.navigate("{url}")\n{indent}dismiss_consent_overlays(page)'
        return f"{match.group(1)}{nav_line}{body}"

    return re.sub(
        r"(def test_\w+\(page: Page, evidence_tracker\) -> None:)(.*?(?=\n\n|\ndef |\Z))",
        _inject_nav,
        code,
        flags=re.S,
    )
