"""Full-pipeline state for the multi-agent orchestration graph.

Distinct from ``src.agents.state.WorkflowState`` which covers only the
skeleton-generation sub-phase.  This state flows through the complete
pipeline: Ingestion → QA Director → Script Synthesizer → Postprocessor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Document-mode dataclasses (Phase 1f) ────────────────────────────


@dataclass
class DataSchemaChange:
    """A single data schema modification extracted from a spec document."""

    field: str  # e.g. "customer_id"
    change_type: str  # "NEW" | "MODIFIED" | "REMOVED"
    old_value: str  # e.g. "VARCHAR(8)"
    new_value: str  # e.g. "VARCHAR(10)"
    migration_notes: str = ""  # breaking change? rollback plan?


@dataclass
class ChangeDelta:
    """A single change extracted from a spec document."""

    category: str  # "new_feature" | "modified" | "removed" | "unchanged"
    name: str  # human-readable name
    description: str  # what changed and why
    affected_systems: list[str] = field(default_factory=list)
    data_schema_changes: list[DataSchemaChange] = field(default_factory=list)


@dataclass
class ImpactMap:
    """Cross-reference of changes to affected test areas."""

    change_ref: str  # which ChangeDelta.name this maps to
    impact_radius: list[str] = field(default_factory=list)  # systems/modules in blast radius
    regression_areas: list[str] = field(default_factory=list)  # unchanged systems needing sanity checks
    test_scenarios: list[str] = field(default_factory=list)  # concrete test ideas
    risk_level: str = "medium"  # "high" | "medium" | "low"


@dataclass
class ConsolidatedReport:
    """Final output of the document-driven pipeline."""

    executive_summary: str = ""
    change_summary: list[ChangeDelta] = field(default_factory=list)
    impact_maps: list[ImpactMap] = field(default_factory=list)
    test_plan: list[Criterion] = field(default_factory=list)  # type: ignore[name-defined]  # forward ref
    generated_tests: str = ""  # pytest code
    unresolved_items: list[str] = field(default_factory=list)  # questions for the human


# ── Core pipeline dataclasses ───────────────────────────────────────


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
    # ── 16b provenance (Phase 1 — data model) ─────────────────────
    #: Citations linking this criterion to verified document locations.
    #: Empty = no document provenance (pasted/typed requirements path).
    source_refs: list[Any] = field(default_factory=list)  # list[SourceRef] (forward ref)
    #: LLM rationale grounded in citations (≤ ~400 chars). Empty for unresolved.
    justification: str = ""


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
    conditions: str = ""  # acceptance criteria — used by Ingestion Agent
    base_url: str = ""
    additional_urls: list[str] = field(default_factory=list)
    credential_profile: dict[str, str] | None = None
    pom_mode: bool = False

    # ── Document Input (Phase 1f — all optional, empty in text mode) ──
    input_mode: str = "text"  # "text" | "document"
    raw_document_text: str = ""  # parsed PDF/Markdown content
    document_source: str = ""  # original filename
    change_deltas: list[ChangeDelta] = field(default_factory=list)
    persona_role: str = ""  # "qa_lead" | "product_owner" | "developer" | "operations"
    impact_maps: list[ImpactMap] = field(default_factory=list)
    consolidated_report: ConsolidatedReport | None = None

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
        from src.source_refs import SourceRef

        def _deserialize_criterion(c: Any) -> Any:
            """Deserialize a criterion, handling source_refs (16b Phase 1)."""
            if not isinstance(c, dict):
                return c
            # Handle source_refs: list of dicts → list of SourceRef
            source_refs = c.get("source_refs", [])
            if source_refs and isinstance(source_refs[0], dict):
                c["source_refs"] = [SourceRef.from_dict(r) for r in source_refs]
            return Criterion(**c)

        analysis = data.pop("story_analysis", None)
        story_analysis = None
        if analysis and isinstance(analysis, dict):
            criteria_list = analysis.pop("criteria", [])
            criteria = [_deserialize_criterion(c) for c in criteria_list]
            story_analysis = StoryAnalysis(criteria=criteria, **analysis)

        # Also handle test_conditions (16b Phase 1)
        test_conditions = data.get("test_conditions", [])
        if test_conditions and isinstance(test_conditions[0], dict):
            data["test_conditions"] = [_deserialize_criterion(c) for c in test_conditions]

        return cls(story_analysis=story_analysis, **data)
