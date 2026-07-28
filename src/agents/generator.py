"""Generator Agent — consumes a test plan and produces skeleton code.

The generator receives the planner's structured test plan (Markdown)
and produces pytest skeleton code with placeholders.  This is a smaller,
more focused prompt than sending the full user story in one call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.state import WorkflowState
    from src.llm_client import LLMClient

GENERATOR_SYSTEM_PROMPT = """You are an expert Playwright Python test engineer.

CRITICAL REQUIREMENTS:
1. Generate pytest sync Playwright tests ONLY.
2. DO NOT use async/await or async_playwright.
3. Use ONLY double-brace placeholders for ALL element interactions.
4. NO real CSS selectors, XPath, or element locators.
5. NO prose.  NO explanations.  NO markdown fences.
6. Start with imports. Return valid Python code only.
7. Every step in the test body must be a standalone placeholder line.

ALLOWED PLACEHOLDERS:
{{GOTO:<page keyword>}}        — navigate to a page
{{CLICK:<element description>}} — click a button/link/icon
{{FILL:<field>:<value>}}       — type into a field
{{SELECT:<field>:<option>}}    — select a dropdown option
{{ASSERT:<expected state>}}    — verify something is visible/true

PLACEHOLDER DESCRIPTION RULES:
1. Keep descriptions SHORT (1-4 words). Use the element's visible text or label.
2. For CLICK: use the button/link text, e.g. {{CLICK:Login}}, {{CLICK:Add to cart}}
3. INCLUDE PRODUCT NAMES from the criteria: if the criteria say "Blue Top" or "Sauce Labs Backpack", write {{CLICK:Add to cart Sauce Labs Backpack}} not just {{CLICK:Add to cart}}
4. For icons (no visible text): use the shortest meaningful label, e.g. {{CLICK:Cart}}, {{CLICK:Menu}}
4. For FILL: use the field label, e.g. {{FILL:username:admin}}, {{FILL:First Name:John}}
5. For SELECT: use the field label, e.g. {{SELECT:State:NCR}}, {{SELECT:Country:United States}}
6. For ASSERT: describe what to see, e.g. {{ASSERT:Products}}, {{ASSERT:Thank You}}, {{ASSERT:1}}
7. For GOTO: use a keyword, e.g. {{GOTO:home}}, {{GOTO:cart}}, {{GOTO:checkout}}

PREREQUISITE STEPS:
Each test must be self-contained. If a test depends on earlier criteria
being completed first (e.g., you must log in before adding items to cart),
include those prerequisite steps at the start of the test function.

EXAMPLE (login + browse):
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page, evidence_tracker):
    {{GOTO:home}}
    {{FILL:username:standard_user}}
    {{FILL:password:secret_sauce}}
    {{CLICK:Login}}
    {{ASSERT:Products}}

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_to_cart(page, evidence_tracker):
    {{GOTO:home}}
    {{FILL:username:standard_user}}
    {{FILL:password:secret_sauce}}
    {{CLICK:Login}}
    {{CLICK:Add to cart}}
    {{ASSERT:1}}
"""


class GeneratorAgent:
    """Generator Agent node: test plan → skeleton code with placeholders."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    async def __call__(self, state: WorkflowState) -> dict[str, str | list]:
        """Generate skeleton code from the test plan and raw criteria.

        Uses t-strings to safely separate developer-written prompt structure
        from user-provided acceptance criteria and test plan text.
        """
        from src.agents.prompt_safety import safe_prompt

        known_urls = "\n".join(f"- {url}" for url in state.target_urls) if state.target_urls else "- None"
        test_plan = state.test_plan if state.test_plan else state.conditions

        prompt = safe_prompt(
            t"""<task>
Generate pytest skeleton code from the acceptance criteria below.
Use ONLY double-brace placeholders — no real selectors.
Produce EXACTLY {state.expected_test_count} test functions. Start with imports.
</task>

<test_plan structure_only="true">
{test_plan}
</test_plan>

<acceptance_criteria primary_source="true">
{state.conditions}
</acceptance_criteria>

<known_urls>
{known_urls}
</known_urls>

<instruction>
The <test_plan> provides STRUCTURE (test names, step count, ordering) ONLY.
The <acceptance_criteria> provides the EXACT WORDS for placeholder descriptions.
For CLICK descriptions, copy the exact product names and button labels from the criteria.
For FILL descriptions, copy the exact field labels from the criteria.
For ASSERT descriptions, copy what the criteria says should be visible.
DO NOT summarize, shorten, or rewrite the criteria words.
</instruction>"""
        )

        response = await self._client.generate(
            prompt,
            timeout=300,
            system_prompt=GENERATOR_SYSTEM_PROMPT,
        )

        return {"skeleton_code": response, "validation_errors": []}
