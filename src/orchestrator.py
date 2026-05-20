"""Primary intelligent generation pipeline for the Streamlit app."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

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
from src.prompt_utils import (
    build_retry_conditions,
    build_single_condition_skeleton_prompt,
    count_conditions,
    prepare_conditions_for_generation,
)
from src.scraper import PageScraper
from src.semantic_candidate_ranker import SemanticCandidateRanker
from src.skeleton_parser import SkeletonParser
from src.skeleton_validator import SkeletonValidator
from src.spec_analyzer import TestCondition, infer_condition_intent
from src.test_generator import TestGenerator
from src.url_utils import extract_route_concepts

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    """Captured metadata for the most recent pipeline run."""

    skeleton_code: str
    final_code: str
    pages_to_scrape: list[str]
    scraped_pages: dict[str, list[dict[str, str]]]
    scraped_errors: dict[str, str] = field(default_factory=dict)
    page_requirements: list[PageRequirement] = field(default_factory=list)
    journeys: list[TestJourney] = field(default_factory=list)
    scraped_page_records: list[ScrapedPage] = field(default_factory=list)
    generated_page_objects: list[GeneratedPageObject] = field(default_factory=list)
    unresolved_placeholders: list[str] = field(default_factory=list)


class TestOrchestrator:
    """Coordinate skeleton generation, scraping, and placeholder replacement."""

    __test__ = False

    def __init__(
        self,
        test_generator: TestGenerator,
        *,
        credential_profile: CredentialProfile | None = None,
        journey_steps: list[JourneyStep] | None = None,
    ) -> None:
        self.test_generator = test_generator
        self.parser = SkeletonParser()
        self._starting_url: str | None = None
        self._credential_profile = credential_profile
        self._journey_steps: list[JourneyStep] | None = journey_steps
        self._placeholder_orchestrator = PlaceholderOrchestrator(
            starting_url=None, credential_profile=self._credential_profile
        )
        # Delegate placeholder resolution to PlaceholderOrchestrator
        self.last_result: PipelineRunResult | None = None
        self._debug_enabled = os.getenv("PIPELINE_DEBUG", "").strip() == "1"
        # Diagnostics for journey execution
        self._pipeline_diagnostics: dict[str, Any] = {}

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
            print(f"[pipeline] {message}", flush=True)

    async def run_pipeline(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        consent_mode: str = "auto-dismiss",
        reviewed_conditions: list[TestCondition] | None = None,
    ) -> str:
        """Execute the full intelligent pipeline and return final code."""
        self._starting_url = (target_urls[0].strip() if target_urls else None) or None
        # Update the placeholder orchestrator with the starting URL
        self._placeholder_orchestrator._starting_url = self._starting_url
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
            # Validate that the skeleton uses placeholders, not real CSS selectors
            validator = SkeletonValidator()
            validation_result = validator.validate(skeleton_code)
            if not validation_result.is_valid:
                self._debug(f"skeleton validation violations: {validation_result.violations}")
                raise ValueError(f"Skeleton contains hallucinated CSS selectors. {validation_result.suggestion}")
            # Phase 3: Detect zero-placeholder skeletons and retry once
            placeholders_found = self.parser.parse_placeholders(skeleton_code)
            if not placeholders_found and expected_test_count > 0:
                logger.warning(
                    "Zero placeholders found in skeleton (expected %d tests). "
                    "LLM likely wrote real selectors. Retrying with stricter prompt.",
                    expected_test_count,
                )
                retry_conditions = build_retry_conditions(prepared_conditions, expected_test_count)
                skeleton_code = await self.test_generator.generate_skeleton(
                    user_story,
                    retry_conditions + "\n\nCRITICAL: Every test body line must be a standalone placeholder "
                    "like {{{{CLICK:description}}}}. Do NOT write evidence_tracker.xxx() calls or real selectors.",
                    target_urls=target_urls,
                    expected_count=expected_test_count,
                )
                skeleton_code = self.parser.normalise_placeholder_actions(skeleton_code)
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

        if not reviewed_conditions and expected_test_count and len(journeys) != expected_test_count:
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
        scraped_data: dict[str, list[dict[str, Any]]] = {
            url: elements for url, (elements, error, _final_url) in raw_scraped_data.items()
        }
        scraped_errors: dict[str, str] = {
            url: _error for url, (elements, _error, _final) in raw_scraped_data.items() if _error
        }
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
        if self._starting_url:
            self._debug("phase=journey_discovery start")
            # Always enable discovery logs in the orchestrator debug output
            discovery_data = await self._scrape_journeys_statefully(
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

        scraped_page_records = self._placeholder_orchestrator._build_scraped_page_records(
            pages_to_scrape, scraped_data, scraped_errors, redirects
        )
        generated_page_objects = self._placeholder_orchestrator._build_page_object_artifacts(scraped_page_records)
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
    ) -> dict[str, list[dict[str, Any]]]:
        """Scrape pages by following the generated skeleton journeys step-by-step."""
        if not starting_url:
            return {}

        all_scraped_data: dict[str, list[dict[str, Any]]] = {}
        scraper = JourneyScraper(
            starting_url=starting_url,
            credential_profile=credential_profile,
        )

        for journey in journeys:
            self._debug(f"following discovery journey for: {journey.test_name}")
            steps: list[JourneyStep] = []

            for step in journey.steps:
                for placeholder in step.placeholders:
                    action = placeholder.action.lower()
                    if action == "goto":
                        # For GOTO, we try to resolve the URL from the description
                        url = self._resolver.resolve_url(placeholder.description, {})
                        if url:
                            steps.append(JourneyStep(action="navigate", url=url, description=placeholder.description))
                    elif action in ("click", "fill"):
                        fill_text: str | None = None
                        if action == "fill":
                            # Try to extract fill text from the raw line first
                            fill_text = self._placeholder_orchestrator._extract_fill_text(step.raw_line)
                            # Fallback: if the placeholder description contains a colon,
                            # the fill value may be embedded as FILL:description:value
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

            # Add a final scrape step if not already there
            if not steps or steps[-1].action != "scrape":
                steps.append(JourneyStep(action="scrape", description="final page state"))

            journey_data = await scraper.scrape_journey(steps, credential_profile=credential_profile)
            all_scraped_data.update(journey_data)

        return all_scraped_data

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
        """Generate one skeleton fragment for one reviewed condition."""
        prompt = build_single_condition_skeleton_prompt(
            user_story=user_story,
            known_urls_block=known_urls_block,
            ordered_conditions=ordered_conditions,
            target_condition_ref=condition.id,
            target_condition_text=condition.text,
            target_condition_expected=condition.expected,
            target_condition_intent=condition.intent,
        )
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
        # Validate that the skeleton uses placeholders, not real CSS selectors
        validator = SkeletonValidator()
        validation_result = validator.validate(fragment)
        if not validation_result.is_valid:
            self._debug(f"skeleton validation violations: {validation_result.violations}")
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
        """Return seed URLs only — journey discovery finds all reachable pages.

        URL guessing via common path patterns has been removed because the journey
        scraper navigates the site statefully, following links and form submissions,
        capturing all pages and elements without guessing URL patterns.

        The scraper captures actual URLs it visits (including redirects), so any page
        the site actually has will be discovered through navigation from seed pages.
        """
        # Deduplicate while preserving order — journey discovery handles the rest
        return list(dict.fromkeys(seed_urls))

    # Backwards-compatible delegation methods for code that references these directly on TestOrchestrator.
    async def _resolve_placeholder_for_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
    ) -> tuple[str, str | None]:
        """Backwards-compatible: delegate to PlaceholderOrchestrator._resolve_placeholder_for_page."""
        return await self._placeholder_orchestrator._resolve_placeholder_for_page(
            action=action,
            description=description,
            current_url=current_url,
            scraped_data=scraped_data,
            scraped_errors=scraped_errors,
        )
