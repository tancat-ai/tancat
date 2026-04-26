"""Pure code-string transformation helpers extracted from TestOrchestrator."""

from __future__ import annotations

import re

# Patterns that match common LLM reasoning/thinking text that leaks into code output.
# These are English sentences, questions, or self-references that are not valid Python.
_LLM_REASONING_PREFIXES = (
    "Wait,",
    "Note,",
    "Actually,",
    "Hmm,",
    "Okay,",
    "Sure,",
    "Let's ",
    "That's ",
    "This is ",
    "The prompt ",
    "The example ",
    "I will ",
    "I need ",
    "I should ",
    "All constraints",
    "Matches all",
    "Output matches",
    "Proceeds",
    "Self-Correction",
    "Refinement",
    "One minor",
    "One check",
    "Final check",
    "Self check",
    "Edge case",
    "Corner case",
    "In the example",
    "To be safe",
    "To avoid",
)

_LLM_REASONING_PATTERNS = [
    re.compile(r"^\s*#\s*[A-Z][a-z]+,\s", re.IGNORECASE),  # # Note, ... # Wait,
    re.compile(r"^\s*(?:Wait|Note|Actually|Hmm|Okay|Sure|Let's|That's|This is)\b", re.IGNORECASE),
    re.compile(r"^\s*# - \d+\.\s+[A-Z][a-z]+,\s"),  # numbered list items that are reasoning
]


def _is_llm_reasoning_line(line: str) -> bool:
    """Return True if the line looks like LLM reasoning text rather than Python code.

    Heuristics:
    - Starts with common LLM reasoning prefixes
    - Is a short English sentence (under 80 chars) with punctuation that Python
      code would not normally have at the start of a line (commas after sentence starters)
    - Contains no valid Python keywords and is not a comment, string, or docstring
    """
    stripped = line.strip()
    if not stripped:
        return False

    # Skip lines that are valid Python constructs
    python_keywords = (
        "def ",
        "class ",
        "import ",
        "from ",
        "return ",
        "if ",
        "elif ",
        "else:",
        "for ",
        "while ",
        "try:",
        "except",
        "finally:",
        "with ",
        "assert ",
        "raise ",
        "yield ",
        "lambda ",
        "pass",
        "break",
        "continue",
        "@pytest",
        "@",
        "# PAGES_NEEDED",
        "# - https",
        "# -http",
        '"""',
        "'''",
        "pytest.",
        "evidence_tracker",
        "dismiss_consent",
        "page.",
        "self.",
    )
    if any(stripped.startswith(kw) for kw in python_keywords):
        return False

    # Check for LLM reasoning prefixes
    for prefix in _LLM_REASONING_PREFIXES:
        if stripped.startswith(prefix):
            return True

    # Check for reasoning patterns
    for pattern in _LLM_REASONING_PATTERNS:
        if pattern.match(stripped):
            return True

    # Heuristic: short lines with sentence-like punctuation that aren't Python
    if len(stripped) < 80 and any(c in stripped for c in (",", ".")):
        # Lines that start with a capital letter followed by a comma are likely reasoning
        if re.match(r"^[A-Z][a-z]+,", stripped):
            # But allow valid Python like "Page," in type hints (unlikely at line start)
            if not re.match(r"^[A-Z][A-Za-z]*\s*[:=]", stripped):
                return True

    return False


def _strip_llm_reasoning_text(code: str) -> str:
    """Remove lines that look like LLM reasoning/thinking text.

    LLMs sometimes output their internal chain-of-thought as part of the code
    block. This function detects and removes such lines while preserving valid
    Python code, comments, and blank lines.
    """
    lines = code.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        if _is_llm_reasoning_line(line):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def normalise_generated_code(code: str, consent_mode: str = "auto-dismiss", target_url: str = "") -> str:
    """Apply small deterministic fixes to common skeleton-generation mistakes."""
    fixed_code = code

    # First: strip LLM reasoning text that may have leaked into the code block
    fixed_code = _strip_llm_reasoning_text(fixed_code)

    # Clean up malformed decorators if the LLM added spaces
    fixed_code = re.sub(r"@\s*pytest\s*\.\s*mark\s*\.\s*evidence", "@pytest.mark.evidence", fixed_code)

    # Always inject pytest at module level when the code uses any pytest constructs.
    # _inject_import handles deduplication by removing any existing copies first.
    if "pytest.skip(" in fixed_code or "pytest.mark." in fixed_code:
        fixed_code = inject_import(fixed_code, "import pytest")
    if re.search(r"\bPage\b", fixed_code) or "expect(" in fixed_code:
        fixed_code = inject_import(fixed_code, "from playwright.sync_api import Page, expect")

    # The tool ships an `evidence_tracker` fixture for generated tests.
    # Some LLMs hallucinate a non-existent `evidence_launcher` fixture name.
    fixed_code = re.sub(r"\bevidence_launcher\b", "evidence_tracker", fixed_code)

    # Ensure evidence_tracker is used for common methods even if LLM forgot
    fixed_code = re.sub(r"page\.goto\(", "evidence_tracker.navigate(", fixed_code)
    fixed_code = re.sub(r"self\.page\.goto\(", "evidence_tracker.navigate(", fixed_code)

    # Some models hallucinate a slash between `pytest.mark` and the marker name.
    # Example: `@pytest.mark/evidence(...)` which is invalid Python.
    fixed_code = re.sub(r"(?m)^\s*@pytest\.mark\s*/\s*([A-Za-z_][A-Za-z0-9_]*)", r"@pytest.mark.\1", fixed_code)

    # Some models hallucinate special constructor names (e.g. `__larry`) which
    # makes instantiation fail immediately at runtime.
    fixed_code = re.sub(
        r"(?m)^(\s*)def\s+__larry\s*\(\s*self\s*,\s*page\s*:\s*Page\s*\)\s*:\s*$",
        r"\1def __init__(self, page: Page) -> None:",
        fixed_code,
    )

    # Some models emit invalid keyword arguments when instantiating page objects.
    fixed_code = re.sub(
        r"(\b[A-Za-z_][A-Za-z0-9_]*Page)\(\s*project\s*=\s*page\s*\)",
        r"\1(page)",
        fixed_code,
    )

    # Guardrail: some models accidentally emit invalid decorator assignment lines like
    # `@pytest.markelse = None`, which breaks syntax validation. Strip any decorator
    # lines that look like attribute assignments on `pytest.mark*`.
    fixed_code = re.sub(r"(?m)^\s*@pytest\.mark\w*\s*=\s*.*\n?", "", fixed_code)

    fixed_code = re.sub(r"(def __init__\(self,\s*page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
    fixed_code = re.sub(r"(def test_[A-Za-z0-9_]*\(page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
    fixed_code = re.sub(r"(?<=:\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)
    fixed_code = re.sub(r"(?<=->\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)

    if consent_mode == "auto-dismiss":
        fixed_code = _inject_consent_helper(fixed_code)

    fixed_code = rewrite_page_references_in_class_methods(fixed_code)

    # Hallucination guard: record_condition(...) -> @pytest.mark.evidence
    # This is a bit tricky to fix automatically if the LLM put it at the end of the function.
    # But we can at least strip it to avoid runtime errors.
    fixed_code = re.sub(r"(?m)^\s*evidence_tracker\.record_condition\(.*?\)\s*$", "", fixed_code)

    # Fix misplaced closing parenthesis in evidence_tracker method calls.
    # Common LLM mistake: evidence_tracker.assert_visible(...'), label="...")
    #                          ^-- extra ) before , label=
    # Pattern: closing paren followed by comma and label= (or other kwarg)
    fixed_code = re.sub(
        r"(evidence_tracker\.\w+\([^)]*)\)'(\s*,\s*label=)",
        r"\1\2",
        fixed_code,
    )
    # Also handle nested parens like evidence_tracker.click(..., label=...)')
    fixed_code = re.sub(
        r"(evidence_tracker\.\w+\([^)]*\)[^)]*)\)'(\s*,\s*\w+=)",
        r"\1\2",
        fixed_code,
    )

    # Ensure every test starts with a navigation if none present
    fixed_code = _ensure_test_navigation(fixed_code)

    # Hallucination fix: Flatten inner functions like `def inner():` and `def run_test():`
    # DISABLED temporarily — causes indentation issues with complex LLM output
    # fixed_code = _flatten_inner_functions(fixed_code)

    # Safety net: replace any remaining unresolved {{ACTION:...}} placeholders with
    # pytest.skip() so they never cause a SyntaxError.  This catches placeholders
    # whose descriptions contain Python variable syntax (e.g. {item_name}) that
    # break the resolver's regex and therefore were never substituted.
    fixed_code = replace_remaining_placeholders(fixed_code)

    # Some models indent entire top-level test blocks after helper functions,
    # producing invalid syntax like `    @pytest.mark.evidence(...)` at module scope.
    fixed_code = _dedent_indented_test_blocks(fixed_code)

    # Fix inconsistent indentation inside test functions and class methods
    fixed_code = _fix_indentation(fixed_code)

    # Deduplicate consecutive pytest.skip() calls in the same test block
    fixed_code = _deduplicate_skip_calls(fixed_code)

    return fixed_code


def replace_token_in_line(
    line: str,
    action: str,
    token: str,
    resolved_value: str,
    duplicate_selectors: set[str],
    description: str = "",
) -> str:
    """Replace a single placeholder token within a code line."""
    stripped = line.strip()
    indent = line[: len(line) - len(line.lstrip())]
    # Duplicate selector disambiguation is handled by EvidenceTracker at runtime.
    # NOTE: Playwright auto-waits for elements to be actionable before clicking,
    # so we no longer append `:visible` to click selectors (it's invalid CSS).

    if "pytest.skip" in resolved_value:
        # If the resolution is a skip, replace the WHOLE line to ensure it executes.
        return f"{indent}{resolved_value}"

    step_label = description if description else token

    # Handle the case where the resolved value (e.g. pytest.skip) is embedded
    # inside a label= argument — the naive str.replace would produce
    # `evidence_tracker.click(..., label='pytest.skip(...)')` which is invalid.
    # Detect this pattern and replace the entire line with the skip statement.
    if "pytest.skip" in resolved_value and "label=" in stripped:
        return f"{indent}{resolved_value}"

    if action == "CLICK":
        selector_literal = resolved_value
        # NOTE: Playwright auto-waits for elements to be actionable before clicking.
        # Appending `:visible` as a CSS pseudo-selector is invalid and causes failures.
        # See: https://playwright.dev/python/docs/actionability
        if stripped == token:
            return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
        if stripped == f"{token}.click()":
            return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
        locator_only_patterns = {
            f"page.locator({token})",
            f"self.page.locator({token})",
            f"page.locator({token}).first",
            f"self.page.locator({token}).first",
        }
        locator_click_patterns = {
            f"page.locator({token}).click()",
            f"self.page.locator({token}).click()",
            f"page.locator({token}).first.click()",
            f"self.page.locator({token}).first.click()",
        }
        if stripped in locator_only_patterns or stripped in locator_click_patterns:
            return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
        # Final fallback: always produce valid evidence_tracker.click() with proper indentation
        return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"

    if action == "ASSERT":
        if stripped == token:
            return f"{indent}evidence_tracker.assert_visible({resolved_value}, label={repr(step_label)})"

        # Use regex to handle expect(page.locator(...)) regardless of content
        expect_match = re.search(r"expect\((?:self\.)?page\.locator\(.*?\)\)\.to_\w+\(.*\)", stripped)
        if expect_match:
            return f"{indent}evidence_tracker.assert_visible({resolved_value}, label={repr(step_label)})"

        locator_only_patterns = {
            f"page.locator({token})",
            f"self.page.locator({token})",
        }
        if stripped in locator_only_patterns:
            return f"{indent}evidence_tracker.assert_visible({resolved_value}, label={repr(step_label)})"
        return line.replace(token, resolved_value)

    if action == "FILL":
        if stripped == token:
            return f'{indent}evidence_tracker.fill({resolved_value}, "", label={repr(step_label)})'
        locator_only_patterns = {
            f"page.locator({token})",
            f"self.page.locator({token})",
        }
        locator_fill_patterns = {
            f'page.locator({token}).fill("")',
            f'self.page.locator({token}).fill("")',
            f"page.locator({token}).fill('')",
            f"self.page.locator({token}).fill('')",
        }
        if stripped in locator_only_patterns or stripped in locator_fill_patterns:
            return f"{indent}evidence_tracker.fill({resolved_value}, '', label={repr(step_label)})"
        # Handle cases where the LLM generates fill(token) without value arg
        fill_no_value = re.match(
            r"(evidence_tracker\.fill\()(" + re.escape(token) + r")(\s*,\s*label=)",
            stripped,
        )
        if fill_no_value:
            return re.sub(
                r"(evidence_tracker\.fill\()(" + re.escape(token) + r")(\s*,\s*label=)",
                r"\1\2, '', \3",
                stripped,
            )
        return line.replace(token, resolved_value)

    if action in {"GOTO", "URL"}:
        if stripped == token:
            return f"{indent}evidence_tracker.navigate({resolved_value})"
        goto_patterns = {
            f"page.goto({token})",
            f"self.page.goto({token})",
            f"evidence_tracker.navigate({token})",
            f'page.goto("{token}")',
            f"page.goto('{token}')",
            f'self.page.goto("{token}")',
            f"self.page.goto('{token}')",
            f'evidence_tracker.navigate("{token}")',
            f"evidence_tracker.navigate('{token}')",
        }
        if stripped in goto_patterns:
            return f"{indent}evidence_tracker.navigate({resolved_value})"
        if f'"{token}"' in line:
            return line.replace(f'"{token}"', resolved_value)
        if f"'{token}'" in line:
            return line.replace(f"'{token}'", resolved_value)
        return line.replace(token, resolved_value)

    return line.replace(token, resolved_value)


def replace_remaining_placeholders(code: str) -> str:
    """Replace any unresolved {{ACTION:description}} placeholders with pytest.skip().

    The resolver's regex uses ``[^}]+`` for the description, which means
    descriptions containing Python variable syntax such as ``{item_name}``
    break the match and the placeholder is never substituted.  Those raw
    strings are invalid Python and will cause a SyntaxError.  This method
    is the last-resort safety net applied after all other post-processing.

    When the placeholder is embedded inside a function call (e.g.
    ``evidence_tracker.fill({{FILL:x}}, label="y")``), the entire call
    is replaced with a skip statement to avoid producing invalid Python.

    Placeholders that appear inside quoted strings (e.g. inside a
    ``label='{{CLICK:basket}}'`` argument) are left untouched because they
    are metadata, not executable code.
    """
    # This regex handles nested braces like {item_name} that break the
    # resolver's simpler [^}]+ pattern.  It matches the shortest string
    # between {{ACTION: and the closing }}.
    placeholder_pattern = re.compile(r"\{\{[A-Z_]+:(.+?)\}\}", re.DOTALL)

    def _is_inside_quotes(text_before: str) -> bool:
        """Return True if the position in text_before is inside single or double quotes."""
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
        # Preserve indentation
        indent = line[: len(line) - len(line.lstrip())]
        the_content = line.strip()

        # Find all unresolved placeholders
        matches = list(placeholder_pattern.finditer(the_content))
        if not matches:
            output_lines.append(line)
            continue

        # Skip replacement if ALL matches are inside quotes (metadata only)
        all_inside_quotes = all(_is_inside_quotes(the_content[: match.start()]) for match in matches)
        if all_inside_quotes:
            output_lines.append(line)
            continue

        # Check if any placeholder is inside a function call (not inside quotes)
        has_function_call = any(
            not _is_inside_quotes(the_content[: match.start()])
            and re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", the_content[: match.start()])
            and ")" in the_content[match.end() :]
            for match in matches
        )

        if has_function_call:
            # Replace the entire line with a skip statement
            preview = ", ".join(match.group(0) for match in matches[:3])
            reason = f"Unresolved placeholder in this step. {preview}"
            output_lines.append(f"{indent}pytest.skip({reason!r})")
        else:
            # Placeholder is standalone — replace it directly
            def _handle_match(m: re.Match) -> str:
                text = m.group(0)
                return f'pytest.skip("Unresolved placeholder: {text}")'

            new_content = placeholder_pattern.sub(_handle_match, the_content)
            output_lines.append(f"{indent}{new_content}")
    return "\n".join(output_lines)


def _fix_indentation(code: str) -> str:
    """Fix inconsistent indentation inside test functions and class methods.

    The LLM sometimes emits lines without indentation inside function bodies.
    This method detects such lines and applies 4-space indentation.
    """
    lines = code.splitlines()
    updated_lines: list[str] = []
    inside_function = False
    func_indent = 0

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Detect function definition
        if re.match(r"^\s*def\s+", line):
            inside_function = True
            func_indent = indent + 4
            updated_lines.append(line)
            continue

        # Detect class definition
        if re.match(r"^\s*class\s+", line):
            inside_function = False
            updated_lines.append(line)
            continue

        # If we're inside a function and the line has less indentation
        # than expected but has content, fix it
        if inside_function and stripped and indent < func_indent:
            # Only fix if the line looks like it should be indented
            # (starts with a known keyword or is a function call)
            if not re.match(r"^\s*(def |class |@|import |from |#|$)", line):
                updated_lines.append(" " * func_indent + stripped)
                continue

        updated_lines.append(line)

    return "\n".join(updated_lines)


def _dedent_indented_test_blocks(code: str) -> str:
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


def flatten_inner_functions(code: str) -> str:
    """Remove nested 'def inner():' style wrappers and move their decorators up.

    Handles the common case where the LLM wraps test logic inside a short
    inner function (e.g. ``def inner():`` or ``def run_test():``) followed
    by a call to that function.  The inner function's body is unindented
    and placed directly inside the outer test function.
    """
    lines = code.splitlines()
    updated_lines: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect a test function that is immediately followed by a nested
        # function definition (not another test, class, or top-level block).
        if stripped.startswith("def test_") and "(" in stripped:
            updated_lines.append(line)
            i += 1

            # Look for a nested function (more indented than the test def)
            while i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()
                next_indent = len(next_line) - len(next_line.lstrip())

                # If we hit another test, class, or top-level block, stop
                if (
                    next_stripped.startswith("def test_")
                    or next_stripped.startswith("class ")
                    or next_stripped.startswith("import ")
                    or next_stripped.startswith("from ")
                    or (next_indent <= 0 and next_stripped)
                ):
                    break

                # Detect nested function definition
                if next_stripped.startswith("def ") and next_indent > 0:
                    # Collect decorators above the nested function
                    decorator_lines: list[str] = []
                    j = i - 1
                    while j >= 0 and lines[j].strip().startswith("@pytest.mark.evidence"):
                        decorator_lines.insert(0, lines[j].strip())
                        j -= 1

                    # Get the nested function name
                    func_name = next_stripped[4:].split("(", 1)[0].strip()

                    # Add decorators to the outer test
                    base_indent = " " * (len(line) - len(line.lstrip()))
                    for d_line in decorator_lines:
                        updated_lines.append(f"{base_indent}{d_line}")

                    # Skip the nested function def line
                    i += 1

                    # Process the body of the nested function
                    nested_indent = next_indent
                    while i < len(lines):
                        body_line = lines[i]
                        body_stripped = body_line.strip()
                        body_indent = len(body_line) - len(body_line.lstrip())

                        # End of nested function (back to nested_indent or less)
                        if body_stripped and body_indent <= nested_indent:
                            break

                        # Skip the call to the inner function
                        if body_indent == nested_indent and body_stripped.startswith(func_name + "("):
                            i += 1
                            continue

                        # Unindent the body to the outer test level
                        if body_stripped:
                            updated_lines.append(base_indent + body_line.lstrip())
                        else:
                            updated_lines.append("")
                        i += 1
                    continue

                # Not a nested function — just a regular line in the test body
                updated_lines.append(next_line)
                i += 1
            continue

        updated_lines.append(line)
        i += 1

    return "\n".join(updated_lines)


def inject_import(code: str, import_line: str) -> str:
    """Insert an import at the very top of the generated file.

    Always ensures the import is at module level (column 0), even if a
    malformed copy already exists somewhere deeper in the file.
    """
    lines = code.splitlines()

    # Remove any existing copy of this import line (with or without whitespace)
    stripped_target = import_line.strip()
    lines = [ln for ln in lines if ln.strip() != stripped_target]

    insert_at = 0
    if lines and lines[0].startswith("from __future__ import"):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
    lines.insert(insert_at, import_line)
    return "\n".join(lines)


def rewrite_page_references_in_class_methods(code: str) -> str:
    """Replace bare `page.` references with `self.page.` inside instance methods."""
    rewritten_lines: list[str] = []
    inside_class = False
    is_test_class = False
    class_indent = 0
    inside_instance_method = False
    method_indent = 0

    for line in code.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if stripped.startswith("class "):
            inside_class = True
            class_indent = indent
            inside_instance_method = False
            class_name = stripped[6:].split(":", 1)[0].split("(", 1)[0].strip()
            is_test_class = class_name.startswith("Test") or class_name.endswith("Test")
        elif inside_class and stripped and indent <= class_indent and not stripped.startswith("#"):
            inside_class = False
            is_test_class = False
            inside_instance_method = False

        if inside_class and not is_test_class and stripped.startswith("def "):
            signature = stripped.split("(", maxsplit=1)[1] if "(" in stripped else ""
            inside_instance_method = signature.startswith("self,") or signature.startswith("self)")
            method_indent = indent
        elif inside_instance_method and stripped and indent <= method_indent and not stripped.startswith("#"):
            inside_instance_method = False

        if inside_instance_method and "page." in line and "self.page." not in line:
            line = re.sub(r"\bpage\.", "self.page.", line)

        if inside_instance_method:
            # Check if evidence_tracker is a method parameter — if so, DON'T convert
            # to self.evidence_tracker (it's passed as an argument, not an instance attr)
            method_sig = ""
            if "(" in stripped and ")" in stripped:
                method_sig = stripped.split("(", 1)[1].split(")")[0]
            has_evidence_tracker_param = "evidence_tracker" in method_sig

            if not has_evidence_tracker_param:
                line = re.sub(r"\bevidence_tracker\.", "self.evidence_tracker.", line)

            line = re.sub(
                r"\bdismiss_consent_overlays\(\s*page\s*\)",
                "dismiss_consent_overlays(self.page)",
                line,
            )
            line = line.replace("(page)", "(self.page)")
            line = line.replace("Page(", "self.page(")

        rewritten_lines.append(line)

    return "\n".join(rewritten_lines)


def _inject_consent_helper(code: str) -> str:
    """Inject a lightweight consent-dismiss helper and call it after navigation."""
    helper_name = "dismiss_consent_overlays"
    if helper_name not in code:
        helper_block = """

def dismiss_consent_overlays(page: Page) -> None:
    candidate_selectors = [
        "button:has-text('Consent')",
        "button:has-text('Accept')",
        "button:has-text('Continue')",
        "button:has-text('OK')",
        "button:has-text('Got it')",
        "button:has-text('I Agree')",
        "button:has-text('Agree')",
        "button[aria-label='Close']",
        "button[aria-label='close']",
    ]
    for selector in candidate_selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                locator.click(timeout=500)
                page.wait_for_timeout(200)
                break
        except Exception:
            continue
"""
        insert_after = "from playwright.sync_api import Page, expect"
        if insert_after in code:
            code = code.replace(insert_after, insert_after + helper_block, 1)
        else:
            code = helper_block + "\n" + code

    lines = code.splitlines()
    updated_lines: list[str] = []
    for line in lines:
        updated_lines.append(line)
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        # Skip injection if the line is already a call to the helper
        if f"{helper_name}(" in stripped:
            continue

        if stripped.startswith("page.goto(") or stripped.startswith("evidence_tracker.navigate("):
            # Check if next line is already a call to avoid duplicates
            updated_lines.append(f"{indent}{helper_name}(page)")

    return "\n".join(updated_lines)


def _deduplicate_skip_calls(code: str) -> str:
    """Remove duplicate consecutive pytest.skip() calls in test blocks.

    When both the orchestrator and the postprocessor inject skips for the same
    placeholder, you get two skip() calls in a row.  Keep only the first one.
    """
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

        # Detect test function start
        if stripped.startswith("def test_"):
            _flush_skips()
            in_test = True
            updated_lines.append(line)
            continue

        # Detect end of test function (another def at same or lesser indent, or class)
        if in_test and stripped and indent == 0:
            _flush_skips()
            if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("@"):
                in_test = False

        # Collect consecutive skip calls
        if in_test and stripped.startswith("pytest.skip("):
            pending_skips.append(line)
            continue

        _flush_skips()
        updated_lines.append(line)

    _flush_skips()
    return "\n".join(updated_lines)


def _ensure_test_navigation(code: str) -> str:
    """Inject an initial navigation to the first known URL if a test lacks navigation."""
    pages_block = re.search(r"# PAGES_NEEDED:\n((?:# https?://.*\n?)+)", code)
    if not pages_block:
        return code

    first_url = re.search(r"https?://[^\s\n]+", pages_block.group(1))
    if not first_url:
        return code

    url = first_url.group(0)
    lines = code.splitlines()
    updated_lines: list[str] = []

    inside_test = False
    test_has_nav = False

    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]

        if stripped.startswith("def test_"):
            inside_test = True
            test_has_nav = False
            updated_lines.append(line)
            continue

        if inside_test:
            if stripped.startswith("def ") or (line.strip() == "" and indent == ""):
                # End of test function or start of next
                if not test_has_nav:
                    # Insert nav at the start of the previous test block
                    # This is complex to do in a single pass, so we'll use a simpler approach
                    pass
                inside_test = False

            if "navigate(" in stripped or "goto(" in stripped:
                test_has_nav = True

        updated_lines.append(line)

    # Simpler approach: find test functions and inject nav if missing
    final_code = "\n".join(updated_lines)

    def _inject_nav(match: re.Match[str]) -> str:
        body = match.group(2)
        if "navigate(" in body or "goto(" in body:
            return match.group(0)

        indent = "    "
        nav_line = f'\n{indent}evidence_tracker.navigate("{url}")\n{indent}dismiss_consent_overlays(page)'
        return f"{match.group(1)}{nav_line}{body}"

    # Match test function signature and capture its body
    return re.sub(
        r"(def test_\w+\(page: Page, evidence_tracker\) -> None:)(.*?(?=\n\n|\ndef |\Z))",
        _inject_nav,
        final_code,
        flags=re.S,
    )
