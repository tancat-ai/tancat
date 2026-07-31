"""Ingestion Agent — analyses user story text into structured StoryAnalysis.

Wraps the existing ``SpecAnalyzer`` for deterministic criteria extraction
and layers RAG retrieval for domain-specific context enrichment.

Phase 1b: real LLM analysis via SpecAnalyzer + optional RAG.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.pipeline_state import ChangeDelta, Criterion, DataSchemaChange, PipelineState, StoryAnalysis
from src.spec_analyzer import SpecAnalyzer

logger = logging.getLogger(__name__)


class IngestionAgent:
    """Analyses user story text and produces structured ``StoryAnalysis``.

    Uses ``SpecAnalyzer`` for criteria extraction (handles numbered lists,
    comma-separated concerns, and LLM fallback for unstructured text).
    Optionally queries the RAG vector store for domain-specific patterns.

    Args:
        client: LLMClient for LLM fallback in SpecAnalyzer.
        rag_retriever: Optional RAGRetriever for domain pattern enrichment.
    """

    def __init__(self, client: Any, rag_retriever: Any | None = None) -> None:
        self._client = client
        self._analyzer = SpecAnalyzer(client)
        self._rag = rag_retriever

    async def __call__(self, state: PipelineState) -> dict[str, Any]:
        """Analyse the user story and return ``story_analysis`` for the graph state.

        When ``state.conditions`` is provided (numbered acceptance criteria),
        each line becomes its own criterion — no LLM needed for extraction.
        Falls back to SpecAnalyzer for unstructured story-only input.
        """
        story_text = state.user_story
        if not story_text or not story_text.strip():
            return {
                "story_analysis": StoryAnalysis(story_text=""),
                "errors": ["Empty user story — nothing to analyse"],
            }

        # 1. Deterministic: use acceptance criteria if provided
        if state.conditions and state.conditions.strip():
            conditions = self._criteria_from_text(state.conditions)
            logger.info("Ingestion: extracted %d criteria from acceptance criteria text", len(conditions))
        else:
            # Fall back to SpecAnalyzer for unstructured story text
            try:
                conditions = self._analyzer.analyze(story_text)
            except Exception as e:
                logger.warning("SpecAnalyzer failed: %s — using raw text", e)
                conditions = self._criteria_from_text(story_text)

        # 1b. Document mode: extract change deltas from raw_document_text
        change_deltas: list[ChangeDelta] = []
        if state.input_mode == "document" and state.raw_document_text:
            try:
                change_deltas = await self._extract_change_deltas(state.raw_document_text)
                logger.info("Ingestion: extracted %d change deltas from document", len(change_deltas))
            except Exception as e:
                logger.warning("Change delta extraction failed: %s — falling back to headings", e)
                change_deltas = self._extract_deltas_from_headings(state.raw_document_text)

        # 2. Query RAG for domain context (non-blocking, best-effort)
        domain_terms: list[str] = []
        if self._rag:
            try:
                patterns = self._rag.retrieve(story_text, action_type="ASSERT")
                seen: set[str] = set()
                for p in patterns[:10]:
                    desc = getattr(p, "description", "")
                    if desc and desc not in seen:
                        domain_terms.append(desc)
                        seen.add(desc)
            except Exception as e:
                logger.debug("RAG retrieval skipped: %s", e)

        # 3. Extract assumptions from flagged conditions
        assumptions = [
            c.expected for c in conditions if c.flagged and c.expected and "Needs refinement" not in c.expected
        ]

        # 4. Map SpecAnalyzer.TestCondition → pipeline Criterion
        criteria = [
            Criterion(
                ref=c.id,
                description=c.text,
                condition_type=c.type,
                priority="medium",
                source_text=c.source,
                needs_clarification=c.flagged,
                clarification_question=c.expected if c.flagged else "",
            )
            for c in conditions
        ]

        # 5. Detect source format
        source_format = "free-form"
        if conditions:
            # Heuristic: numbered criteria → "numbered", Gherkin keywords → "gherkin"
            first_text = conditions[0].source.lower() if conditions else ""
            if "acceptance criteria" in first_text or len(conditions) > 1:
                source_format = "numbered"
            if any(kw in story_text.lower() for kw in ("given ", "when ", "then ", "feature:")):
                source_format = "gherkin"

        return {
            "story_analysis": StoryAnalysis(
                story_text=story_text,
                criteria=criteria,
                domain_terms=domain_terms,
                assumptions=assumptions,
                source_format=source_format,
            ),
            "change_deltas": change_deltas,
        }

    @staticmethod
    def _criteria_from_text(conditions_text: str) -> list:
        """Extract criteria deterministically from numbered acceptance criteria.

        Each non-empty line becomes one ``TestCondition``.  Strips leading
        numbering (e.g. '1.', '1)', '[TC-01]').  Returns objects
        compatible with ``SpecAnalyzer.TestCondition``.
        """
        import re

        from src.spec_analyzer import TestCondition

        lines = [line.strip() for line in conditions_text.splitlines() if line.strip()]
        if not lines:
            return []

        conditions: list[TestCondition] = []
        for i, line in enumerate(lines, start=1):
            # Strip leading numbers and markers
            cleaned = re.sub(r"^\d+[.)\]\s]+", "", line).strip()
            cleaned = re.sub(r"^\[([^\]]+)\]\s*", "", cleaned).strip()
            if not cleaned:
                continue

            ref = f"TC01.{i:02d}"
            conditions.append(
                TestCondition(
                    id=ref,
                    type="happy_path",
                    text=cleaned,
                    expected="Meets acceptance criteria.",
                    source=line,
                    flagged=False,
                    src="ai",
                    intent="journey_step",
                )
            )

        return conditions

    # ------------------------------------------------------------------
    # Change delta extraction (Phase 1g)
    # ------------------------------------------------------------------

    async def _extract_change_deltas(self, document_text: str) -> list[ChangeDelta]:
        """Extract structured change deltas from a spec document via LLM.

        Sends a prompt asking the LLM to identify new features, modified
        systems, unchanged systems, and data schema changes.  Parses the
        JSON response into ``ChangeDelta`` objects.

        Falls back to heading-based extraction if the LLM returns
        unparseable output.
        """
        if self._client is None:
            return self._extract_deltas_from_headings(document_text)

        # Truncate very large documents to avoid token overflow
        text = document_text[:8000]

        prompt = f"""Analyse the following spec document and extract structured change information.

<document>
{text}
</document>

Return a JSON object with a "change_deltas" array. Each entry must have:
- category: "new_feature" | "modified" | "removed" | "unchanged"
- name: short human-readable name
- description: what changed and why
- affected_systems: list of downstream systems impacted (can be empty)
- data_schema_changes: list of {{field, change_type ("NEW"|"MODIFIED"|"REMOVED"), old_value, new_value, migration_notes}} (can be empty)

Return ONLY valid JSON, no markdown fences, no prose."""

        try:
            response = await self._client.generate(
                prompt,
                timeout=120,
                temperature=0,
            )
            deltas = self._parse_change_deltas_json(response)
            if not deltas:
                # Parse succeeded but returned empty — fall back to headings
                return self._extract_deltas_from_headings(document_text)
            return deltas
        except Exception as e:
            logger.warning("LLM change delta extraction failed: %s", e)
            return self._extract_deltas_from_headings(document_text)

    @staticmethod
    def _extract_deltas_from_headings(text: str) -> list[ChangeDelta]:
        """Deterministic fallback: extract markdown headings as feature names.

        Each ``##`` or ``###`` heading becomes a ``ChangeDelta``.  Prefixes
        like ``New:``, ``Modified:`` and suffixes like ``[NEW FEATURE]``,
        ``[REMOVED]`` are stripped; the prefix is used to infer the category.
        ``#`` (h1) headings are skipped as document titles.
        """
        import re

        deltas: list[ChangeDelta] = []
        heading_pattern = re.compile(r"^#{2,3}\s+(.+)$", re.MULTILINE)
        prefix_pattern = re.compile(
            r"^(New|Modified|Removed|Unchanged)\s*:\s*", re.IGNORECASE
        )
        suffix_pattern = re.compile(
            r"\s*\[(NEW FEATURE|MODIFIED|REMOVED|UNCHANGED)\]\s*$", re.IGNORECASE
        )
        jira_pattern = re.compile(r"^[A-Z]+-\d+\s*:\s*")
        matches = heading_pattern.findall(text)

        for _i, heading in enumerate(matches):
            heading = heading.strip()
            if not heading or len(heading) < 3:
                continue

            lower = heading.lower()
            if lower in ("overview", "introduction", "background", "appendix", "table of contents"):
                continue
            # Also skip sections with "Unchanged" prefix or suffix — they're not deltas
            prefix_match = prefix_pattern.match(heading)
            skip_unchanged = bool(
                prefix_match and prefix_match.group(1).lower() == "unchanged"
            )
            suffix_match = suffix_pattern.search(heading)
            if suffix_match and "UNCHANGED" in suffix_match.group(1).upper():
                skip_unchanged = True
            if skip_unchanged:
                continue

            # Infer category from prefix
            category = "modified"
            prefix_match = prefix_pattern.match(heading)
            if prefix_match:
                cat = prefix_match.group(1).lower()
                if cat != "unchanged":
                    category = cat
                heading = prefix_pattern.sub("", heading).strip()
            else:
                jira_match = jira_pattern.match(heading)
                if jira_match:
                    heading = jira_pattern.sub("", heading).strip()

            # Strip bracket suffix for clean name
            heading = suffix_pattern.sub("", heading).strip()

            deltas.append(
                ChangeDelta(
                    category=category,
                    name=heading,
                    description=f"Change described in section: {heading}",
                    affected_systems=[],
                )
            )

        return deltas

    @staticmethod
    def _parse_change_deltas_json(response: str) -> list[ChangeDelta]:
        """Parse LLM JSON response into ChangeDelta objects.

        Handles common LLM output issues: markdown fences, trailing
        commas, and prose wrapping.
        """
        import json
        import re

        # Strip markdown fences
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"^```(?:json)?\s*", "", response)
            response = re.sub(r"\s*```$", "", response)

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON object within the response
            match = re.search(r"\{[^{}]*\"change_deltas\"[^{}]*\[[^]]*\][^{}]*\}", response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        raw_deltas = data.get("change_deltas", [])
        if not isinstance(raw_deltas, list):
            return []

        deltas: list[ChangeDelta] = []
        for rd in raw_deltas:
            if not isinstance(rd, dict):
                continue

            schema_changes: list[DataSchemaChange] = []
            for sc in rd.get("data_schema_changes", []) or []:
                if isinstance(sc, dict):
                    schema_changes.append(
                        DataSchemaChange(
                            field=str(sc.get("field", "")),
                            change_type=str(sc.get("change_type", "MODIFIED")),
                            old_value=str(sc.get("old_value", "")),
                            new_value=str(sc.get("new_value", "")),
                            migration_notes=str(sc.get("migration_notes", "")),
                        )
                    )

            deltas.append(
                ChangeDelta(
                    category=str(rd.get("category", "modified")),
                    name=str(rd.get("name", "")),
                    description=str(rd.get("description", "")),
                    affected_systems=[str(s) for s in rd.get("affected_systems", []) or []],
                    data_schema_changes=schema_changes,
                )
            )

        return deltas
