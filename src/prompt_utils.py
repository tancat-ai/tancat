"""Prompt helpers for both the intelligent pipeline and compatibility flows."""

from __future__ import annotations

import re
from typing import Any

_EVIDENCE_TRACKER_RULES = """=== EVIDENCE TRACKER RULES (STRICT) ===
1. MANDATORY SIGNATURE: Every test function MUST include `evidence_tracker` in its arguments.
   Example: `def test_example(page, evidence_tracker):`
2. FORBIDDEN METHODS: NEVER use raw Playwright methods on the `page` object for navigation or interaction.
   - ❌ DO NOT USE: `page.goto(url)` -> ✅ USE: `evidence_tracker.navigate(url)`
   - ❌ DO NOT USE: `page.locator(...).fill(...)` -> ✅ USE: `evidence_tracker.fill(locator, value, label=...)`
   - ❌ DO NOT USE: `page.locator(...).click()` -> ✅ USE: `evidence_tracker.click(locator, label=...)`
   - ❌ DO NOT USE: `expect(page.locator(...)).to_be_visible()` -> ✅ USE: `evidence_tracker.assert_visible(locator, label=...)`
3. MANDATORY DECORATOR: Every test function MUST be decorated with the `@pytest.mark.evidence` decorator containing valid references.
   Example: `@pytest.mark.evidence(condition_ref="CRITERIA_ID", story_ref="STORY_ID")`
4. EVIDENCE INTEGRITY: All interactions that produce screenshots or logs must go through `evidence_tracker`. Never call `page.screenshot()` directly.
"""


# Sentinel placeholder — never processed by .format() since it uses % style.
_USER_STORY_PLACEHOLDER = "%(USER_STORY)s"
_CONDITIONS_PLACEHOLDER = "%(CONDITIONS)s"
_KNOWN_URLS_PLACEHOLDER = "%(KNOWN_URLS)s"


def get_skeleton_prompt_template(
    expected_count: int | None = None,
    *,
    user_story: str = "USER STORY GOES HERE",
    conditions: str = "1. Acceptance criterion 1\n2. Acceptance criterion 2",
    known_urls_block: str = "- No URLs provided",
) -> str:
    """Return the Phase 1 skeleton-generation prompt.

    Args:
        expected_count: If provided, the exact number of test functions to generate
                        is injected prominently into the prompt.
        user_story: The user story text (default placeholder).
        conditions: The acceptance criteria text (default placeholder).
        known_urls_block: Known target URLs block (default placeholder).
    """
    count_label = str(expected_count) if expected_count is not None else "N"

    # The prompt MUST start with the count instruction — LLMs attend most to beginning.
    count_header = ""
    if expected_count is not None:
        count_header = (
            f"MANDATORY OUTPUT REQUIREMENT:\n"
            f"1. Your ENTIRE output must contain EXACTLY {expected_count} SEPARATE test functions.\n"
            f"2. ONE test per acceptance criterion. NEVER combine multiple criteria.\n"
            f"3. Each test must be SHORT: 3-10 lines MAX. No comments inside tests.\n"
            f"4. NEVER use comments like '# ... N more tests' — write ALL {expected_count} tests fully.\n"
            f"5. If you produce fewer than {expected_count} tests, the output is rejected.\n\n"
        )

    # Brace examples shown to the LLM — built with raw strings to avoid any
    # .format() interpretation.  The LLM must see exactly two braces each side.
    _OPEN = "{{"
    _CLOSE = "}}"

    def _double(text: str) -> str:
        return f"{_OPEN}{text}{_CLOSE}"

    # Double-escape for .format() survival: {{{{ }} }} -> {{ }} in output
    _DOUBLED = "{{{{"
    _DOUBLED_CLOSE = "}}}}"

    def _show(text: str) -> str:
        return f"{_DOUBLED}{text}{_DOUBLED_CLOSE}"

    brace_examples = (
        "\n"
        "PLACEHOLDER BRACE RULE (CRITICAL — READ CAREFULLY):\n"
        "Every placeholder uses EXACTLY TWO braces on each side.\n"
        f"CORRECT: {_show('CLICK:button')}  {_show('FILL:name')}  {_show('ASSERT:visible')}\n"
        "If your output has a different number of braces, it is INVALID.\n"
        "\n"
    )

    # Minimal output template — SHORT, direct, and brace-count explicit.
    # Uses % style for user_story/conditions/known_urls so .format() is never
    # called on the brace-heavy examples.
    output_template = (
        "\n=== REQUIRED OUTPUT FORMAT (STRICT) ===\n"
        f"Your output must contain EXACTLY {count_label} test functions. NOTHING ELSE.\n"
        "Each test: 3-10 lines MAX. No comments. No blank lines between steps.\n"
        "Imports go ONCE at the top. # PAGES_NEEDED goes at the bottom.\n"
        "\n"
        "MINIMAL EXAMPLE (1 test, showing format):\n"
        "\n"
        "from playwright.sync_api import Page, expect\n"
        "import pytest\n"
        "\n"
        '@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")\n'
        "def test_01_example(page: Page, evidence_tracker) -> None:\n"
        '    evidence_tracker.navigate("{{GOTO:home_url}}")\n'
        f'    evidence_tracker.click({_show("CLICK:button")}, label="button")\n'
        f'    evidence_tracker.assert_visible({_show("ASSERT:result")}, label="result")\n'
        "\n"
        "# PAGES_NEEDED:\n"
        "# - https://your-target-site.com/ (home page)\n"
        "\n"
        f"IMPORTANT: Write ALL {count_label} tests fully. Each test SEPARATE. "
        "NO comments like '# ... more tests'. NEVER merge criteria.\n"
    )

    placeholder_syntax_section = (
        "=== PLACEHOLDER SYNTAX (STRICT) ===\n"
        "Use ONLY double-brace placeholders with EXACTLY 2 braces each side.\n"
        "Format: {{{{ACTION:description}}}} where ACTION is one of: CLICK, FILL, GOTO, URL, ASSERT\n"
        f"Examples: {_show('CLICK:button')}  {_show('FILL:name')}  {_show('GOTO:url')}  {_show('ASSERT:visible')}\n"
        "NEVER use single braces, CSS selectors, XPath, or guess locators.\n"
        "NEVER write {{{{ACTION:description}}}} literally — replace ACTION with CLICK/FILL/GOTO/URL/ASSERT.\n"
        "\n"
        "=== ALLOWED PLACEHOLDERS (NO OTHER ACTIONS ARE VALID) ===\n"
        "The ONLY allowed ACTION values are: CLICK, FILL, GOTO, URL, ASSERT\n"
        f"- CLICK:{_show('description')} — for clicking buttons, links, or elements\n"
        f"- FILL:{_show('description')} — for typing into input fields\n"
        f"- GOTO:{_show('description')} — for navigating to a URL\n"
        f"- URL:{_show('description')} — for navigating to a URL (same as GOTO)\n"
        f"- ASSERT:{_show('description')} — for asserting element visibility\n"
        "For ANY other action (CLOSE, WAIT, PRESS, SELECT, SCROLL, etc.),\n"
        "write: pytest.skip('Not supported in skeleton: action name')\n"
        "DO NOT invent new placeholder action names. Only CLICK, FILL, GOTO, URL, ASSERT.\n"
        "\n"
    )

    return (
        "You are a Playwright Python test engineer.\n"
        "\n"
        "Generate a pytest sync Playwright skeleton from the specification below.\n"
        "\n"
        + count_header
        + output_template
        + "\n"
        + brace_examples
        + placeholder_syntax_section
        + "=== EVIDENCE TRACKER (STRICT) ===\n"
        "- In test functions: evidence_tracker is a fixture argument -> `def test_xxx(page: Page, evidence_tracker):\n"
        "- In Page Object methods: include evidence_tracker as a method parameter\n"
        "- NEVER use raw page.goto(), page.click(), page.fill(), expect(page.locator(...))\n"
        "- ALWAYS use evidence_tracker.navigate(), evidence_tracker.click(), evidence_tracker.fill(), evidence_tracker.assert_visible()\n"
        '- Decorate every test with: @pytest.mark.evidence(condition_ref="TC...", story_ref="...")\n'
        "\n"
        "=== CODE STRUCTURE ===\n"
        "- pytest format, sync API only. No async/await.\n"
        "- Imports: from playwright.sync_api import Page, expect; import pytest\n"
        "- Page Object classes: structural stubs only; do NOT guess selectors inside them.\n"
        "- Include a # PAGES_NEEDED: block with real absolute URLs only (no placeholders).\n"
        "\n"
        "Known Target URLs:\n"
        "{known_urls_block}\n"
        "\n"
        "User Story:\n"
        "{user_story}\n"
        "\n"
        "Derived Test Conditions:\n"
        "{conditions}\n"
        "\n"
        f"ALL {count_label.upper()} CRITERIA MUST HAVE SEPARATE TEST FUNCTIONS. "
        "Generate ONE test per criterion. Do NOT combine, skip, or omit any criteria.\n"
    )


def get_streamlit_system_prompt_template() -> str:
    """DEPRECATED — This prompt format is not used in production.

    The skeleton-first pipeline with placeholder resolution is now the only active path.
    Kept for historical reference only. Do not wire this back into the generation flow.
    """
    return (
        """You are an expert QA engineer writing Playwright Python tests in pytest format using the sync API.

REQUIREMENTS:
- Generate exactly {count} test functions from the acceptance criteria below.
- Use pytest format and Playwright sync API only.
- Do not use async/await or async_playwright.
- Each test runs in a FRESH browser context, so never assume login or cart state carries across tests.
- Use ONLY LOCATORS LISTED IN THE PAGE CONTEXT ABOVE.
- NEVER invent, guess, or create locators that are not present in the PAGE CONTEXT.

"""
        + _EVIDENCE_TRACKER_RULES
        + """

User Story:
{user_story}

Derived Test Conditions:
{conditions}
"""
    )


def build_page_context_prompt_block(page_context: Any) -> str:
    """Format page context into an approved-locators block for prompt injection."""
    raw_context = str(page_context or "").strip()
    if not raw_context:
        return """=== PAGE CONTEXT ===
No context available.

No PAGE CONTEXT is available, so only generate structural test logic and leave unknown interactions explicit.
"""

    truncated = raw_context
    truncation_note = ""
    if len(truncated) > 5000:
        truncated = truncated[:5000]
        truncation_note = "\nNOTE: PAGE CONTEXT was truncated to keep prompt size bounded.\n"

    locators = re.findall(r"(page\.[^\n]+)", truncated)
    if not locators:
        locators_block = "- No approved locators were extracted from PAGE CONTEXT."
    else:
        locators_block = "\n".join(f"- {locator.strip()}" for locator in locators)

    return f"""=== PAGE CONTEXT ===
{truncated}
{truncation_note}
=== APPROVED LOCATORS ===
{locators_block}
"""


def count_conditions(conditions: str) -> int:
    """Return the number of non-empty condition lines."""
    return len([line.strip() for line in conditions.splitlines() if line.strip()])


def prepare_conditions_for_generation(conditions: str) -> str:
    """Enumerate conditions with line numbers for clear LLM referencing."""
    condition_lines = [line.strip() for line in conditions.splitlines() if line.strip()]
    normalized_lines: list[str] = []

    for index, line in enumerate(condition_lines, start=1):
        stripped_line = re.sub(r"^\d+[.)]\s*", "", line).strip()
        normalized_lines.append(f"{index}. {stripped_line}")

    total_count = len(normalized_lines)
    if total_count == 0:
        return conditions

    return (
        f"There are exactly {total_count} test conditions below.\n"
        f"Generate EXACTLY {total_count} pytest test functions.\n"
        "Generate ONE test function per condition.\n"
        "Do NOT combine multiple conditions into one test.\n"
        "Name the tests in order such as test_01_..., test_02_..., test_03_....\n\n" + "\n".join(normalized_lines)
    )


def build_retry_conditions(
    prepared_conditions: str,
    expected_test_count: int,
) -> str:
    """Return a stricter condition prompt for a one-time skeleton retry."""
    return (
        prepared_conditions
        + "\n\nCRITICAL CORRECTION:\n"
        + f"The previous answer did not produce exactly {expected_test_count} separate pytest test functions.\n"
        + "Regenerate the file with one test function per numbered condition and do not merge them."
    )
