"""LangGraph multi-agent workflow for skeleton generation.

Planner → Generator → Validator (with retry loop).

Usage:
    from src.agents.graph import SkeletonGraph
    from src.llm_client import LLMClient

    client = LLMClient()
    graph = SkeletonGraph(client)
    result = await graph.run(
        user_story="As a user...",
        conditions="1. Login\\n2. Add to cart...",
        target_urls=["http://...", ...],
        expected_test_count=2,
    )
    print(result["skeleton_code"])
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.generator import GeneratorAgent
from src.agents.planner import PlannerAgent
from src.agents.state import WorkflowState
from src.agents.validator import ValidatorAgent

logger = logging.getLogger(__name__)


def _should_retry(state: WorkflowState) -> str:
    """Conditional edge: route to Generator for retry, or END if done."""
    if state.validation_errors and state.retry_count <= state.max_retries:
        logger.info(
            "Validator found %d errors (retry %d/%d), routing back to Generator",
            len(state.validation_errors),
            state.retry_count,
            state.max_retries,
        )
        return "generate"
    return END


class SkeletonGraph:
    """LangGraph StateGraph for multi-agent skeleton generation.

    Args:
        client: LLMClient instance for LLM calls.
    """

    def __init__(self, client: Any) -> None:
        self._planner = PlannerAgent(client)
        self._generator = GeneratorAgent(client)
        self._validator = ValidatorAgent()

        self._graph: CompiledStateGraph[WorkflowState, None, WorkflowState, WorkflowState] = self._build_graph()

    def _build_graph(self) -> CompiledStateGraph[WorkflowState, None, WorkflowState, WorkflowState]:
        """Build and compile the StateGraph."""
        builder = StateGraph(WorkflowState)

        builder.add_node("plan", self._planner)
        builder.add_node("generate", self._generator)
        builder.add_node("validate", self._validator)

        builder.set_entry_point("plan")
        builder.add_edge("plan", "generate")
        builder.add_edge("generate", "validate")

        builder.add_conditional_edges(
            "validate",
            _should_retry,
            {
                "generate": "generate",
                END: END,
            },
        )

        return builder.compile()

    async def run(
        self,
        *,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        expected_test_count: int = 0,
        raw_dom_snapshot: str = "",
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Execute the full Planner → Generator → Validator workflow.

        Returns a dict with ``skeleton_code``, ``test_plan``,
        ``validation_errors``, and ``retry_count``.
        """
        initial_state = WorkflowState(
            user_story=user_story,
            conditions=conditions,
            target_urls=target_urls or [],
            expected_test_count=expected_test_count,
            raw_dom_snapshot=raw_dom_snapshot,
            max_retries=max_retries,
        )

        final_state = await self._graph.ainvoke(initial_state)

        return {
            "skeleton_code": final_state.get("skeleton_code", ""),
            "test_plan": final_state.get("test_plan", ""),
            "validation_errors": final_state.get("validation_errors", []),
            "retry_count": final_state.get("retry_count", 0),
        }
