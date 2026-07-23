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
5. NO evidence_tracker calls.  NO prose.  NO explanations.
6. Return valid Python code with imports at the top.
7. Every step in the test body must be a standalone placeholder line.

ALLOWED PLACEHOLDERS:
{{GOTO:<page keyword>}}        — navigate to a page
{{CLICK:<element description>}} — click a button/link
{{FILL:<field>:<value>}}       — type into a field
{{ASSERT:<expected state>}}    — verify something is visible/true

EXAMPLE OUTPUT:
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page, evidence_tracker):
    {{GOTO:login}}
    {{FILL:username:admin}}
    {{FILL:password:secret}}
    {{CLICK:login button}}
    {{ASSERT:welcome message}}
"""

GENERATOR_USER_PROMPT_TEMPLATE = """Generate pytest skeleton code from the test plan below.

CONTEXT:
User Story: {user_story}

{test_plan_block}

CRITICAL: Generate EXACTLY {count} test functions.  One per planned test.
Use ONLY double-brace placeholders — no real selectors.
Start with imports.  Each test body must be ALL placeholders."""


class GeneratorAgent:
    """Generator Agent node: test plan → skeleton code with placeholders."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    async def __call__(self, state: WorkflowState) -> dict[str, str | list]:
        """Generate skeleton code from the test plan."""
        prompt = GENERATOR_USER_PROMPT_TEMPLATE.format(
            user_story=state.user_story,
            test_plan_block=state.test_plan if state.test_plan else state.conditions,
            count=state.expected_test_count,
        )

        response = await self._client.generate(
            prompt,
            timeout=300,
            system_prompt=GENERATOR_SYSTEM_PROMPT,
        )

        return {"skeleton_code": response, "validation_errors": []}
