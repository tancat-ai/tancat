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
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.pipeline_state import ChangeDelta, ImpactMap, PipelineState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------


def _route_entry(state: PipelineState) -> str:
    """Route the entry point: document mode goes through parsing first."""
    if state.input_mode == "document" and state.document_source:
        return "parse_document"
    return "ingest"


def _after_qa_director(state: PipelineState) -> str:
    """Route after QA Director: checkpoint, then route by persona.

    If the plan isn't confirmed (human checkpoint pending), pause.
    Once confirmed, route based on persona_role:
    - qa_lead / operations → impact_map → synthesize
    - developer → synthesize (skip impact)
    - product_owner → consolidated_report (skip synthesis)
    - default (no persona) → synthesize (existing behaviour)
    """
    if not state.plan_confirmed and not state.auto_confirm:
        return END  # pause for human checkpoint

    if not state.persona_role:
        return "synthesize"  # default: no persona routing

    routes: dict[str, str] = {
        "qa_lead": "impact_map",
        "operations": "impact_map",
        "developer": "synthesize",
        "product_owner": "consolidated_report",
    }
    return routes.get(state.persona_role, "synthesize")


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
    # Node implementations
    # ------------------------------------------------------------------

    async def _parse_document(self, state: PipelineState) -> dict[str, Any]:
        """Pre-processing node: PDF/Markdown → structured text.

        Only runs when ``input_mode == "document"`` (routed by ``_route_entry``).
        Uses the configured OCR backend (``OCR_BACKEND`` env var, default: pymupdf).

        16b Phase 2 (merged with AI-055 wiring — D2: protected file touched once):
        PDF documents are now parsed **page-aware** via
        :func:`src.pdf_ingest.ingest_pdf_page_aware`, so every chunk carries
        its physical page index and printed page label.  The full document
        text is fed into ``user_story`` (removes the 500-char ceiling), and
        page-tagged chunks are stored in ``raw_document_text`` for citation
        verification in Phase 3.
        """
        from pathlib import Path

        from src.ocr_backends import get_ocr_backend

        if not state.document_source:
            return {"errors": ["document_source is empty — nothing to parse"]}

        source_path = Path(state.document_source)
        if not source_path.exists():
            return {"errors": [f"Document not found: {state.document_source}"]}

        # 16b Phase 2 — page-aware PDF parsing (merged with AI-055 per-page OCR)
        if source_path.suffix.lower() == ".pdf":
            from src.pdf_ingest import ingest_pdf_page_aware

            # Use the tier-1 CPU OCR backend as the fallback for scanned pages
            ocr_backend = get_ocr_backend()
            ocr_hook: Callable[[Path, int], str] | None = None
            if ocr_backend.available:

                def ocr_hook(path: Path, page_num: int) -> str:  # type: ignore[redefinition]
                    return ocr_backend.parse_page(path, page_num)

            try:
                page_chunks = ingest_pdf_page_aware(source_path, ocr_fallback=ocr_hook)
            except Exception as e:
                logger.warning("Page-aware PDF parsing failed: %s", e)
                return {"errors": [f"Document parsing failed: {e}"]}

            if not page_chunks:
                return {"errors": ["Document is empty — nothing to analyse"]}

            # Build full text from page-tagged chunks (removes 500-char ceiling)
            full_text = "\n\n".join(c.text for c in page_chunks)

            logger.info(
                "Parsed document (page-aware): %d chunks, %d chars from %s",
                len(page_chunks),
                len(full_text),
                state.document_source,
            )

            return {
                "raw_document_text": full_text,
                # Feed the FULL document text into user_story (16b Phase 2)
                # — removes the 500-char ceiling that prevented boundary figures
                # deep in a policy from appearing in generated tests.
                "user_story": full_text,
            }

        # Non-PDF documents (Markdown) — use the OCR backend as before
        backend = get_ocr_backend()
        try:
            raw_text = backend.parse_markdown(source_path)
        except Exception as e:
            logger.warning("Document parsing failed (%s backend): %s", backend.name, e)
            return {"errors": [f"Document parsing failed: {e}"]}

        if not raw_text.strip():
            return {"errors": ["Document is empty — nothing to analyse"]}

        logger.info(
            "Parsed document: %d chars from %s (backend=%s)",
            len(raw_text),
            state.document_source,
            backend.name,
        )

        return {
            "raw_document_text": raw_text,
            "user_story": raw_text,
        }

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

        # Phase 1f/1g: extract change deltas from headings in document mode
        change_deltas: list[ChangeDelta] = []
        if state.input_mode == "document" and state.raw_document_text:
            from src.agents.ingestion import IngestionAgent

            change_deltas = IngestionAgent._extract_deltas_from_headings(state.raw_document_text)

        return {
            "story_analysis": StoryAnalysis(
                story_text=state.user_story,
                criteria=criteria,
                source_format="free-form",
            ),
            "change_deltas": change_deltas,
        }

    async def _plan(self, state: PipelineState) -> dict[str, Any]:
        """QA Director: story analysis → test conditions."""
        return await self._director_agent(state)

    async def _synthesize(self, state: PipelineState) -> dict[str, Any]:
        """Script Synthesizer: conditions → test code."""
        return await self._synthesizer_agent(state)

    async def _impact_map(self, state: PipelineState) -> dict[str, Any]:
        """Impact Mapper: ChangeDelta + persona_role → ImpactMap per change.

        For each ChangeDelta extracted by the Ingestion Agent, builds an
        ImpactMap describing the blast radius, regression areas, test
        scenarios, and risk level.  Uses rule-based heuristics.
        """
        deltas = state.change_deltas
        if not deltas:
            logger.info("Impact Mapper: no change deltas — skipping")
            return {}

        maps: list[ImpactMap] = []
        for delta in deltas:
            impact_radius = list(delta.affected_systems) if delta.affected_systems else []

            # Regression areas: systems NOT in the change but related
            regression_areas: list[str] = []
            if delta.category in ("modified", "removed"):
                regression_areas = ["integration-tests", "e2e-smoke"]

            # Test scenarios derived from change type
            test_scenarios: list[str] = []
            if delta.category == "new_feature":
                test_scenarios = [
                    f"Happy path: {delta.name}",
                    f"Error path: {delta.name} with invalid input",
                ]
            elif delta.category == "modified":
                test_scenarios = [
                    f"Verify {delta.name} still works as expected",
                    f"Verify {delta.name} handles edge cases after change",
                ]
            elif delta.category == "removed":
                test_scenarios = [
                    f"Verify {delta.name} is no longer accessible",
                    f"Verify dependent features still work without {delta.name}",
                ]

            # Risk level
            risk = "medium"
            if delta.category == "removed":
                risk = "high"
            elif delta.data_schema_changes:
                risk = "high"
            elif len(impact_radius) > 2:
                risk = "high"
            elif delta.category == "new_feature" and len(impact_radius) <= 1:
                risk = "low"

            if state.persona_role == "operations":
                # Ops persona adds deployment-focused scenarios
                test_scenarios.append("Verify deployment rollback works")
                test_scenarios.append("Verify monitoring alerts configured")

            maps.append(
                ImpactMap(
                    change_ref=delta.name,
                    impact_radius=impact_radius,
                    regression_areas=regression_areas,
                    test_scenarios=test_scenarios,
                    risk_level=risk,
                )
            )

        logger.info("Impact Mapper: built %d impact maps (persona=%s)", len(maps), state.persona_role)
        return {"impact_maps": maps}

    async def _consolidated_report(self, state: PipelineState) -> dict[str, Any]:
        """Build a ConsolidatedReport from all pipeline outputs.

        Used by the product_owner persona route — skips test code
        generation and produces a human-readable report instead.
        """
        from src.agents.pipeline_state import ConsolidatedReport

        deltas = state.change_deltas
        maps = state.impact_maps

        if not deltas:
            summary = "No changes detected in the document."
        else:
            categories: dict[str, int] = {}
            for d in deltas:
                categories[d.category] = categories.get(d.category, 0) + 1
            parts = [f"{count} {cat.replace('_', ' ')}" for cat, count in sorted(categories.items())]
            summary = f"Document analysis found: {', '.join(parts)}."

        tests = state.test_code if state.test_code else ""
        unresolved = [e for e in state.errors if e] + state.unresolved_placeholders

        report = ConsolidatedReport(
            executive_summary=summary,
            change_summary=list(deltas),
            impact_maps=list(maps),
            test_plan=list(state.test_conditions),
            generated_tests=tests,
            unresolved_items=list(unresolved),
        )

        logger.info("Consolidated Report: %d changes, %d impacts", len(deltas), len(maps))
        return {"consolidated_report": report}

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
        """Build and compile the StateGraph.

        Entry routing: text mode → ingest; document mode → parse_document → ingest.
        """

        # Use PipelineState as the state schema.
        # LangGraph support for TypedDict-based state is evolving;
        # we cast to Any for now since PipelineState is a dataclass.
        builder: Any = StateGraph(PipelineState)  # type: ignore[arg-type]

        builder.add_node("parse_document", self._parse_document)
        builder.add_node("ingest", self._ingest)
        builder.add_node("plan", self._plan)
        builder.add_node("impact_map", self._impact_map)
        builder.add_node("synthesize", self._synthesize)
        builder.add_node("consolidated_report", self._consolidated_report)
        builder.add_node("postprocess", self._postprocess)

        # Conditional entry: text mode → ingest; document mode → parse_document
        builder.set_conditional_entry_point(
            _route_entry,
            {
                "parse_document": "parse_document",
                "ingest": "ingest",
            },
        )

        builder.add_edge("parse_document", "ingest")
        builder.add_edge("ingest", "plan")

        # After QA Director: checkpoint + persona routing
        #   default → synthesize
        #   qa_lead / operations → impact_map → synthesize
        #   developer → synthesize
        #   product_owner → consolidated_report → END
        builder.add_conditional_edges(
            "plan",
            _after_qa_director,
            {
                "synthesize": "synthesize",
                "impact_map": "impact_map",
                "consolidated_report": "consolidated_report",
                END: END,
            },
        )

        builder.add_edge("impact_map", "synthesize")
        builder.add_edge("consolidated_report", END)

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
        conditions: str = "",
        base_url: str = "",
        additional_urls: list[str] | None = None,
        credential_profile: dict[str, str] | None = None,
        pom_mode: bool = False,
        auto_confirm: bool = False,
        input_mode: str = "text",
        document_source: str = "",
        persona_role: str = "",
    ) -> PipelineState:
        """Execute the full pipeline graph.

        Args:
            input_mode: ``"text"`` (default) or ``"document"`` for PDF/Markdown input.
            document_source: Path to PDF or Markdown file (required when ``input_mode="document"``).
            persona_role: ``"qa_lead"``, ``"product_owner"``, ``"developer"``, or ``"operations"``.

        Returns the final ``PipelineState`` with ``test_code`` populated.
        """
        initial = PipelineState(
            user_story=user_story,
            conditions=conditions,
            base_url=base_url,
            additional_urls=additional_urls or [],
            credential_profile=credential_profile,
            pom_mode=pom_mode,
            auto_confirm=auto_confirm,
            input_mode=input_mode,
            document_source=document_source,
            persona_role=persona_role,
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
