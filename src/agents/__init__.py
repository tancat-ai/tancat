"""LangGraph multi-agent pipelines.

The ``SkeletonGraph`` (Planner → Generator → Validator) handles the
skeleton-generation sub-phase.  The ``PipelineGraph`` (Ingestion →
QA Director → Script Synthesizer → Postprocessor) orchestrates the
full test-generation pipeline and composes ``SkeletonGraph`` as a
sub-component of the Synthesizer.

Enabled by default when langgraph is installed (``pip install ai-playwright-generator[langgraph]``).
Set ``LANGGRAPH_ENABLED=0`` to force the single-call linear pipeline.
Degrades gracefully if langgraph is not available.
"""

from __future__ import annotations

from typing import Any

from src.agents.pipeline_state import Criterion, PipelineState, StoryAnalysis
from src.agents.state import WorkflowState

# Lazy imports — langgraph is an optional dependency
_SkeletonGraph: Any = None
_PipelineGraph: Any = None
_QADirectorAgent: Any = None
_IngestionAgent: Any = None
_ScriptSynthesizerAgent: Any = None


def _lazy_import(name: str) -> Any:
    """Lazy-import a module that depends on optional langgraph."""
    if name == "SkeletonGraph":
        global _SkeletonGraph
        if _SkeletonGraph is None:
            from src.agents.graph import SkeletonGraph as SG

            _SkeletonGraph = SG
        return _SkeletonGraph
    if name == "PipelineGraph":
        global _PipelineGraph
        if _PipelineGraph is None:
            from src.agents.pipeline_graph import PipelineGraph as PG

            _PipelineGraph = PG
        return _PipelineGraph
    if name == "QADirectorAgent":
        global _QADirectorAgent
        if _QADirectorAgent is None:
            from src.agents.director import QADirectorAgent as QDA

            _QADirectorAgent = QDA
        return _QADirectorAgent
    if name == "IngestionAgent":
        global _IngestionAgent
        if _IngestionAgent is None:
            from src.agents.ingestion import IngestionAgent as IA

            _IngestionAgent = IA
        return _IngestionAgent
    if name == "ScriptSynthesizerAgent":
        global _ScriptSynthesizerAgent
        if _ScriptSynthesizerAgent is None:
            from src.agents.synthesizer import ScriptSynthesizerAgent as SSA

            _ScriptSynthesizerAgent = SSA
        return _ScriptSynthesizerAgent
    raise ValueError(f"Unknown lazy import: {name}")


__all__ = [
    "Criterion",
    "PipelineState",
    "StoryAnalysis",
    "WorkflowState",
]
