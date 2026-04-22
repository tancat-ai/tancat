"""Primary intelligent generation pipeline for the Streamlit app."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from src.code_postprocessor import (
    normalise_generated_code,
    replace_token_in_line,
)
from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney
from src.placeholder_resolver import PlaceholderResolver
from src.prompt_utils import (
    build_retry_conditions,
    count_conditions,
    prepare_conditions_for_generation,
)
from src.scraper import PageScraper
from src.semantic_candidate_ranker import SemanticCandidateRanker
from src.skeleton_parser import SkeletonParser
from src.stateful_scraper import StatefulPageScraper
from src.test_generator import TestGenerator
from src.url_utils import (
    build_common_path_candidates,
    extract_route_concepts,
    extract_seed_domain,
    filter_urls_to_allowed_domain,
    heuristic_url_from_description,
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
        self.resolver = PlaceholderResolver()
        self.scraper = PageScraper()
        self._starting_url: str | None = None
        self.page_object_builder = PageObjectBuilder()
        self.semantic_ranker = SemanticCandidateRanker(getattr(test_generator, "client", None))
        self.last_result: PipelineRunResult | None = None
        self._debug_enabled = os.getenv("PIPELINE_DEBUG", "").strip() == "1"

    def _debug(self, message: str) -> None:
        if self._debug_enabled:
            print(f"[pipeline] {message}", flush=True)

    async def _ensure_scraped(
        self,
        url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
    ) -> None:
        """Scrape the URL once and cache into scraped_data."""
        if not url or url in scraped_data:
            return

        self._debug(f"scrape_on_demand url={url}")
        parsed = urlparse(url)
        is_stateful_target = parsed.path.rstrip("/") in {"/view_cart", "/checkout"}
        if is_stateful_target and self._starting_url:
            stateful_scraper = StatefulPageScraper(self._starting_url)
            elements = await stateful_scraper.scrape_url(url)
            scraped_data[url] = elements
            # Fall back to stateless scrape if the stateful attempt produced nothing.
            if elements:
                return

        elements, error, _final_url = await self.scraper.scrape_url(url)
        scraped_data[url] = elements
        if error and scraped_errors is not None:
            scraped_errors[url] = error

    async def run_pipeline(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        consent_mode: str = "auto-dismiss",
    ) -> str:
        """Execute the full intelligent pipeline and return final code."""
        self._starting_url = (target_urls[0].strip() if target_urls else None) or None
        self._debug("phase=generate_skeleton start")
        expected_test_count = count_conditions(conditions)
        prepared_conditions = prepare_conditions_for_generation(conditions)
        skeleton_code = await self.test_generator.generate_skeleton(
            user_story,
            prepared_conditions,
            target_urls=target_urls,
            expected_count=expected_test_count,
        )
        self._debug("phase=generate_skeleton done")
        skeleton_code = self.parser.normalise_placeholder_actions(skeleton_code)
        skeleton_error = self.parser.validate_skeleton(skeleton_code)
        if skeleton_error:
            raise ValueError(skeleton_error)

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

        if expected_test_count and len(journeys) != expected_test_count:
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
        raw_scraped_data = await self.scraper.scrape_all(pages_to_scrape) if pages_to_scrape else {}
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
            scraped_data = await self._upgrade_stateful_pages(scraped_data)
        self._debug("phase=scrape done")
        scraped_page_records = self._build_scraped_page_records(
            pages_to_scrape, scraped_data, scraped_errors, redirects
        )
        generated_page_objects = self._build_page_object_artifacts(scraped_page_records)
        self._debug("phase=resolve_placeholders start")
        final_code = await self._replace_placeholders_sequentially(
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
            for resolution in self.resolver.resolve_all(placeholders, scraped_data)
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

    async def _upgrade_stateful_pages(
        self,
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, list[dict[str, str]]]:
        """Replace stateless scrapes for cart/checkout pages with session-backed scrapes.

        These pages often render critical elements only when a cart session exists.
        """
        if not self._starting_url:
            return scraped_data

        upgraded = dict(scraped_data)
        stateful_targets: list[str] = []
        for url in scraped_data:
            parsed = urlparse(url)
            if parsed.path.rstrip("/") in {"/view_cart", "/checkout"}:
                stateful_targets.append(url)

        if not stateful_targets:
            return upgraded

        stateful_scraper = StatefulPageScraper(self._starting_url)
        stateful_map = await stateful_scraper.scrape_urls(stateful_targets)
        for url in stateful_targets:
            existing = scraped_data.get(url, [])
            candidate = stateful_map.get(url, [])
            if len(candidate) > len(existing):
                upgraded[url] = candidate

        return upgraded

    @staticmethod
    def _build_scraped_page_records(
        pages_to_scrape: list[str],
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
        redirects: dict[str, str] | None = None,
    ) -> list[ScrapedPage]:
        """Return typed scraped-page records in journey order."""
        scraped_page_records: list[ScrapedPage] = []
        errors = scraped_errors or {}
        redir_map = redirects or {}

        for url in pages_to_scrape:
            elements = scraped_data.get(url, [])
            scraped_page_records.append(
                ScrapedPage(
                    url=redir_map.get(url, url),  # Use redirect URL for the POM context
                    element_count=len(elements),
                    elements=elements,
                    error=errors.get(url),
                )
            )

        return scraped_page_records

    def _build_page_object_artifacts(self, scraped_pages: list[ScrapedPage]) -> list[GeneratedPageObject]:
        """Return page object artifacts generated from scraped pages."""
        generated_objects: list[GeneratedPageObject] = []

        for scraped_page in scraped_pages:
            generated_objects.append(
                self.page_object_builder.build_page_object(
                    scraped_page,
                    file_path=self.page_object_builder.get_default_file_path(scraped_page.url),
                )
            )

        return generated_objects

    async def _replace_placeholders_sequentially(
        self,
        *,
        skeleton_code: str,
        journeys: list[TestJourney],
        page_requirements: list[PageRequirement],
        seed_urls: list[str],
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
    ) -> str:
        """Resolve placeholders step by step while tracking the active page for each test."""
        duplicate_selectors = self._get_duplicate_selectors(scraped_data)
        lines = skeleton_code.splitlines()
        line_resolutions: dict[int, list[tuple[str, str, str, str]]] = {}
        all_placeholder_uses = self.parser.parse_placeholder_uses(skeleton_code)
        fallback_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)
        errors = scraped_errors or {}

        # 1. Resolve placeholders inside test functions (journey-aware)
        for journey in journeys:
            current_url = self._select_initial_page_url(journey, page_requirements, seed_urls, scraped_data)

            for step in journey.steps:
                if current_url is None:
                    current_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)

                for placeholder in step.placeholders:
                    resolved_value, next_url = await self._resolve_placeholder_for_page(
                        action=placeholder.action,
                        description=placeholder.description,
                        current_url=current_url,
                        scraped_data=scraped_data,
                        scraped_errors=errors,
                    )

                    # Record the resolution to apply it later in a single pass per line.
                    self._debug(f"Resolved placeholder '{placeholder.token}' to '{resolved_value}'")
                    line_resolutions.setdefault(placeholder.line_number, []).append(
                        (placeholder.token, placeholder.action, resolved_value, placeholder.description)
                    )

                    if next_url:
                        current_url = next_url

        # 2. Resolve any remaining placeholders (e.g. inside Page Objects) using fallback context
        resolved_tokens = {
            token
            for replacements in line_resolutions.values()
            for token, _action, _resolved_value, _description in replacements
        }

        for use in all_placeholder_uses:
            if use.token in resolved_tokens:
                continue

            # Use the fallback URL for Page Object placeholders since we don't have journey context here
            resolved_value, _ = await self._resolve_placeholder_for_page(
                action=use.action,
                description=use.description,
                current_url=fallback_url,
                scraped_data=scraped_data,
                scraped_errors=errors,
            )

            self._debug(f"Resolved PageObject placeholder '{use.token}' to '{resolved_value}'")
            line_resolutions.setdefault(use.line_number, []).append(
                (use.token, use.action, resolved_value, use.description)
            )

        final_lines: list[str] = []
        for line_number, line in enumerate(lines, start=1):
            updated_line = line
            for token, action, resolved_value, description in line_resolutions.get(line_number, []):
                updated_line = replace_token_in_line(
                    updated_line,
                    action,
                    token,
                    resolved_value,
                    duplicate_selectors,
                    description,
                )
            final_lines.append(updated_line)

        return "\n".join(final_lines)

    @staticmethod
    def _get_duplicate_selectors(scraped_data: dict[str, list[dict[str, str]]]) -> set[str]:
        """Return selectors that appear more than once across scraped pages."""
        selector_counts: dict[str, int] = {}

        for elements in scraped_data.values():
            for element in elements:
                selector = str(element.get("selector", "")).strip()
                if not selector:
                    continue
                selector_counts[selector] = selector_counts.get(selector, 0) + 1

        return {selector for selector, count in selector_counts.items() if count > 1}

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

    async def _resolve_placeholder_for_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
    ) -> tuple[str, str | None]:
        """Resolve one placeholder using the active page first, then fall back to known pages."""
        # Implement journey-driven scraping: if the journey arrives on a page we haven't
        # scraped yet, scrape it now so we can resolve locators/links from it.
        await self._ensure_scraped(current_url, scraped_data, scraped_errors)
        scoped_pages = self._build_scoped_pages(current_url, scraped_data)

        if action in {"GOTO", "URL"}:
            resolved_url = self.resolver.resolve_url(description, scoped_pages or scraped_data)
            if resolved_url:
                return repr(resolved_url), resolved_url
            if current_url:
                heuristic = heuristic_url_from_description(current_url, description)
                if heuristic:
                    # Scrape the heuristic page so subsequent steps can resolve locators from it.
                    await self._ensure_scraped(heuristic, scraped_data, scraped_errors)
                    return repr(heuristic), heuristic

            error_msg = f"Locator for '{description}' not found on scraped pages."
            if current_url and scraped_errors and current_url in scraped_errors:
                error_msg += f" (Note: scraping {current_url} failed with {scraped_errors[current_url]})"
            return f'pytest.skip("{error_msg}")', None

        matched_element = await self._find_best_element_for_current_page(action, description, current_url, scoped_pages)
        if matched_element is None:
            matched_element = await self._find_best_element_for_current_page(
                action, description, current_url, scraped_data
            )

        if matched_element is not None:
            selector = repr(str(matched_element.get("selector", "")).strip())
            next_url = self._infer_next_page_url(action, description, matched_element, scraped_data, current_url)
            if next_url:
                await self._ensure_scraped(next_url, scraped_data, scraped_errors)
            return selector, next_url

        error_msg = f"Locator for '{description}' not found on scraped pages."
        print(f"[DEBUG] Failed to find '{description}'. Available scraped URLs: {list(scraped_data.keys())}")
        return f'pytest.skip("{error_msg}")', None

    @staticmethod
    def _build_scoped_pages(
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, list[dict[str, str]]]:
        """Return a page mapping scoped to the current journey URL when available."""
        if current_url and current_url in scraped_data:
            return {current_url: scraped_data[current_url]}
        return {}

    async def _find_best_element_for_current_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Return the best element match across the supplied page mapping."""
        for elements in pages_data.values():
            ranked_candidates = self.resolver.rank_candidates(action, description, elements)
            if not ranked_candidates:
                continue
            top_score = ranked_candidates[0][0]
            shortlisted = [element for score, element in ranked_candidates if score == top_score][:4]

            matched_element = None
            if len(shortlisted) > 1 and action in {"ASSERT", "CLICK", "FILL"}:
                matched_element = await self.semantic_ranker.choose_best_candidate(
                    action=action,
                    description=description,
                    current_url=current_url,
                    candidates=shortlisted,
                )
            if matched_element is None:
                matched_element = shortlisted[0]
            if matched_element is not None:
                return matched_element
        return None

    def _infer_next_page_url(
        self,
        action: str,
        description: str,
        matched_element: dict[str, str],
        scraped_data: dict[str, list[dict[str, str]]],
        current_url: str | None,
    ) -> str | None:
        """Infer the next active page after a resolved step when navigation is implied."""
        href = str(matched_element.get("href", "")).strip()
        if action == "CLICK" and href:
            if href.startswith(("http://", "https://")):
                return href
            if current_url:
                from urllib.parse import urljoin

                return urljoin(current_url, href)
            return href

        if action == "CLICK" and any(term in description.lower() for term in ("cart", "checkout", "product", "home")):
            return self.resolver.resolve_url(description, scraped_data)

        return None

    def _select_initial_page_url(
        self,
        journey: TestJourney,
        page_requirements: list[PageRequirement],
        seed_urls: list[str],
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> str | None:
        """Choose the starting page for one test journey."""
        for placeholder in journey.placeholders:
            if placeholder.action in {"GOTO", "URL"}:
                resolved_url = self.resolver.resolve_url(
                    placeholder.description,
                    self._page_requirements_to_pages(page_requirements, scraped_data) or scraped_data,
                )
                if resolved_url:
                    return resolved_url

        return self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)

    @staticmethod
    def _page_requirements_to_pages(
        page_requirements: list[PageRequirement],
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, list[dict[str, str]]]:
        """Return scraped data filtered to explicitly required pages."""
        requirement_urls = {page_requirement.url for page_requirement in page_requirements}
        return {url: elements for url, elements in scraped_data.items() if url in requirement_urls}

    @staticmethod
    def _select_fallback_page_url(
        page_requirements: list[PageRequirement],
        seed_urls: list[str],
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> str | None:
        """Return the default page URL to use when no journey-specific page is known."""
        for page_requirement in page_requirements:
            if page_requirement.url in scraped_data:
                return page_requirement.url
        for seed_url in seed_urls:
            if seed_url in scraped_data:
                return seed_url
        return next(iter(scraped_data), None)
