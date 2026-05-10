"""Prompt helpers for both the intelligent pipeline and compatibility flows."""

from __future__ import annotations

import re

# Sentinel placeholders — never processed by .format() directly since they use % style.
_USER_STORY_PLACEHOLDER = "%(USER_STORY)s"
_CONDITIONS_PLACEHOLDER = "%(CONDITIONS)s"
_KNOWN_URLS_PLACEHOLDER = "%(KNOWN_URLS)s"


def count_conditions(conditions: str) -> int:
    """Return the number of numbered criteria in the conditions text."""
    # Matches lines starting with "1. ", "1)", etc.
    return len(re.findall(r"^\d+[.)]\s+", conditions, re.M))


def prepare_conditions_for_generation(conditions: str) -> str:
    """Prepare conditions text for LLM generation by ensuring proper numbering."""
    lines = [line.strip() for line in conditions.splitlines() if line.strip()]
    prepared = []
    for i, line in enumerate(lines, 1):
        # Remove existing numbering if present
        clean_line = re.sub(r"^\d+[.)]\s*", "", line)
        prepared.append(f"{i}. {clean_line}")
    return "\n".join(prepared)


def build_retry_conditions(conditions: str, expected_count: int) -> str:
    """Format conditions for a retry with a strict count requirement."""
    header = f"STRICT REQUIREMENT: You MUST generate EXACTLY {expected_count} test functions. One for each criterion below. DO NOT skip or combine any."
    return f"{header}\n\n{conditions}"


def build_single_condition_skeleton_prompt(
    *,
    user_story: str,
    known_urls_block: str,
    ordered_conditions: list[str],
    target_condition_ref: str,
    target_condition_text: str,
    target_condition_expected: str,
    target_condition_intent: str | None = None,
) -> str:
    """Build a prompt for generating a single test function fragment."""
    conditions_block = "\n".join(f"- {c}" for c in ordered_conditions)

    return (
        "You are a Playwright Python test engineer.\n"
        "\n"
        "Generate EXACTLY ONE pytest test function for the target condition below.\n"
        "\n"
        "=== TARGET CONDITION ===\n"
        f"ID: {target_condition_ref}\n"
        f"Description: {target_condition_text}\n"
        f"Expected: {target_condition_expected}\n"
        "\n"
        "=== MANDATORY OUTPUT FORMAT ===\n"
        "1. Output ONLY the test function code. NO PROSE.\n"
        "2. Use ONLY standalone double-brace placeholders inside the test.\n"
        "3. Every line in the test body must be a placeholder like {{CLICK:description}}.\n"
        "\n"
        "=== ALLOWED PLACEHOLDERS ===\n"
        "{{GOTO:url or description}}\n"
        "{{CLICK:element description}}\n"
        "{{FILL:element description:value to type}}\n"
        "{{ASSERT:element description}}\n"
        "\n"
        "=== USER STORY ===\n"
        f"{user_story}\n"
        "\n"
        "=== ALL CONDITIONS (FOR CONTEXT) ===\n"
        f"{conditions_block}\n"
        "\n"
        "=== KNOWN TARGET URLS ===\n"
        f"{known_urls_block}\n"
        "\n"
        f"Generate the test function for {target_condition_ref} now."
    )


def get_skeleton_prompt_template(
    expected_count: int | None = None,
) -> str:
    """Return a template for Phase 1 skeleton-generation prompt."""
    count_label = str(expected_count) if expected_count is not None else "N"

    return (
        "You are a Playwright Python test engineer.\n"
        "\n"
        "=== INSTRUCTIONS ===\n"
        f"Generate EXACTLY {count_label} test functions. One per criterion.\n"
        "Use ONLY the double-brace placeholder format for test steps.\n"
        "NO PROSE. NO EXPLANATIONS. START WITH IMPORTS.\n"
        "\n"
        "=== ALLOWED STEP FORMATS ===\n"
        "{{GOTO:page keyword}}\n"
        "{{CLICK:button or link description}}\n"
        "{{FILL:input field description:value to type}}\n"
        "{{ASSERT:visible element description}}\n"
        "\n"
        "=== PAGES_NEEDED BLOCK ===\n"
        "At the end of your output, list the pages needed using KEYWORDS (not URLs):\n"
        "# PAGES_NEEDED:\n"
        "# - home (homepage)\n"
        "# - cart (shopping cart page)\n"
        "# - checkout (checkout page)\n"
        "Each keyword must match a GOTO placeholder. DO NOT write URLs here.\n"
        "\n"
        "=== PREREQUISITE STEPS ===\n"
        "Each test must be self-contained. If a test depends on earlier criteria\n"
        "being completed first (e.g., you must log in before adding items to cart),\n"
        "include those prerequisite steps at the start of the test function.\n"
        "\n"
        "=== EXAMPLE OUTPUT ===\n"
        "import pytest\n"
        "from playwright.sync_api import Page\n"
        "\n"
        '@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")\n'
        "def test_01_example(page, evidence_tracker):\n"
        "    {{GOTO:home}}\n"
        "    {{FILL:username:admin}}\n"
        "    {{CLICK:submit button}}\n"
        "    {{ASSERT:welcome message}}\n"
        "\n"
        '@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")\n'
        "def test_02_example(page, evidence_tracker):\n"
        "    {{GOTO:home}}\n"
        "    {{FILL:username:admin}}\n"
        "    {{CLICK:submit button}}\n"
        "    {{CLICK:add to cart button}}\n"
        "    {{ASSERT:cart badge updated}}\n"
        "\n"
        "# PAGES_NEEDED:\n"
        "# - home (homepage)\n"
        "\n"
        "=== USER STORY ===\n"
        "{user_story}\n"
        "\n"
        "=== ACCEPTANCE CRITERIA ===\n"
        "{conditions}\n"
        "\n"
        "=== KNOWN URLS ===\n"
        "{known_urls_block}\n"
        "\n"
        f"Generate the {count_label} test functions now."
    )


def get_streamlit_system_prompt_template() -> str:
    """Return the system prompt for the Streamlit UI."""
    return (
        "You are a Playwright Python test engineer.\n"
        "Generate a pytest sync Playwright test based on the User Story and Conditions.\n"
        "\n"
        "=== CONTEXT ===\n"
        "User Story: {user_story}\n"
        "Conditions: {conditions}\n"
        "Test Count: {count}\n"
        "\n"
        "=== RULES ===\n"
        "1. Use pytest format with sync Playwright API.\n"
        "2. Do NOT use async/await.\n"
        "3. Every test runs in a FRESH browser context.\n"
        "4. Follow the PAGE CONTEXT constraints if provided.\n"
    )


def build_page_context_prompt_block(page_context: str) -> str:
    """Format the scraped page context for inclusion in an LLM prompt."""
    if not page_context:
        return "=== PAGE CONTEXT ===\nNo PAGE CONTEXT is available for this page."

    if len(page_context) > 15000:
        page_context = page_context[:15000] + "\n... (truncated)"

    return f"=== APPROVED LOCATORS (PAGE CONTEXT) ===\n{page_context}\n"
