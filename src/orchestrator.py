"""Primary intelligent generation pipeline for the Streamlit app."""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from src.agents.pipeline_state import PipelineState
from src.code_postprocessor import normalise_generated_code
from src.journey_scraper import (
    CredentialProfile,
    JourneyResult,
    JourneyScraper,
    JourneyStep,
    execute_journey,
)
from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_resolver import PlaceholderResolver
from src.prerequisite_injector import PrerequisiteInjector
from src.prompt_builder import PromptBuilder, build_single_condition_prompt
from src.prompt_utils import (
    build_retry_conditions,
    count_conditions,
    prepare_conditions_for_generation,
)
from src.scraper import PageScraper, scrape_with_enrichment
from src.semantic_candidate_ranker import SemanticCandidateRanker
from src.skeleton_parser import SkeletonParser
from src.skeleton_validator import SkeletonValidator
from src.spec_analyzer import TestCondition, infer_condition_intent
from src.test_generator import TestGenerator
from src.test_structure_assembler import rebuild_test_structure
from src.url_utils import build_common_path_candidates, extract_route_concepts

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    """Captured metadata for the most recent pipeline run."""

    skeleton_code: str = ""
    final_code: str = ""
    pages_to_scrape: list[str] = field(default_factory=list)
    scraped_pages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    scraped_errors: dict[str, str] = field(default_factory=dict)
    page_requirements: list[PageRequirement] = field(default_factory=list)
    journeys: list[TestJourney] = field(default_factory=list)
    scraped_page_records: list[ScrapedPage] = field(default_factory=list)
    generated_page_objects: list[GeneratedPageObject] = field(default_factory=list)
    unresolved_placeholders: list[str] = field(default_factory=list)
    pages_visited: list[str] = field(default_factory=list)
    pom_mode: bool = False


class TestOrchestrator:
    """Coordinate skeleton generation, scraping, and placeholder replacement."""

    __test__ = False

    def __init__(
        self,
        test_generator: TestGenerator,
        *,
        credential_profile: CredentialProfile | None = None,
        journey_steps: list[JourneyStep] | None = None,
        pom_mode: bool = False,
        provider: str = "",
        model: str = "",
    ) -> None:
        self.test_generator = test_generator
        self.parser = SkeletonParser()
        self._starting_url: str | None = None
        self._credential_profile = credential_profile
        self._journey_steps: list[JourneyStep] | None = journey_steps
        self._pom_mode = pom_mode
        self._provider = provider
        self._model = model
        # RAG: optionally wire retrieval-augmented scoring
        rag_retriever = self._build_rag_retriever()
        self._placeholder_orchestrator = PlaceholderOrchestrator(
            starting_url=None,
            credential_profile=self._credential_profile,
            pom_mode=pom_mode,
            generator=test_generator.client,
            rag_retriever=rag_retriever,
        )
        # Delegate placeholder resolution to PlaceholderOrchestrator
        self.last_result: PipelineRunResult | None = None
        self._debug_enabled = os.getenv("PIPELINE_DEBUG", "").strip() == "1"
        # Diagnostics for journey execution
        self._pipeline_diagnostics: dict[str, Any] = {}
        self._last_phase_time: float = 0.0

        # Phase 1c: LangGraph multi-agent pipeline (PipelineGraph).
        # NOTE (2026-08-01): this graph is NOT wired into the user-facing path —
        # ``run_pipeline()`` (Streamlit/CLI/uat) always uses the linear pipeline.
        # The graph is reachable only via ``run_pipeline_via_graph()``, which the
        # eval harness exercises with ``--use-graph`` and which unit tests cover
        # directly. Initialisation here is harmless but unused in normal runs.
        langgraph_disabled = os.getenv("LANGGRAPH_ENABLED", "").strip() == "0"
        self._use_graph = not langgraph_disabled
        self._pipeline_graph: Any | None = None
        if self._use_graph:
            try:
                from src.agents.pipeline_graph import PipelineGraph

                self._pipeline_graph = PipelineGraph(
                    client=test_generator.client,
                    rag_retriever=rag_retriever,
                )
                logger.info("LangGraph multi-agent pipeline enabled")
            except Exception:
                logger.warning("LangGraph failed to initialise — falling back to linear pipeline", exc_info=True)
                self._use_graph = False

    @staticmethod
    def _build_rag_retriever() -> Any | None:
        """Build a RAGRetriever when RAG_ENABLED=1, else return None."""
        rag_enabled = os.getenv("RAG_ENABLED", "").strip() == "1"
        if not rag_enabled:
            return None
        try:
            from src.rag_retriever import RAGRetriever
            from src.rag_store import MilvusLiteBackend, RAGStore, SentenceTransformerEmbedder
            from src.storage import get_storage

            embedder = SentenceTransformerEmbedder()
            backend = MilvusLiteBackend(str(get_storage().rag_path()), embedder.dimension)
            store = RAGStore(backend, embedder)
            return RAGRetriever(store)
        except Exception:
            logger.warning("RAG enabled but failed to initialise — disabling", exc_info=True)
            return None

    # Backwards-compatible attributes: these let existing test code assign/mock
    # attributes like ``orchestrator.scraper``, ``orchestrator.resolver``, etc.
    # without reaching into ``_placeholder_orchestrator`` directly.

    @property
    def _resolver(self) -> PlaceholderResolver:
        """Backwards-compatible property for any code that references self.resolver."""
        return self._placeholder_orchestrator.resolver

    @property
    def _scraper(self) -> PageScraper:
        """Backwards-compatible property for any code that references self.scraper."""
        return self._placeholder_orchestrator.scraper

    @property
    def _page_object_builder(self) -> PageObjectBuilder:
        """Backwards-compatible property for any code that references self.page_object_builder."""
        return self._placeholder_orchestrator.page_object_builder

    @property
    def _semantic_ranker(self) -> SemanticCandidateRanker:
        """Backwards-compatible property for any code that references self.semantic_ranker."""
        return self._placeholder_orchestrator.semantic_ranker

    # Backwards-compatible: allow ``orchestrator.scraper`` to work as a shorthand
    # for tests that mock directly on the orchestrator instance.
    @property
    def scraper(self) -> PageScraper:
        """Backwards-compatible alias for ``self._scraper``."""
        return self._scraper

    @property
    def resolver(self) -> PlaceholderResolver:
        """Backwards-compatible alias for ``self._resolver``."""
        return self._resolver

    @property
    def page_object_builder(self) -> PageObjectBuilder:
        """Backwards-compatible alias for ``self._page_object_builder``."""
        return self._page_object_builder

    @property
    def semantic_ranker(self) -> SemanticCandidateRanker:
        """Backwards-compatible alias for ``self._semantic_ranker``."""
        return self._semantic_ranker

    def _debug(self, message: str) -> None:
        if self._debug_enabled:
            now = time.time()
            elapsed = now - self._last_phase_time if self._last_phase_time else 0
            self._last_phase_time = now
            if " start" in message or self._last_phase_time == 0:
                print(f"[pipeline] {message}", flush=True)
            else:
                print(f"[pipeline] {message}  [{elapsed:.1f}s]", flush=True)

    async def run_pipeline(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        consent_mode: str = "auto-dismiss",
        reviewed_conditions: list[TestCondition] | None = None,
        prebuilt_skeleton: str | None = None,
    ) -> str:
        """Execute the full intelligent pipeline and return final code.

        Args:
            user_story: The raw user story text.
            conditions: Numbered acceptance criteria.
            target_urls: Starting URLs for scraping.
            consent_mode: How to handle consent banners.
            reviewed_conditions: Pre-reviewed test conditions (bypasses skeleton generation).
            prebuilt_skeleton: Pre-generated skeleton code (from LangGraph graph).
                When provided, skips skeleton generation and uses this directly.

        Returns:
            Final test code with resolved placeholders.
        """
        self._starting_url = (target_urls[0].strip() if target_urls else None) or None
        # Build list of known URLs for journey resolution
        self._starting_url_list = list(set(target_urls or []))
        if self._starting_url:
            self._starting_url_list.append(self._starting_url)
        self._starting_url_list = list(set(self._starting_url_list))
        # Update the placeholder orchestrator with the starting URL
        self._placeholder_orchestrator._starting_url = self._starting_url

        if prebuilt_skeleton:
            # Phase 1d: Use pre-generated skeleton from the LangGraph graph
            skeleton_code = prebuilt_skeleton
            self._debug("phase=use_prebuilt_skeleton")
            generation_conditions = self._build_generation_conditions(conditions, reviewed_conditions)
            expected_test_count = len(generation_conditions) if reviewed_conditions else count_conditions(conditions)
            prepared_conditions = prepare_conditions_for_generation(conditions)
        else:
            self._debug("phase=generate_skeleton start")
            generation_conditions = self._build_generation_conditions(conditions, reviewed_conditions)
            expected_test_count = len(generation_conditions) if reviewed_conditions else count_conditions(conditions)
            prepared_conditions = prepare_conditions_for_generation(conditions)

            if reviewed_conditions and len(generation_conditions) > 1:
                skeleton_code = await self._generate_combined_skeleton_for_conditions(
                    user_story=user_story,
                    conditions=generation_conditions,
                    target_urls=target_urls or [],
                )
            else:
                skeleton_code = await self.test_generator.generate_skeleton(
                    user_story,
                    prepared_conditions,
                    target_urls=target_urls,
                    expected_count=expected_test_count,
                )
                skeleton_code = self.parser.normalise_placeholder_actions(skeleton_code)
                skeleton_error = self.parser.validate_skeleton(skeleton_code)
                if skeleton_error:
                    raise ValueError(skeleton_error)
                validator = SkeletonValidator()
                validation_result = validator.validate(skeleton_code)
                placeholders_found = self.parser.parse_placeholders(skeleton_code)

                # Phase 3: Detect zero-placeholder skeletons and retry once
                if (not validation_result.is_valid or not placeholders_found) and expected_test_count > 0:
                    if not validation_result.is_valid:
                        self._debug(f"skeleton validation violations: {validation_result.violations}")
                        logger.warning("Hallucinated CSS selectors found. Retrying with stricter prompt.")
                    else:
                        logger.warning(
                            "Zero placeholders found (expected %d tests). Retrying with stricter prompt.",
                            expected_test_count,
                        )
                    retry_conditions = build_retry_conditions(prepared_conditions, expected_test_count)
                    skeleton_code = await self.test_generator.generate_skeleton(
                        user_story,
                        retry_conditions + "\n\nCRITICAL: Every test body line must be a standalone placeholder "
                        "like {{{{CLICK:description}}}}.",
                        target_urls=target_urls,
                        expected_count=expected_test_count,
                    )
                    skeleton_code = self.parser.normalise_placeholder_actions(skeleton_code)
                    validation_result = validator.validate(skeleton_code)
                    if not validation_result.is_valid:
                        raise ValueError(
                            f"Skeleton contains hallucinated CSS selectors. {validation_result.suggestion}"
                        )
                elif not validation_result.is_valid:
                    raise ValueError(f"Skeleton contains hallucinated CSS selectors. {validation_result.suggestion}")

                self._debug("phase=generate_skeleton done")

        placeholders = self.parser.parse_placeholders(skeleton_code)
        journeys = self.parser.parse_test_journeys(skeleton_code)

        logger.info(
            "Skeleton parsed: expected=%d, journeys=%d, placeholders=%d",
            expected_test_count,
            len(journeys),
            len(placeholders),
        )
        for idx, j in enumerate(journeys):
            logger.info(
                "  journey[%d]: %s (lines %d-%d, steps=%d)", idx, j.test_name, j.start_line, j.end_line, len(j.steps)
            )

        if (
            not prebuilt_skeleton
            and not reviewed_conditions
            and expected_test_count
            and len(journeys) != expected_test_count
        ):
            logger.warning(
                "Journey count mismatch: expected=%d, got=%d. Retrying once with stricter prompt.",
                expected_test_count,
                len(journeys),
            )
            retry_conditions = build_retry_conditions(prepared_conditions, expected_test_count)
            skeleton_code = await self.test_generator.generate_skeleton(
                user_story,
                retry_conditions,
                target_urls=target_urls,
                expected_count=expected_test_count,
            )
            skeleton_code = self.parser.normalise_placeholder_actions(skeleton_code)
            skeleton_error = self.parser.validate_skeleton(skeleton_code)
            if skeleton_error:
                raise ValueError(skeleton_error)
            journeys = self.parser.parse_test_journeys(skeleton_code)
            placeholders = self.parser.parse_placeholders(skeleton_code)
            logger.info(
                "Retry complete: journeys=%d, placeholders=%d",
                len(journeys),
                len(placeholders),
            )

        page_requirements = self.parser.parse_page_requirements(skeleton_code)

        # Discover and scrape pages required for the journeys.
        # We combine two approaches:
        # 1. Static seed URLs (fast, provides baseline)
        # 2. Stateful journey discovery (follows test steps, handles auth/cart)
        pages_to_scrape = self._build_candidate_urls(
            seed_urls=target_urls or [],
            page_requirements=page_requirements,
            journeys=journeys,
            user_story=user_story,
            conditions=conditions,
        )
        self._debug(f"phase=scrape start urls={len(pages_to_scrape)}")

        # Approach 1: Initial static scrape
        raw_scraped_data = await self._scraper.scrape_all(pages_to_scrape) if pages_to_scrape else {}

        # AI-027: Apply vision enrichment to scraped elements when possible
        # Must run BEFORE building scraped_data so enriched elements flow through
        if self._scraper.last_scrape_results:
            results = list(self._scraper.last_scrape_results.values())
            enriched = scrape_with_enrichment(
                scrape_results=results,
                provider=self._provider,
                model=self._model,
            )
            # Update the scraper's stored results with enriched elements
            for result in enriched:
                self._scraper.last_scrape_results[result.url] = result

        # Re-extract elements from (now enriched) ScrapeResult objects
        # Fall back to raw_scraped_data if last_scrape_results is empty (mocked tests)
        scraped_data: dict[str, list[dict[str, Any]]]
        scraped_errors: dict[str, str]
        if self._scraper.last_scrape_results:
            scraped_data = {}
            scraped_errors = {}
            for url, result in self._scraper.last_scrape_results.items():
                scraped_data[url] = result.elements
                if result.error:
                    scraped_errors[url] = result.error
        else:
            scraped_data = {url: elements for url, (elements, _error, _final_url) in raw_scraped_data.items()}
            scraped_errors = {url: _error for url, (_elements, _error, _final) in raw_scraped_data.items() if _error}
        all_journey_scraped_data: dict[str, list[dict[str, Any]]] = {}

        # Approach 2: User-provided journey execution (Phase B — authenticated scraping)
        if self._journey_steps and len(self._journey_steps) > 0:
            self._debug("phase=journey_execution start (Phase B)")
            journey_result: JourneyResult = execute_journey(
                journey_steps=self._journey_steps,
                credential_profile=self._credential_profile,
                starting_url=self._starting_url,
            )
            journey_scraped: dict[str, list[dict[str, Any]]] = journey_result.captured_pages
            all_journey_scraped_data.update(journey_scraped)

            # Record diagnostics
            self._pipeline_diagnostics["journey_failed_steps"] = journey_result.failed_steps
            if journey_result.error_message:
                self._pipeline_diagnostics["journey_error"] = journey_result.error_message
            if journey_result.redirected_urls:
                self._pipeline_diagnostics["auth_redirects"] = journey_result.redirected_urls

            # Merge journey data with static scrape data (journey pages supplement static data)
            for url, elements in journey_scraped.items():
                if elements:
                    scraped_data[url] = elements
                    self._debug(f"journey execution captured: {url} ({len(elements)} elements)")
            self._debug("phase=journey_execution done")

        # Approach 3: Stateful journey discovery (the "User-Driven" fix)
        pages_visited: list[str] = []
        if self._starting_url:
            self._debug("phase=journey_discovery start")
            discovery_data, pages_visited = await self._scrape_journeys_statefully(
                journeys, self._starting_url, self._credential_profile
            )
            all_journey_scraped_data.update(discovery_data)
            # Journey-aware data takes precedence as it has correct state
            for url, elements in discovery_data.items():
                if elements:
                    scraped_data[url] = elements
                    self._debug(f"journey discovery enriched: {url} ({len(elements)} elements)")
            self._debug("phase=journey_discovery done")

        journey_selector_data = self._extract_journey_selectors(all_journey_scraped_data)
        for url, elements in journey_selector_data.items():
            if url not in scraped_data:
                scraped_data[url] = elements
            else:
                scraped_data[url] = scraped_data[url] + elements

        # Approach 4: Upgrade stateful pages with cart-seeding scraper.
        # This captures transient states (confirmation popups) and gated pages
        # (cart/checkout) that require a seeded session.
        if self._starting_url:
            self._debug("phase=stateful_upgrade start")
            scraped_data = await self._placeholder_orchestrator._upgrade_stateful_pages(scraped_data)
            self._debug("phase=stateful_upgrade done")

        # Track redirects to maintain correct page context
        redirects: dict[str, str] = {
            url: final_url for url, (_elems, _err, final_url) in raw_scraped_data.items() if url != final_url
        }

        self._debug("phase=scrape done")

        # Build keyword → URL mapping from discovered URLs (Phase 3: UrlResolver)
        # This maps PAGES_NEEDED keywords to actual URLs discovered by scraping
        if self._starting_url:
            keywords = [pr.keyword for pr in page_requirements]
            scraped_urls = list(scraped_data.keys())
            placeholder_descs = [ph.description for j in journeys for ph in j.placeholders]
            concepts_list = list(extract_route_concepts([user_story, conditions, *placeholder_descs, *keywords]))
            self._placeholder_orchestrator.url_resolver.build_mapping(
                keywords=keywords,
                scraped_urls=scraped_urls,
                seed_url=self._starting_url,
                concepts=concepts_list,
            )
            self._debug(f"url_resolver mappings: {self._placeholder_orchestrator.url_resolver.get_all_mappings()}")

        # Build page objects from ALL scraped URLs, not just the initial candidate list.
        # Journey discovery, stateful scraping, and cart seeding may have added extra
        # pages beyond the initial candidate set. Each unique URL gets its own page object.
        all_scraped_urls = list(scraped_data.keys())
        scraped_page_records = self._placeholder_orchestrator._build_scraped_page_records(
            all_scraped_urls, scraped_data, scraped_errors, redirects
        )
        generated_page_objects = self._placeholder_orchestrator._build_page_object_artifacts(scraped_page_records)
        self._debug(f"Built {len(generated_page_objects)} page objects from {len(all_scraped_urls)} scraped URLs")
        self._debug("phase=resolve_placeholders start")
        final_code = await self._placeholder_orchestrator._replace_placeholders_sequentially(
            skeleton_code=skeleton_code,
            journeys=journeys,
            page_requirements=page_requirements,
            seed_urls=target_urls or [],
            scraped_data=scraped_data,
            scraped_errors=scraped_errors,
        )
        self._debug("phase=resolve_placeholders done")

        # Inject @pytest.mark.evidence decorators so condition_ref is populated
        if generation_conditions:
            self._debug("phase=evidence_markers start")
            final_code = self._inject_evidence_markers(
                final_code,
                generation_conditions,
            )
            self._debug("phase=evidence_markers done")

        # Inject POM imports and instantiations when POM mode is enabled
        if self._pom_mode and generated_page_objects:
            self._debug("phase=pom_injection start")
            pom_imports = self._placeholder_orchestrator._build_pom_imports(generated_page_objects)
            pom_instantiation = self._placeholder_orchestrator._build_pom_instantiation(
                generated_page_objects, use_evidence_tracker=True
            )
            if pom_imports:
                final_code = self._inject_pom_imports(final_code, pom_imports)
            if pom_instantiation:
                final_code = self._inject_pom_instantiation(final_code, pom_instantiation)
            self._debug("phase=pom_injection done")

        # Prerequisite injection: detect dependency chains and inject auth steps
        self._debug("phase=prerequisite_injection start")
        injector = PrerequisiteInjector()
        if journeys and self._starting_url:
            resolved_journeys = self.parser.parse_test_journeys(final_code)
            injection_plans = injector.analyze_dependencies(
                journeys=resolved_journeys or journeys,
                starting_url=self._starting_url,
                scraped_pages=scraped_data,
            )
            if injection_plans:
                final_code = injector.inject_into_code(final_code, injection_plans)
                self._debug(f"phase=prerequisite_injection injected={len(injection_plans)} tests")
        self._debug("phase=prerequisite_injection done")

        final_code = normalise_generated_code(
            final_code, consent_mode=consent_mode, target_url=self._starting_url or ""
        )

        # Structural safety pass: rebuild the file from the parsed journey
        # model so the pipeline owns the structure. Module-level statement
        # leaks / dangling decorators (LLM skeleton mistakes that crashed
        # pytest at COLLECTION time) become structurally impossible.
        self._debug("phase=structure_assembly start")
        final_code = rebuild_test_structure(final_code)
        self._debug("phase=structure_assembly done")

        unresolved = [line.strip() for line in final_code.splitlines() if "pytest.skip(" in line]
        self.last_result = PipelineRunResult(
            skeleton_code=skeleton_code,
            final_code=final_code,
            pages_to_scrape=pages_to_scrape,
            scraped_pages=scraped_data,
            scraped_errors=scraped_errors,
            page_requirements=page_requirements,
            journeys=journeys,
            scraped_page_records=scraped_page_records,
            generated_page_objects=generated_page_objects,
            unresolved_placeholders=unresolved,
            pages_visited=pages_visited,
            pom_mode=self._pom_mode,
        )
        return final_code

    def _extract_journey_selectors(
        self,
        all_scraped_data: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Build synthetic resolver elements from journey-discovered selectors."""
        journey_elements: dict[str, list[dict[str, Any]]] = {}
        for url, elements in all_scraped_data.items():
            synthetic: list[dict[str, Any]] = []
            for element in elements:
                selector = str(element.get("selector", "")).strip()
                if not selector:
                    continue
                synthetic.append(
                    {
                        "selector": selector,
                        "text": element.get("text", ""),
                        "role": element.get("role", ""),
                        "href": element.get("href", ""),
                        "aria_label": element.get("aria_label", ""),
                        "accessible_name": element.get("accessible_name", ""),
                        "is_visible": element.get("is_visible", True),
                        "_journey_discovered": "true",
                    }
                )
            if synthetic:
                journey_elements[url] = synthetic
        return journey_elements

    async def _scrape_journeys_statefully(
        self,
        journeys: list[TestJourney],
        starting_url: str,
        credential_profile: CredentialProfile | None = None,
    ) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        """Scrape pages by following the generated skeleton journeys step-by-step.

        Journeys are independent — each starts from the same base URL and follows
        its own path. They run in parallel via asyncio.gather to cut the journey
        discovery phase time (~34s → ~10-15s expected).

        Returns a tuple of (scraped_data, pages_visited) where pages_visited is
        extracted from the journey scraper's context log.
        """
        if not starting_url:
            return {}, []

        import asyncio

        async def _scrape_one(journey: TestJourney) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
            """Scrape a single journey in its own JourneyScraper instance."""
            scraper = JourneyScraper(
                starting_url=starting_url,
                credential_profile=credential_profile,
            )
            steps: list[JourneyStep] = []

            for step in journey.steps:
                for placeholder in step.placeholders:
                    action = placeholder.action.lower()
                    if action == "goto":
                        url = self._resolver.resolve_url(placeholder.description, {}, self._starting_url_list)
                        if url:
                            steps.append(JourneyStep(action="navigate", url=url, description=placeholder.description))
                    elif action in ("click", "fill"):
                        fill_text: str | None = None
                        if action == "fill":
                            fill_text = self._placeholder_orchestrator._extract_fill_text(step.raw_line)
                            if not fill_text and ":" in placeholder.description:
                                parts = placeholder.description.split(":", 1)
                                fill_text = parts[1].strip() if len(parts) > 1 else None
                        steps.append(
                            JourneyStep(
                                action=action,
                                text=fill_text,
                                description=placeholder.description,
                            )
                        )
                    elif action == "assert":
                        steps.append(JourneyStep(action="scrape", description=placeholder.description))

            steps = self._normalize_journey_urls(steps)
            if not steps or steps[-1].action != "scrape":
                steps.append(JourneyStep(action="scrape", description="final page state"))

            self._debug(f"following discovery journey for: {journey.test_name}")
            journey_data = await scraper.scrape_journey(steps, credential_profile=credential_profile)
            pages = scraper.get_pages_visited()
            return journey_data, pages

        # Run all journeys concurrently — each gets its own browser subprocess
        tasks = [_scrape_one(j) for j in journeys]
        results = await asyncio.gather(*tasks)

        all_scraped_data: dict[str, list[dict[str, Any]]] = {}
        all_pages_visited: list[str] = []
        for data, pages in results:
            all_scraped_data.update(data)
            all_pages_visited.extend(pages)

        return all_scraped_data, all_pages_visited

    @staticmethod
    def _normalize_journey_urls(steps: list[JourneyStep]) -> list[JourneyStep]:
        """Normalize URLs in navigate steps to handle common path variations."""
        from src.url_utils import normalize_url_path

        normalized_steps: list[JourneyStep] = []
        for step in steps:
            if step.action == "navigate" and step.url:
                normalized_steps.append(
                    JourneyStep(
                        action=step.action,
                        url=normalize_url_path(step.url),
                        description=step.description,
                    )
                )
            else:
                normalized_steps.append(step)
        return normalized_steps

    # ------------------------------------------------------------------
    # Phase 1c: LangGraph graph-based pipeline (experimental / opt-in)
    # ------------------------------------------------------------------
    # NOTE (2026-08-01): not part of the user-facing flow. Only the eval
    # harness (``eval_harness.py run --use-graph``) and unit tests call
    # ``run_pipeline_via_graph``; the UI/CLI/uat all use ``run_pipeline``
    # (linear). See BACKLOG "LangGraph pipeline: dormant" note.

    async def run_pipeline_via_graph(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        auto_confirm: bool = False,
    ) -> PipelineState | None:
        """Execute the full pipeline through the LangGraph multi-agent graph.

        Returns the PipelineState after execution.  If the graph pauses
        at the human checkpoint (auto_confirm=False), the returned state
        has ``plan_confirmed=False`` and the caller should present the
        test plan to the user, then call ``resume_graph()`` to continue.

        Args:
            auto_confirm: If True, skip the human checkpoint.
        """
        if self._pipeline_graph is None:
            logger.warning("PipelineGraph not initialised — falling back to linear pipeline")
            return None

        base_url = target_urls[0] if target_urls else ""
        additional = target_urls[1:] if target_urls and len(target_urls) > 1 else []

        result = await self._pipeline_graph.run(
            user_story=user_story,
            conditions=conditions,
            base_url=base_url,
            additional_urls=additional,
            auto_confirm=auto_confirm,
            pom_mode=self._pom_mode,
        )

        # Store the result for the caller
        self._graph_state = result

        if result.plan_confirmed or auto_confirm:
            # Graph completed — skeleton code is ready
            logger.info(
                "Graph pipeline completed: %d conditions, %d chars of code",
                len(result.test_conditions),
                len(result.test_code),
            )
        else:
            logger.info("Graph paused at human checkpoint — %d conditions awaiting review", len(result.test_conditions))

        return result

    async def resume_graph(
        self,
        confirmed_conditions: list,
    ) -> PipelineState | None:
        """Resume the graph after the human checkpoint.

        Call this after the tester has reviewed and confirmed the test plan.
        """
        if self._pipeline_graph is None or not hasattr(self, "_graph_state"):
            return None

        return await self._pipeline_graph.resume_after_checkpoint(
            self._graph_state,
            confirmed_conditions,
        )

    @property
    def graph_conditions(self) -> list:
        """Access the test conditions from the last graph run (for UI display)."""
        if hasattr(self, "_graph_state") and self._graph_state is not None:
            return self._graph_state.test_conditions
        return []

    @staticmethod
    def _build_generation_conditions(
        conditions_text: str,
        reviewed_conditions: list[TestCondition] | None,
    ) -> list[TestCondition]:
        """Return ordered conditions used for skeleton generation."""
        if reviewed_conditions:
            return list(reviewed_conditions)

        inferred_conditions: list[TestCondition] = []
        condition_lines = [line.strip() for line in conditions_text.splitlines() if line.strip()]
        for index, raw_line in enumerate(condition_lines, start=1):
            condition_text = raw_line
            condition_id = f"TC{index:02d}"
            bracket_match = re.match(r"^\d+[.)]?\s*\[([^\]]+)\]\s*(.+?)(?:\s*->\s*Expected:\s*(.+))?$", raw_line)
            if bracket_match:
                condition_id = bracket_match.group(1).strip()
                condition_text = bracket_match.group(2).strip()
                expected = (bracket_match.group(3) or "Meets acceptance criteria.").strip()
            else:
                stripped_line = re.sub(r"^\d+[.)]\s*", "", raw_line).strip()
                expected = "Meets acceptance criteria."
                condition_text = stripped_line

            inferred_conditions.append(
                TestCondition(
                    id=condition_id,
                    type="happy_path",
                    text=condition_text,
                    expected=expected,
                    source=f"Condition {index}",
                    flagged=False,
                    src="manual",
                    intent=infer_condition_intent(condition_text),
                )
            )

        return inferred_conditions

    async def _generate_combined_skeleton_for_conditions(
        self,
        *,
        user_story: str,
        conditions: list[TestCondition],
        target_urls: list[str],
    ) -> str:
        """Generate one skeleton fragment per condition and combine them into one module."""
        known_urls_block = "\n".join(f"- {url}" for url in target_urls) if target_urls else "- No URLs were supplied."
        ordered_conditions = [
            f"[{condition.id}] {condition.text} -> Expected: {condition.expected}" for condition in conditions
        ]
        fragments: list[str] = []

        for condition in conditions:
            fragments.append(
                await self._generate_single_condition_fragment(
                    user_story=user_story,
                    known_urls_block=known_urls_block,
                    ordered_conditions=ordered_conditions,
                    condition=condition,
                )
            )

        combined = self._combine_condition_fragments(fragments)
        combined = self.parser.normalise_placeholder_actions(combined)
        skeleton_error = self.parser.validate_skeleton(combined)
        if skeleton_error:
            raise ValueError(skeleton_error)
        # Validate that the skeleton uses placeholders, not real CSS selectors
        validator = SkeletonValidator()
        validation_result = validator.validate(combined)
        if not validation_result.is_valid:
            self._debug(f"skeleton validation violations: {validation_result.violations}")
            raise ValueError(f"Skeleton contains hallucinated CSS selectors. {validation_result.suggestion}")
        self._debug("phase=generate_skeleton done")
        return combined

    async def _generate_single_condition_fragment(
        self,
        *,
        user_story: str,
        known_urls_block: str,
        ordered_conditions: list[str],
        condition: TestCondition,
    ) -> str:
        """Generate one skeleton fragment for one reviewed condition.

        Prompt assembly uses the PEP 750 t-string PromptBuilder — same pattern
        as ``TestGenerator._generate_skeleton_single_call``. Note this renders
        placeholder examples as single-brace ``{CLICK:...}`` (consistent with
        the main skeleton prompt); the parser accepts both brace forms.
        """
        rendered = PromptBuilder(
            build_single_condition_prompt(
                user_story=user_story,
                conditions_block="\n".join(f"- {c}" for c in ordered_conditions),
                known_urls_block=known_urls_block,
                target_condition_ref=condition.id,
                target_condition_text=condition.text,
                target_condition_expected=condition.expected,
            )
        ).render()
        # Structured audit trail — same seam as skeleton generation.
        logger.debug("llm_call=generate_single_condition_fragment fields=%s", rendered.to_log_entry())
        prompt = rendered.text
        fragment = await self.test_generator.client.generate(prompt)
        fragment = self.parser.normalise_placeholder_actions(fragment)

        if len(self.parser.parse_test_journeys(fragment)) != 1:
            correction = (
                prompt
                + "\n\nCORRECTION: Your previous answer did not contain exactly one pytest test function. "
                + "Regenerate the file with one test function for the target condition only."
            )
            fragment = await self.test_generator.client.generate(correction)
            fragment = self.parser.normalise_placeholder_actions(fragment)

        skeleton_error = self.parser.validate_skeleton(fragment)
        if skeleton_error:
            raise ValueError(skeleton_error)
        validator = SkeletonValidator()
        validation_result = validator.validate(fragment)

        if not validation_result.is_valid:
            self._debug(f"skeleton validation violations: {validation_result.violations}")
            logger.warning("Hallucinated CSS selectors found in fragment. Retrying with stricter prompt.")
            correction = (
                "You are a Playwright Python test engineer.\n"
                "\n"
                "Generate EXACTLY ONE pytest test function.\n"
                "\n"
                "=== CRITICAL RULE ===\n"
                "You MUST use ONLY placeholder tokens. NEVER write real Playwright locators.\n"
                "- WRONG: page.get_by_role('button', name='Login').click()\n"
                "- WRONG: page.locator('#email').fill('test@example.com')\n"
                "- WRONG: page.get_by_text('Add to cart').click()\n"
                "- CORRECT: {{CLICK:Login}}\n"
                "- CORRECT: {{FILL:email:test@example.com}}\n"
                "- CORRECT: {{CLICK:Add to cart}}\n"
                "\n"
                "=== ALLOWED PLACEHOLDERS ===\n"
                "{{GOTO:page description}}\n"
                "{{CLICK:button or link text}}\n"
                "{{FILL:field description:value to type}}\n"
                "{{ASSERT:what should be visible}}\n"
                "\n"
                "=== EXAMPLE ===\n"
                "def test_example(page, evidence_tracker):\n"
                "    {{GOTO:home}}\n"
                "    {{FILL:username:admin}}\n"
                "    {{FILL:password:secret}}\n"
                "    {{CLICK:Login}}\n"
                "    {{ASSERT:dashboard}}\n"
                "\n"
                "=== TARGET CONDITION ===\n"
                f"ID: {condition.id}\n"
                f"Description: {condition.text}\n"
                f"Expected: {condition.expected}\n"
                "\n"
                "Generate the test function now using ONLY placeholders."
            )
            fragment = await self.test_generator.client.generate(correction)
            fragment = self.parser.normalise_placeholder_actions(fragment)

            validation_result = validator.validate(fragment)
            if not validation_result.is_valid:
                self._debug(f"skeleton validation violations after retry: {validation_result.violations}")
                logger.warning(
                    "Second retry failed for fragment %s. Attempting third retry with minimal prompt.", condition.id
                )
                minimal_prompt = (
                    f"Generate one pytest test function for: {condition.text}\n"
                    f"Expected: {condition.expected}\n"
                    "Output ONLY this format (replace placeholders, do NOT write real locators):\n\n"
                    "def test_xxx(page, evidence_tracker):\n"
                    "    {{GOTO:page}}\n"
                    "    {{CLICK:button text}}\n"
                    "    {{FILL:field:value}}\n"
                    "    {{ASSERT:what to see}}\n\n"
                    "Every body line MUST be a {{ACTION:description}} placeholder. No real code."
                )
                fragment = await self.test_generator.client.generate(minimal_prompt)
                fragment = self.parser.normalise_placeholder_actions(fragment)
                validation_result = validator.validate(fragment)
                if not validation_result.is_valid:
                    self._debug(f"skeleton validation violations after second retry: {validation_result.violations}")
                    raise ValueError(f"Skeleton contains hallucinated CSS selectors. {validation_result.suggestion}")

        return fragment

    def _combine_condition_fragments(self, fragments: list[str]) -> str:
        """Combine one-condition skeleton fragments into a single skeleton module.

        Pages are now discovered organically by the journey scraper at runtime.
        PAGES_NEEDED pre-declaration is no longer emitted in combined output.
        """
        body_blocks: list[str] = []

        for fragment in fragments:
            fragment_body = self._strip_imports_and_pages_needed(fragment).strip()
            body_blocks.append(fragment_body)

        combined_parts = [
            "from playwright.sync_api import Page, expect",
            "import pytest",
            "",
            "\n\n".join(block for block in body_blocks if block),
        ]

        return "\n".join(part for part in combined_parts if part != "")

    @staticmethod
    def _strip_imports_and_pages_needed(code: str) -> str:
        """Return fragment body without import lines or trailing PAGES_NEEDED block."""
        lines = code.splitlines()
        cleaned_lines: list[str] = []
        inside_pages_needed = False

        for line in lines:
            stripped = line.strip()
            if stripped == "# PAGES_NEEDED:":
                inside_pages_needed = True
                continue
            if inside_pages_needed:
                if stripped.startswith("# -"):
                    continue
                if not stripped:
                    continue
                inside_pages_needed = False

            if stripped.startswith("from playwright.sync_api import") or stripped == "import pytest":
                continue

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()

    def _build_candidate_urls(
        self,
        seed_urls: list[str],
        page_requirements: list[PageRequirement],
        journeys: list[TestJourney],
        user_story: str,
        conditions: str,
    ) -> list[str]:
        """Return URLs to pre-scrape before placeholder resolution.

        Combines:
        - Seed URLs (the starting page)
        - URLs explicitly referenced by GOTO/URL placeholders in journeys
        - Common path candidates derived from user story and placeholder descriptions

        Pre-scraping these URLs ensures placeholder resolution has element data
        available for all pages referenced in the test journeys, not just the
        pages the journey scraper happens to visit.
        """
        candidate_urls: list[str] = list(seed_urls)

        # Collect URLs from GOTO/URL placeholders in journeys
        for journey in journeys:
            for step in journey.steps:
                for placeholder in step.placeholders:
                    if placeholder.action in {"GOTO", "URL"}:
                        desc = placeholder.description
                        # Handle keyword descriptions like "home", "cart", "checkout"
                        # by resolving them through the placeholder resolver
                        resolved = self.resolver.resolve_url(desc, {})
                        if resolved:
                            candidate_urls.append(resolved)
                        elif desc.startswith("http"):
                            candidate_urls.append(desc)

        # Add heuristic path candidates from user story and conditions
        concepts = extract_route_concepts([user_story, conditions])
        candidate_urls.extend(build_common_path_candidates(seed_urls, concepts))

        # Deduplicate while preserving order
        return list(dict.fromkeys(candidate_urls))

    @staticmethod
    def _inject_pom_imports(code: str, pom_imports: list[str]) -> str:
        """Inject POM import statements after existing imports.

        Finds the last existing import line and inserts POM imports after it.
        Skips any import lines that are already present in the code to avoid
        duplicate imports when the combined skeleton already contains them.
        """
        existing_code = code
        new_imports = [imp for imp in pom_imports if imp.strip() not in existing_code]
        if not new_imports:
            return code

        lines = code.splitlines()
        insert_index: int = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("import "):
                insert_index = i + 1
            elif stripped and not stripped.startswith("#"):
                # First non-import, non-comment line — stop scanning
                break

        import_block = "\n".join(new_imports)
        new_lines = lines[:insert_index] + [import_block, ""] + lines[insert_index:]
        return "\n".join(new_lines)

    @staticmethod
    def _inject_pom_instantiation(code: str, pom_instantiation: list[str]) -> str:
        """Inject POM instantiation lines at the start of each test function.

        Finds each `def test_` line and inserts indented instantiation lines after it.
        Skips instantiation if those lines are already present in the function body
        to avoid duplicate instances when the skeleton already contains them.
        """
        lines = code.splitlines()
        indented_lines = [f"    {line}" for line in pom_instantiation]
        instantiation_block = "\n".join(indented_lines)
        new_lines: list[str] = []
        i = 0

        while i < len(lines):
            line = lines[i]
            new_lines.append(line)
            stripped = line.strip()
            if stripped.startswith("def test_") and "(" in stripped and ":":
                # Scan the next few lines to see if instantiations are already there
                scan_limit = min(i + len(pom_instantiation) + 5, len(lines))
                already_present = any(
                    any(inst_line.strip() in lines[j].strip() for inst_line in pom_instantiation)
                    for j in range(i + 1, scan_limit)
                )
                if not already_present:
                    new_lines.append(instantiation_block)
            i += 1

        return "\n".join(new_lines)

    @staticmethod
    def _inject_evidence_markers(
        code: str,
        conditions: list[TestCondition],
    ) -> str:
        """Inject @pytest.mark.evidence(condition_ref=..., story_ref=...) before each test function.

        Maps condition IDs to test functions by order — the Nth condition maps to the Nth test.
        If a test already has the decorator it is left untouched.
        """
        lines = code.splitlines()
        new_lines: list[str] = []
        test_match_re = re.compile(r"^def\s+test_")
        has_decorator_re = re.compile(r"^@pytest\.mark\.evidence")
        condition_idx = 0
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check if this is a test function definition
            if test_match_re.match(stripped):
                # Check if the previous line already has the decorator
                if new_lines and has_decorator_re.match(new_lines[-1].strip()):
                    # Already decorated — skip injection
                    condition_idx += 1
                elif condition_idx < len(conditions):
                    # Inject the decorator
                    condition = conditions[condition_idx]
                    decorator = (
                        f'@pytest.mark.evidence(condition_ref="{condition.id}", story_ref="S{condition_idx + 1:02d}")'
                    )
                    new_lines.append(decorator)
                    condition_idx += 1
                else:
                    # More tests than conditions — use a default
                    decorator = f'@pytest.mark.evidence(condition_ref="TC{condition_idx + 1:02d}", story_ref="S{condition_idx + 1:02d}")'
                    new_lines.append(decorator)
                    condition_idx += 1

            new_lines.append(line)
            i += 1

        return "\n".join(new_lines)

    # Backwards-compatible delegation methods for code that references these directly on TestOrchestrator.
    async def _resolve_placeholder_for_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
    ) -> tuple[str, str | None, str | None]:
        """Backwards-compatible: delegate to PlaceholderOrchestrator._resolve_placeholder_for_page.

        Returns:
            3-tuple of (resolved_value, next_url, assertion_type).
            assertion_type is None for non-ASSERT actions.
        """
        return await self._placeholder_orchestrator._resolve_placeholder_for_page(
            action=action,
            description=description,
            current_url=current_url,
            scraped_data=scraped_data,
            scraped_errors=scraped_errors,
        )
