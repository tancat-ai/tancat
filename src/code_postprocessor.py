"""Pure code-string transformation helpers extracted from TestOrchestrator.

Orchestrates normalization by delegating to specialised sub-modules:
- :mod:`src.llm_reasoning_filter` — detects and strips LLM reasoning text
- :mod:`src.code_normalizer` — deterministic normalization transforms
"""

from __future__ import annotations

import re

from .code_normalizer import (
    convert_standalone_placeholders,
    dedent_indented_test_blocks,
    deduplicate_skip_calls,
    ensure_test_navigation,
    fix_indentation,
    fix_module_scope_indentation,
    replace_bare_ellipsis,
    replace_remaining_placeholders,
    strip_pages_needed_block,
)
from .llm_reasoning_filter import strip_llm_reasoning


def normalise_generated_code(code: str, consent_mode: str = "auto-dismiss", target_url: str = "") -> str:
    """Apply small deterministic fixes to common skeleton-generation mistakes."""
    fixed_code = code

    # First: strip LLM reasoning text that may have leaked into the code block
    fixed_code = strip_llm_reasoning(fixed_code)

    # Convert standalone placeholder lines and unwrap evidence_tracker-wrapped placeholders.
    fixed_code = convert_standalone_placeholders(fixed_code)

    # Clean up malformed decorators if the LLM added spaces
    fixed_code = re.sub(r"@\s*pytest\s*\.\s*mark\s*\.\s*evidence", "@pytest.mark.evidence", fixed_code)

    # Always inject pytest at module level when the code uses any pytest constructs.
    if "pytest.skip(" in fixed_code or "pytest.mark." in fixed_code:
        fixed_code = inject_import(fixed_code, "import pytest")
    if re.search(r"\bPage\b", fixed_code) or "expect(" in fixed_code:
        fixed_code = inject_import(fixed_code, "from playwright.sync_api import Page, expect")

    # The tool ships an `evidence_tracker` fixture for generated tests.
    # Some LLMs hallucinate a non-existent `evidence_launcher` fixture name.
    fixed_code = re.sub(r"\bevidence_launcher\b", "evidence_tracker", fixed_code)
    fixed_code = _ensure_evidence_tracker_fixture(fixed_code)

    # Ensure evidence_tracker is used for common methods even if LLM forgot
    fixed_code = re.sub(r"page\.goto\(", "evidence_tracker.navigate(", fixed_code)
    fixed_code = re.sub(r"self\.page\.goto\(", "evidence_tracker.navigate(", fixed_code)

    # Some models hallucinate a slash between `pytest.mark` and the marker name.
    fixed_code = re.sub(r"(?m)^\s*@pytest\.mark\s*/\s*([A-Za-z_][A-Za-z0-9_]*)", r"@pytest.mark.\1", fixed_code)

    # Some models hallucinate special constructor names (e.g. `__larry`)
    fixed_code = re.sub(
        r"(?m)(^\s*)def\s+__larry\s*\(\s*self\s*,\s*page\s*:\s*Page\s*\)\s*:\s*$",
        r"\1def __init__(self, page: Page) -> None:",
        fixed_code,
    )

    # Some models emit invalid keyword arguments when instantiating page objects.
    fixed_code = re.sub(
        r"(\b[A-Za-z_][A-Za-z0-9_]*Page)\(\s*project\s*=\s*page\s*\)",
        r"\1(page)",
        fixed_code,
    )

    # Guardrail: strip invalid decorator assignment lines
    fixed_code = re.sub(r"(?m)^\s*@pytest\.mark\w*\s*=\s*.*\n?", "", fixed_code)

    fixed_code = re.sub(r"(def __init__\(self,\s*page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
    fixed_code = re.sub(r"(def test_[A-Za-z0-9_]*\(page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
    fixed_code = re.sub(r"(?<=:\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)
    fixed_code = re.sub(r"(?<=->\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)

    if consent_mode == "auto-dismiss":
        fixed_code = _inject_consent_helper(fixed_code)

    fixed_code = rewrite_page_references_in_class_methods(fixed_code)

    # Hallucination guard: record_condition(...) -> strip
    fixed_code = re.sub(r"(?m)^\s*evidence_tracker\.record_condition\(.*?\)\s*$", "", fixed_code)

    # Fix misplaced closing parenthesis in evidence_tracker method calls.
    fixed_code = re.sub(
        r"(evidence_tracker\.\w+\([^)]*)\)'\)(\s*,\s*\w+=)",
        r"\1)'\2",
        fixed_code,
    )

    # Ensure every test starts with a navigation if none present.
    fixed_code = ensure_test_navigation(fixed_code, target_url=target_url or None)

    # Dedent module-level constructs that the LLM accidentally indented
    fixed_code = fix_module_scope_indentation(fixed_code)

    # Safety net: replace any remaining unresolved placeholders with pytest.skip()
    fixed_code = replace_remaining_placeholders(fixed_code)
    fixed_code = strip_pages_needed_block(fixed_code)

    # Some models indent entire top-level test blocks after helper functions
    fixed_code = dedent_indented_test_blocks(fixed_code)

    # Fix inconsistent indentation inside test functions and class methods
    fixed_code = fix_indentation(fixed_code)

    # Deduplicate consecutive pytest.skip() calls in the same test block
    fixed_code = deduplicate_skip_calls(fixed_code)

    # Replace bare `...` (ellipsis) in test functions with pytest.skip()
    fixed_code = replace_bare_ellipsis(fixed_code)

    return fixed_code


def replace_token_in_line(
    line: str,
    action: str,
    token: str,
    resolved_value: str,
    duplicate_selectors: set[str],
    description: str = "",
    fill_value: str = "",
) -> str:
    """Replace a single placeholder token within a code line."""
    stripped = line.strip()
    indent = line[: len(line) - len(line.lstrip())]

    if "pytest.skip" in resolved_value:
        return f"{indent}{resolved_value}"

    step_label = description if description else token

    if "pytest.skip" in resolved_value and "label=" in stripped:
        return f"{indent}{resolved_value}"

    if action == "CLICK":
        selector_literal = resolved_value
        if not (resolved_value.startswith("'") or resolved_value.startswith('"')):
            selector_literal = repr(resolved_value)
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
        return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"

    if action == "ASSERT":
        assert_value = resolved_value
        if not (resolved_value.startswith("'") or resolved_value.startswith('"')):
            assert_value = repr(resolved_value)
        if stripped == token:
            return f"{indent}evidence_tracker.assert_visible({assert_value}, label={repr(step_label)})"
        if re.search(r"expect\((?:self\.)?page\.locator\(.*?\)\)\.to_\w+\(.*\)", stripped):
            return f"{indent}evidence_tracker.assert_visible({assert_value}, label={repr(step_label)})"
        locator_only_patterns = {
            f"page.locator({token})",
            f"self.page.locator({token})",
        }
        if stripped in locator_only_patterns:
            return f"{indent}evidence_tracker.assert_visible({assert_value}, label={repr(step_label)})"
        return line.replace(token, resolved_value)

    if action == "FILL":
        if stripped == token:
            return f"{indent}evidence_tracker.fill({resolved_value}, {repr(fill_value)}, label={repr(step_label)})"
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
            return f"{indent}evidence_tracker.fill({resolved_value}, {repr(fill_value)}, label={repr(step_label)})"
        fill_no_value = re.match(
            r"(evidence_tracker\.fill\()(" + re.escape(token) + r")(\s*,\s*label=)",
            stripped,
        )
        if fill_no_value:
            return f"{indent}{fill_no_value.group(1)}{resolved_value}, {repr(fill_value)}{fill_no_value.group(3)}{repr(step_label)})"
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


def _ensure_evidence_tracker_fixture(code: str) -> str:
    """Add the evidence_tracker pytest fixture argument to tests that use it."""
    lines = code.splitlines()
    updated_lines: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)def\s+(test_\w+)\(([^)]*)\)(.*):\s*$", line)
        if not match:
            updated_lines.append(line)
            index += 1
            continue

        block_lines: list[str] = []
        lookahead = index + 1
        while lookahead < len(lines):
            next_line = lines[lookahead]
            if next_line and not next_line[0].isspace() and re.match(r"^(?:@|def |class |import |from )", next_line):
                break
            block_lines.append(next_line)
            lookahead += 1

        if "evidence_tracker." not in "\n".join(block_lines):
            updated_lines.append(line)
            index += 1
            continue

        params = [param.strip() for param in match.group(3).split(",") if param.strip()]
        param_names = [param.split(":", 1)[0].split("=", 1)[0].strip() for param in params]
        if "evidence_tracker" not in param_names:
            params.append("evidence_tracker")
            line = f"{match.group(1)}def {match.group(2)}({', '.join(params)}){match.group(4)}:"

        updated_lines.append(line)
        index += 1

    return "\n".join(updated_lines)


def flatten_inner_functions(code: str) -> str:
    """Remove nested 'def inner():' style wrappers and move their decorators up."""
    lines = code.splitlines()
    updated_lines: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("def test_") and "(" in stripped:
            updated_lines.append(line)
            i += 1

            while i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()
                next_indent = len(next_line) - len(next_line.lstrip())

                if (
                    next_stripped.startswith("def test_")
                    or next_stripped.startswith("class ")
                    or next_stripped.startswith("import ")
                    or next_stripped.startswith("from ")
                    or (next_indent <= 0 and next_stripped)
                ):
                    break

                if next_stripped.startswith("def ") and next_indent > 0:
                    decorator_lines: list[str] = []
                    j = i - 1
                    while j >= 0 and lines[j].strip().startswith("@pytest.mark.evidence"):
                        decorator_lines.insert(0, lines[j].strip())
                        j -= 1

                    func_name = next_stripped[4:].split("(", 1)[0].strip()

                    base_indent = " " * (len(line) - len(line.lstrip()))
                    for d_line in decorator_lines:
                        updated_lines.append(f"{base_indent}{d_line}")

                    i += 1

                    nested_indent = next_indent
                    while i < len(lines):
                        body_line = lines[i]
                        body_stripped = body_line.strip()
                        body_indent = len(body_line) - len(body_line.lstrip())

                        if body_stripped and body_indent <= nested_indent:
                            break

                        if body_indent == nested_indent and body_stripped.startswith(func_name + "("):
                            i += 1
                            continue

                        if body_stripped:
                            updated_lines.append(base_indent + body_line.lstrip())
                        else:
                            updated_lines.append("")
                        i += 1
                    continue

                updated_lines.append(next_line)
                i += 1
            continue

        updated_lines.append(line)
        i += 1

    return "\n".join(updated_lines)


def inject_import(code: str, import_line: str) -> str:
    """Insert an import at the very top of the generated file."""
    lines = code.splitlines()

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
    """Inject the dismiss_consent_overlays import and calls into the code."""
    helper_name = "dismiss_consent_overlays"
    import_line = "from src.browser_utils import dismiss_consent_overlays"

    if import_line not in code:
        insert_after = "from playwright.sync_api import Page, expect"
        if insert_after in code:
            code = code.replace(insert_after, insert_after + "\n" + import_line, 1)
        else:
            code = import_line + "\n" + code

    lines = code.splitlines()
    updated_lines: list[str] = []
    for line in lines:
        updated_lines.append(line)
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        if f"{helper_name}(" in stripped:
            continue

        if stripped.startswith("page.goto(") or stripped.startswith("evidence_tracker.navigate("):
            updated_lines.append(f"{indent}{helper_name}(page)")

    return "\n".join(updated_lines)
