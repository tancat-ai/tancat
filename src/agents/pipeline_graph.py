"""Full-pipeline LangGraph StateGraph — Ingestion → QA Director → Synthesizer.

Composes the existing ``SkeletonGraph`` (Planner → Generator → Validator)
as a sub-component of the Script Synthesizer node.

Usage:
    from src.agents.pipeline_graph import PipelineGraph
    from src.llm_client import LLMClient

    client = LLMClient()
    graph = PipelineGraph(client)
    result = await graph.run(
        user_story="As a user I want to...",
        base_url="https://example.com",
    )
    print(result.test_code)
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------


def _after_qa_director(state: PipelineState) -> str:
    """Route after QA Director: pause for human, or skip checkpoint."""
    if state.auto_confirm:
        return "synthesize"
    if state.plan_confirmed:
        return "synthesize"
    # Pending human confirmation — graph pauses here.
    # Caller sets plan_confirmed=True and resumes.
    return END


def _after_synthesizer(state: PipelineState) -> str:
    """Route after Synthesizer: retry on failure, or proceed."""
    if state.errors and state.retry_count < state.max_retries:
        logger.info("Synthesizer errors (retry %d/%d)", state.retry_count, state.max_retries)
        state.retry_count += 1
        return "synthesize"
    return "postprocess"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class PipelineGraph:
    """LangGraph StateGraph for the full test-generation pipeline.

    Nodes:
        ingest       — Ingestion Agent: story → StoryAnalysis
        plan         — QA Director: StoryAnalysis → test conditions
        synthesize   — Script Synthesizer: conditions → test code
        postprocess  — Code Postprocessor: validate, strip evidence, export

    Edges:
        ingest → plan → [human checkpoint] → synthesize ⇄ postprocess → END

    Args:
        client: LLMClient for LLM calls (shared across agents).
        enable_checkpoint: If True, pause after QA Director for human review.
    """

    def __init__(
        self,
        client: Any | None = None,
        rag_retriever: Any | None = None,
        enable_checkpoint: bool = True,
    ) -> None:
        self._client = client
        self._rag_retriever = rag_retriever
        self._enable_checkpoint = enable_checkpoint

        # Phase 1b: real agents (fall back to mock if no client)
        from src.agents.director import QADirectorAgent
        from src.agents.ingestion import IngestionAgent
        from src.agents.synthesizer import ScriptSynthesizerAgent

        self._ingestion_agent = IngestionAgent(client, rag_retriever) if client else None
        self._director_agent = QADirectorAgent(client)
        self._synthesizer_agent = ScriptSynthesizerAgent(client)

        self._graph: CompiledStateGraph = self._build_graph()

    # ------------------------------------------------------------------
    # Node implementations (mock for Phase 1a — real logic in Phase 1b)
    # ------------------------------------------------------------------

    async def _ingest(self, state: PipelineState) -> dict[str, Any]:
        """Ingestion Agent: analyse the user story."""
        if self._ingestion_agent is not None:
            return await self._ingestion_agent(state)
        return await self._ingest_mock(state)

    async def _ingest_mock(self, state: PipelineState) -> dict[str, Any]:
        """Mock ingestion for when no LLM client is available."""
        from src.agents.pipeline_state import Criterion, StoryAnalysis

        conditions = state.user_story.split("\n")
        conditions = [c.strip() for c in conditions if c.strip()]
        criteria = [
            Criterion(
                ref=f"TC01.{i + 1:02d}",
                description=c[:80],
                condition_type="happy_path",
                priority="medium",
            )
            for i, c in enumerate(conditions)
        ]
        return {
            "story_analysis": StoryAnalysis(
                story_text=state.user_story,
                criteria=criteria,
                source_format="free-form",
            ),
        }

    async def _plan(self, state: PipelineState) -> dict[str, Any]:
        """QA Director: story analysis → test conditions."""
        return await self._director_agent(state)

    async def _synthesize(self, state: PipelineState) -> dict[str, Any]:
        """Script Synthesizer: conditions → test code."""
        return await self._synthesizer_agent(state)

    async def _postprocess(self, state: PipelineState) -> dict[str, Any]:
        """Code Postprocessor: validate syntax, strip evidence for export.

        Skips syntax validation when the code contains double-brace
        placeholders (skeleton mode) — placeholders are not valid Python
        until resolved.
        """
        errors: list[str] = list(state.errors)
        if state.test_code:
            # Skip AST validation for skeleton code with placeholders
            if "{{" not in state.test_code:
                import ast

                try:
                    ast.parse(state.test_code)
                except SyntaxError as e:
                    errors.append(f"Syntax error in generated code: {e}")

        return {"errors": errors}

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self) -> CompiledStateGraph:
        """Build and compile the StateGraph."""

        # Use PipelineState as the state schema.
        # LangGraph support for TypedDict-based state is evolving;
        # we cast to Any for now since PipelineState is a dataclass.
        builder: Any = StateGraph(PipelineState)  # type: ignore[arg-type]

        builder.add_node("ingest", self._ingest)
        builder.add_node("plan", self._plan)
        builder.add_node("synthesize", self._synthesize)
        builder.add_node("postprocess", self._postprocess)

        builder.set_entry_point("ingest")
        builder.add_edge("ingest", "plan")

        # After QA Director: conditional (human checkpoint or straight to synthesize)
        builder.add_conditional_edges(
            "plan",
            _after_qa_director,
            {
                "synthesize": "synthesize",
                END: END,
            },
        )

        # After Synthesizer: conditional (retry on error, or proceed)
        builder.add_conditional_edges(
            "synthesize",
            _after_synthesizer,
            {
                "synthesize": "synthesize",
                "postprocess": "postprocess",
            },
        )

        builder.add_edge("postprocess", END)

        return builder.compile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        user_story: str,
        base_url: str = "",
        additional_urls: list[str] | None = None,
        credential_profile: dict[str, str] | None = None,
        pom_mode: bool = False,
        auto_confirm: bool = False,
    ) -> PipelineState:
        """Execute the full pipeline graph.

        Returns the final ``PipelineState`` with ``test_code`` populated.
        """
        initial = PipelineState(
            user_story=user_story,
            base_url=base_url,
            additional_urls=additional_urls or [],
            credential_profile=credential_profile,
            pom_mode=pom_mode,
            auto_confirm=auto_confirm,
        )

        result = await self._graph.ainvoke(initial)
        return PipelineState(**{k: v for k, v in result.items() if k in PipelineState.__dataclass_fields__})  # type: ignore[arg-type]

    async def resume_after_checkpoint(
        self,
        state: PipelineState,
        confirmed_conditions: list[Any],
    ) -> PipelineState:
        """Resume the graph after a human checkpoint.

        Call this after the tester has reviewed the test plan and confirmed
        the conditions.  Sets ``plan_confirmed=True`` and continues from
        the QA Director node.

        Args:
            state: The ``PipelineState`` as it was when the graph paused.
            confirmed_conditions: The (potentially edited) list of conditions.
        """
        state.plan_confirmed = True
        state.test_conditions = confirmed_conditions  # type: ignore[assignment]

        result = await self._graph.ainvoke(state)
        return PipelineState(**{k: v for k, v in result.items() if k in PipelineState.__dataclass_fields__})  # type: ignore[arg-type]

    @property
    def compiled_graph(self) -> CompiledStateGraph:
        """Expose the compiled graph for testing and introspection."""
        return self._graph
