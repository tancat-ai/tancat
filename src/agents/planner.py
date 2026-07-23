"""Planning Agent — parses user story + conditions into an ordered test plan.

The planner outputs Markdown (not code), giving the Generator a
structured, unambiguous description of every test function to produce.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.prompt_utils import prepare_conditions_for_generation

if TYPE_CHECKING:
    from src.agents.state import WorkflowState
    from src.llm_client import LLMClient

PLANNER_SYSTEM_PROMPT = """You are an expert QA test planner. Your job is to analyse a user story
and its acceptance criteria, then produce a clear, numbered test plan.

For each criterion, produce:
1. A test function name (e.g. test_01_login)
2. A list of step descriptions, each tagged with its action type
   (GOTO, CLICK, FILL, ASSERT)

IMPORTANT RULES:
- Include PREREQUISITE steps at the start of each test if the test
  depends on earlier actions (e.g. login before adding to cart).
- Each test must be self-contained: do NOT assume prior state from
  another test function.
- Use SHORT step descriptions (2-5 words).
- Output ONLY the test plan in the format below — no prose, no code.

OUTPUT FORMAT:

## Test Plan

### test_01_<name>
Steps:
- GOTO: <page or URL>
- FILL: <field>:<value>
- CLICK: <button>
- ASSERT: <expected state>

### test_02_<name>
Steps:
..."""

PLANNER_USER_PROMPT_TEMPLATE = """Create a test plan for the following user story and acceptance criteria.

USER STORY:
{user_story}

ACCEPTANCE CRITERIA ({count} total):
{conditions}

Generate the test plan with EXACTLY {count} test functions — one per criterion."""


class PlannerAgent:
    """Planning Agent node: user story + conditions → test plan Markdown."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    async def __call__(self, state: WorkflowState) -> dict[str, str]:
        """Parse the user story and produce a structured test plan."""
        prepared = prepare_conditions_for_generation(state.conditions)
        prompt = PLANNER_USER_PROMPT_TEMPLATE.format(
            user_story=state.user_story,
            conditions=prepared,
            count=state.expected_test_count,
        )

        response = await self._client.generate(
            prompt,
            timeout=300,
            system_prompt=PLANNER_SYSTEM_PROMPT,
        )

        return {"test_plan": response.strip()}
