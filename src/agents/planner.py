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

PLANNER_SYSTEM_PROMPT = """You are an expert QA test planner. Your job is to analyse acceptance
criteria and produce a test plan that defines STRUCTURE only:
- Test function names (one per criterion)
- Step ordering (which steps go in which test)
- Prerequisite step injection

CRITICAL — USE THE CRITERIA'S EXACT WORDS:
- Copy descriptions VERBATIM from the criteria. Do NOT rewrite or shorten.
- If criterion says "click the Add to cart button next to Blue Top", write: CLICK: Add to cart Blue Top
- If criterion says "verify the confirmation message appears", write: ASSERT: confirmation message appears
- Never generalize or simplify. The downstream code generator needs the exact words.

ONE TEST PER CRITERION — never merge, never skip.
Each test must start from the beginning and include ONLY:
- Navigation to the starting page (GOTO)
- The specific steps for THIS criterion
- Authentication steps (login) if the site requires it
Do NOT include steps from earlier criteria unless they are login/auth steps.
Do NOT accumulate all prior test steps as prerequisites.
Each test function should be SHORT — 3-6 steps for simple criteria.

OUTPUT FORMAT:

## Test Plan

### test_01_<name>
Steps:
- GOTO: home
- FILL: username:standard_user
- FILL: password:secret_sauce
- CLICK: Login
- ASSERT: Products

### test_02_<name>
Steps:
- GOTO: home
- FILL: username:standard_user
- FILL: password:secret_sauce
- CLICK: Login
- CLICK: Add to cart Backpack
- ASSERT: 1"""

PLANNER_USER_PROMPT_TEMPLATE = """Create a test plan from the acceptance criteria below.

<acceptance_criteria count="{count}">
{conditions}
</acceptance_criteria>

<instruction>
Generate EXACTLY {count} test plan entries — one per criterion above.
Use the criteria's EXACT words for step descriptions — do NOT rewrite.
Each test starts from the beginning (GOTO) and does ONLY its own steps.
Include login/auth ONLY if the site requires it. Do NOT chain prior criteria.
Keep each test SHORT — 3-6 steps is ideal.
</instruction>"""


class PlannerAgent:
    """Planning Agent node: user story + conditions → test plan Markdown."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    async def __call__(self, state: WorkflowState) -> dict[str, str]:
        """Parse the user story and produce a structured test plan."""
        from src.agents.prompt_safety import safe_prompt

        prepared = prepare_conditions_for_generation(state.conditions)
        prompt = safe_prompt(
            t"""<acceptance_criteria count="{state.expected_test_count}">
{prepared}
</acceptance_criteria>

<instruction>
Generate EXACTLY {state.expected_test_count} test plan entries — one per criterion above.
Use the criteria's EXACT words for step descriptions — do NOT rewrite.
Include prerequisite login/navigation steps in each test.
</instruction>"""
        )

        response = await self._client.generate(
            prompt,
            timeout=300,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            temperature=0,
        )

        return {"test_plan": response.strip()}
