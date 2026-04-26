"""Primary intelligent generation pipeline for the Streamlit app."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from src.code_postprocessor import normalise_generated_code
from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_resolver import PlaceholderResolver
from src.prompt_utils import (
    build_retry_conditions,
    build_single_condition_skeleton_prompt,
    count_conditions,
    prepare_conditions_for_generation,
)
from src.scraper import PageScraper
from src.semantic_candidate_ranker import SemanticCandidateRanker
from src.skeleton_parser import SkeletonParser, SkeletonValidator
from src.spec_analyzer import TestCondition, infer_condition_intent
from src.test_generator import TestGenerator
from src.url_utils import (
    build_common_path_candidates,
    extract_route_concepts,
    extract_seed_domain,
    filter_urls_to_allowed_domain,
)

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

    def __init__(self, test_generator: TestGenerator) -> None:
        self.test_generator = test_generator
        self.parser = SkeletonParser()
        self._starting_url: str | None = None
        self._placeholder_orchestrator = PlaceholderOrchestrator(starting_url=None)
        # Delegate placeholder resolution to PlaceholderOrchestrator
        self.last_result: PipelineRunResult | None = None
        self._debug_enabled = os.getenv("PIPELINE_DEBUG", "").strip() == "1"

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
        pages_to_scrape = self._build_candidate_urls(
            seed_urls=target_urls or [],
            page_requirements=page_requirements,
            journeys=journeys,
            user_story=user_story,
            conditions=conditions,
        )
        self._debug(f"phase=scrape start urls={len(pages_to_scrape)}")
        raw_scraped_data = await self._scraper.scrape_all(pages_to_scrape) if pages_to_scrape else {}
        scraped_data: dict[str, list[dict[str, Any]]] = {
            url: elements for url, (elements, error, _final_url) in raw_scraped_data.items()
        }
        scraped_errors: dict[str, str] = {
            url: _error for url, (elements, _error, _final) in raw_scraped_data.items() if _error
        }

        # Track redirects to maintain correct page context
        redirects: dict[str, str] = {
            url: final_url for url, (_elems, _err, final_url) in raw_scraped_data.items() if url != final_url
        }

        if self._starting_url and scraped_data:
            scraped_data = await self._placeholder_orchestrator._upgrade_stateful_pages(scraped_data)
        self._debug("phase=scrape done")
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
        final_code = normalise_generated_code(
            final_code, consent_mode=consent_mode, target_url=self._starting_url or ""
        )
        unresolved = [
            resolution
            for resolution in self._resolver.resolve_all(placeholders, scraped_data)
            if "pytest.skip" in resolution
        ]
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
        """Combine one-condition skeleton fragments into a single skeleton module."""
        body_blocks: list[str] = []
        page_requirements: list[tuple[str, str]] = []

        for fragment in fragments:
            page_requirements.extend(self.parser.parse_pages_needed(fragment))
            body_blocks.append(self._strip_imports_and_pages_needed(fragment).strip())

        combined_parts = [
            "from playwright.sync_api import Page, expect",
            "import pytest",
            "",
            "\n\n".join(block for block in body_blocks if block),
        ]

        unique_pages = list(dict.fromkeys(page_requirements))
        if unique_pages:
            page_lines = ["# PAGES_NEEDED:"]
            for url, description in unique_pages:
                if description:
                    page_lines.append(f"# - {url} ({description})")
                else:
                    page_lines.append(f"# - {url}")
            combined_parts.extend(["", "\n".join(page_lines)])

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
        """Return a tightly-scoped list of URLs needed for the current journeys."""
        allowed_domains = extract_seed_domain(seed_urls)
        raw_required_urls = [page_requirement.url for page_requirement in page_requirements]
        required_urls = filter_urls_to_allowed_domain(raw_required_urls, allowed_domains)
        placeholder_descriptions = [
            placeholder.description for journey in journeys for placeholder in journey.placeholders
        ]
        concepts = extract_route_concepts([user_story, conditions, *placeholder_descriptions])
        return list(dict.fromkeys(seed_urls + required_urls + build_common_path_candidates(seed_urls, concepts)))

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
