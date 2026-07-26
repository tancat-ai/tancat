"""Full-pipeline state for the multi-agent orchestration graph.

Distinct from ``src.agents.state.WorkflowState`` which covers only the
skeleton-generation sub-phase.  This state flows through the complete
pipeline: Ingestion → QA Director → Script Synthesizer → Postprocessor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Criterion:
    """A single acceptance criterion extracted from the user story."""

    ref: str  # "TC01.03"
    description: str
    condition_type: str  # "happy_path" | "boundary" | "negative" | "exploratory" | "ambiguity"
    priority: str  # "high" | "medium" | "low"
    source_text: str = ""
    needs_clarification: bool = False
    clarification_question: str = ""
    prerequisite_refs: list[str] = field(default_factory=list)


@dataclass
class StoryAnalysis:
    """Output of the Ingestion Agent — structured understanding of the user story."""

    story_text: str = ""
    criteria: list[Criterion] = field(default_factory=list)
    domain_terms: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    boundary_values: list[dict[str, str]] = field(default_factory=list)
    source_format: str = ""  # "gherkin" | "jira" | "free-form" | "numbered"


@dataclass
class PipelineState:
    """Typed state flowing through all nodes of the multi-agent pipeline.

    Serializable — LangGraph checkpoints persist this between nodes.
    """

    # ── Input ──────────────────────────────────────────────────────
    user_story: str = ""
    base_url: str = ""
    additional_urls: list[str] = field(default_factory=list)
    credential_profile: dict[str, str] | None = None
    pom_mode: bool = False

    # ── Intermediate ───────────────────────────────────────────────
    story_analysis: StoryAnalysis | None = None
    test_conditions: list[Criterion] = field(default_factory=list)
    plan_confirmed: bool = False
    scraped_pages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    # ── Output ─────────────────────────────────────────────────────
    test_code: str = ""
    pom_classes: list[dict[str, Any]] = field(default_factory=list)
    unresolved_placeholders: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # ── Control ────────────────────────────────────────────────────
    max_retries: int = 2
    retry_count: int = 0
    auto_confirm: bool = False  # True in CLI/CI mode — skip human checkpoint

    def to_dict(self) -> dict[str, Any]:
        """Serialize for LangGraph checkpointing."""
        import dataclasses

        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineState:
        """Deserialize from a checkpoint dict."""
        analysis = data.pop("story_analysis", None)
        story_analysis = None
        if analysis and isinstance(analysis, dict):
            criteria_list = analysis.pop("criteria", [])
            criteria = [Criterion(**c) if isinstance(c, dict) else c for c in criteria_list]
            story_analysis = StoryAnalysis(criteria=criteria, **analysis)

        return cls(story_analysis=story_analysis, **data)
