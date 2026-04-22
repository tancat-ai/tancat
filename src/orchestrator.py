"""Primary intelligent generation pipeline for the Streamlit app."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from src.code_postprocessor import (
    _ensure_test_navigation,
    _fix_indentation,
    _inject_consent_helper,
    inject_import,
    normalise_generated_code,
    replace_remaining_placeholders,
    rewrite_page_references_in_class_methods,
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

    @staticmethod
    def _heuristic_url_from_description(current_url: str, description: str) -> str | None:
        """Best-effort URL guess when we haven't scraped links yet."""
        base_url = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}/"
        lowered = description.lower().strip()
        if any(term in lowered for term in ("product", "products", "shop", "store", "catalog")):
            return urljoin(base_url, "products")
        if "cart" in lowered or "basket" in lowered:
            return urljoin(base_url, "view_cart")
        if "checkout" in lowered or "check out" in lowered:
            return urljoin(base_url, "checkout")
        return None

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
                updated_line = self._replace_token_in_line(
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
    def _replace_token_in_line(
        line: str,
        action: str,
        token: str,
        resolved_value: str,
        duplicate_selectors: set[str],
        description: str = "",
    ) -> str:
        """Replace a single placeholder token within a code line."""
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        selector_value = resolved_value.strip("'\"")
        prefer_visible = action == "CLICK"
        # Duplicate selector disambiguation is handled by EvidenceTracker at runtime.

        if "pytest.skip" in resolved_value:
            # If the resolution is a skip, replace the WHOLE line to ensure it executes.
            return f"{indent}{resolved_value}"

        step_label = description if description else token

        # Handle the case where the resolved value (e.g. pytest.skip) is embedded
        # inside a label= argument — the naive str.replace would produce
        # `evidence_tracker.click(..., label='pytest.skip(...)')` which is invalid.
        # Detect this pattern and replace the entire line with the skip statement.
        if "pytest.skip" in resolved_value and "label=" in stripped:
            return f"{indent}{resolved_value}"

        if action == "CLICK":
            selector_literal = resolved_value
            if prefer_visible and ":not(:has-text(''))" not in selector_value:
                selector_literal = repr(f"{selector_value}:visible")
            if stripped == token:
                return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
            if stripped == f"{token}.click()":
                return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
            locator_only_patterns = {
                f"page.locator({token})",
                f"self.page.locator({token})",
                f"page.locator({token}).first",
                f"self.page.locator({token}).first",
            }
            locator_click_patterns = {
                f"page.locator({token}).click()",
                f"self.page.locator({token}).click()",
                f"page.locator({token}).first.click()",
                f"self.page.locator({token}).first.click()",
            }
            if stripped in locator_only_patterns or stripped in locator_click_patterns:
                return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"
            # Final fallback: always produce valid evidence_tracker.click() with proper indentation
            return f"{indent}evidence_tracker.click({selector_literal}, label={repr(step_label)})"

        if action == "ASSERT":
            if stripped == token:
                return f"{indent}evidence_tracker.assert_visible({resolved_value}, label={repr(step_label)})"

            # Use regex to handle expect(page.locator(...)) regardless of content
            expect_match = re.search(r"expect\((?:self\.)?page\.locator\(.*?\)\)\.to_\w+\(.*\)", stripped)
            if expect_match:
                return f"{indent}evidence_tracker.assert_visible({resolved_value}, label={repr(step_label)})"

            locator_only_patterns = {
                f"page.locator({token})",
                f"self.page.locator({token})",
            }
            if stripped in locator_only_patterns:
                return f"{indent}evidence_tracker.assert_visible({resolved_value}, label={repr(step_label)})"
            return line.replace(token, resolved_value)

        if action == "FILL":
            if stripped == token:
                return f'{indent}evidence_tracker.fill({resolved_value}, "", label={repr(step_label)})'
            locator_only_patterns = {
                f"page.locator({token})",
                f"self.page.locator({token})",
            }
            locator_fill_patterns = {
                f'page.locator({token}).fill("")',
                f'self.page.locator({token}).fill("")',
                f"page.locator({token}).fill('')",
                f"self.page.locator({token}).fill('')",
            }
            if stripped in locator_only_patterns or stripped in locator_fill_patterns:
                return f"{indent}evidence_tracker.fill({resolved_value}, '', label={repr(step_label)})"
            # Handle cases where the LLM generates fill(token) without value arg
            fill_no_value = re.match(
                r"(evidence_tracker\.fill\()(" + re.escape(token) + r")(\s*,\s*label=)",
                stripped,
            )
            if fill_no_value:
                return re.sub(
                    r"(evidence_tracker\.fill\()(" + re.escape(token) + r")(\s*,\s*label=)",
                    r"\1\2, '', \3",
                    stripped,
                )
            return line.replace(token, resolved_value)

        if action in {"GOTO", "URL"}:
            if stripped == token:
                return f"{indent}evidence_tracker.navigate({resolved_value})"
            goto_patterns = {
                f"page.goto({token})",
                f"self.page.goto({token})",
            }
            if stripped in goto_patterns:
                return f"{indent}evidence_tracker.navigate({resolved_value})"
            return line.replace(token, resolved_value)

        return line.replace(token, resolved_value)

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
                heuristic = self._heuristic_url_from_description(current_url, description)
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

    @staticmethod
    def _normalise_generated_code(code: str, consent_mode: str = "auto-dismiss", target_url: str = "") -> str:
        """Apply small deterministic fixes to common skeleton-generation mistakes."""
        # Hallucination fix: Remove backticks, markdown, or extra spaces from URLs inside strings.
        # This handles: " `http...` ", ' `http...` ', "http... ", etc.
        fixed_code = re.sub(r'([\'"])\s*`?(https?://[^`\s\'"]+)`?\s*([\'"])', r"\1\2\3", code)

        # CRITICAL: Replace hallucinated example.com / example-store.com / other
        # placeholder URLs with the real target URL.
        # The LLM often hallucinates example.com or example-store.com instead of
        # using the actual site URL.
        # The regex must handle cases where dismiss_consent_overlays(page) is
        # injected between the navigate call and the closing paren.
        if target_url:
            # Pattern 1: evidence_tracker.navigate("url")  — simple case
            fixed_code = re.sub(
                r'(evidence_tracker\.navigate\()([\'"])https?://(?:\w+\.)?(?:example(?:-\w*)?\.com|example\.org)[^"\']*([\'"]\))',
                r"\1\2" + target_url + r"\3",
                fixed_code,
            )
            # Pattern 2: evidence_tracker.navigate("url")  followed by dismiss_consent_overlays(page)
            # on the next line — replace the URL in the navigate line only
            fixed_code = re.sub(
                r'(evidence_tracker\.navigate\()([\'"])https?://(?:\w+\.)?(?:example(?:-\w*)?\.com|example\.org)[^"\']*([\'"])',
                r"\1\2" + target_url + r"\3",
                fixed_code,
            )

        # Additional aggressive URL cleanup for nested backticks or spaces
        # Only match navigate/goto with a single string argument (URL), not fill() etc.
        fixed_code = re.sub(
            r'(navigate|goto)\(\s*([\'"])\s*`?(https?://[^`\s\'"]+)`?\s*([\'"])\s*\)',
            r"\1(\2\3\4)",
            fixed_code,
        )

        # Hallucination fix: Clean up malformed decorators if the LLM added spaces
        fixed_code = re.sub(r"@\s*pytest\s*\.\s*mark\s*\.\s*evidence", "@pytest.mark.evidence", fixed_code)

        # Always inject pytest at module level when the code uses any pytest constructs.
        # _inject_import handles deduplication by removing any existing copies first.
        if "pytest.skip(" in fixed_code or "pytest.mark." in fixed_code:
            fixed_code = inject_import(fixed_code, "import pytest")

        # The tool ships an `evidence_tracker` fixture for generated tests.
        # Some LLMs hallucinate a non-existent `evidence_launcher` fixture name.
        fixed_code = re.sub(r"\bevidence_launcher\b", "evidence_tracker", fixed_code)

        # Ensure evidence_tracker is used for common methods even if LLM forgot
        fixed_code = re.sub(r"page\.goto\(", "evidence_tracker.navigate(", fixed_code)
        fixed_code = re.sub(r"self\.page\.goto\(", "evidence_tracker.navigate(", fixed_code)

        # Some models hallucinate a slash between `pytest.mark` and the marker name.
        # Example: `@pytest.mark/evidence(...)` which is invalid Python.
        fixed_code = re.sub(r"(?m)^\s*@pytest\.mark\s*/\s*([A-Za-z_][A-Za-z0-9_]*)", r"@pytest.mark.\1", fixed_code)

        # Some models hallucinate special constructor names (e.g. `__larry`) which
        # makes instantiation fail immediately at runtime.
        fixed_code = re.sub(
            r"(?m)^(\s*)def\s+__larry\s*\(\s*self\s*,\s*page\s*:\s*Page\s*\)\s*:\s*$",
            r"\1def __init__(self, page: Page) -> None:",
            fixed_code,
        )

        # Some models emit invalid keyword arguments when instantiating page objects.
        fixed_code = re.sub(
            r"(\b[A-Za-z_][A-Za-z0-9_]*Page)\(\s*project\s*=\s*page\s*\)",
            r"\1(page)",
            fixed_code,
        )

        # Guardrail: some models accidentally emit invalid decorator assignment lines like
        # `@pytest.markelse = None`, which breaks syntax validation. Strip any decorator
        # lines that look like attribute assignments on `pytest.mark*`.
        fixed_code = re.sub(r"(?m)^\s*@pytest\.mark\w*\s*=\s*.*\n?", "", fixed_code)

        fixed_code = re.sub(r"(def __init__\(self,\s*page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
        fixed_code = re.sub(r"(def test_[A-Za-z0-9_]*\(page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
        fixed_code = re.sub(r"(?<=:\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)
        fixed_code = re.sub(r"(?<=->\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)

        if consent_mode == "auto-dismiss":
            fixed_code = _inject_consent_helper(fixed_code)

        fixed_code = rewrite_page_references_in_class_methods(fixed_code)

        # Hallucination guard: record_condition(...) -> @pytest.mark.evidence
        # This is a bit tricky to fix automatically if the LLM put it at the end of the function.
        # But we can at least strip it to avoid runtime errors.
        fixed_code = re.sub(r"(?m)^\s*evidence_tracker\.record_condition\(.*?\)\s*$", "", fixed_code)

        # Ensure every test starts with a navigation if none present
        fixed_code = _ensure_test_navigation(fixed_code)

        # Hallucination fix: Flatten inner functions like `def inner():` and `def run_test():`
        # DISABLED temporarily — causes indentation issues with complex LLM output
        # fixed_code = flatten_inner_functions(fixed_code)

        # Safety net: replace any remaining unresolved {{ACTION:...}} placeholders with
        # pytest.skip() so they never cause a SyntaxError.  This catches placeholders
        # whose descriptions contain Python variable syntax (e.g. {item_name}) that
        # break the resolver's regex and therefore were never substituted.
        fixed_code = replace_remaining_placeholders(fixed_code)

        # Fix inconsistent indentation inside test functions and class methods
        fixed_code = _fix_indentation(fixed_code)

        return fixed_code

    @staticmethod
    def _replace_remaining_placeholders(code: str) -> str:
        """Replace any unresolved {{ACTION:description}} placeholders with pytest.skip().

        The resolver's regex uses ``[^}]+`` for the description, which means
        descriptions containing Python variable syntax such as ``{item_name}``
        break the match and the placeholder is never substituted.  Those raw
        strings are invalid Python and will cause a SyntaxError.  This method
        is the last-resort safety net applied after all other post-processing.

        When the placeholder is embedded inside a function call (e.g.
        ``evidence_tracker.fill({{FILL:x}}, label="y")``), the entire call
        is replaced with a skip statement to avoid producing invalid Python.

        Placeholders that appear inside quoted strings (e.g. inside a
        ``label='{{CLICK:basket}}'`` argument) are left untouched because they
        are metadata, not executable code.
        """
        # This regex handles nested braces like {item_name} that break the
        # resolver's simpler [^}]+ pattern.  It matches the shortest string
        # between {{ACTION: and the closing }}.
        placeholder_pattern = re.compile(r"\{\{[A-Z_]+:(.+?)\}\}", re.DOTALL)

        def _is_inside_quotes(text_before: str) -> bool:
            """Return True if the position in text_before is inside single or double quotes."""
            in_single = False
            in_double = False
            for ch in text_before:
                if ch == "'" and not in_double:
                    in_single = not in_single
                elif ch == '"' and not in_single:
                    in_double = not in_double
            return in_single or in_double

        output_lines: list[str] = []
        for line in code.splitlines():
            if "{{" not in line:
                output_lines.append(line)
                continue
            # Preserve indentation
            indent = line[: len(line) - len(line.lstrip())]
            the_content = line.strip()

            # Find all unresolved placeholders
            matches = list(placeholder_pattern.finditer(the_content))
            if not matches:
                output_lines.append(line)
                continue

            # Skip replacement if ALL matches are inside quotes (metadata only)
            all_inside_quotes = all(_is_inside_quotes(the_content[: match.start()]) for match in matches)
            if all_inside_quotes:
                output_lines.append(line)
                continue

            # Check if any placeholder is inside a function call (not inside quotes)
            has_function_call = any(
                not _is_inside_quotes(the_content[: match.start()])
                and re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", the_content[: match.start()])
                and ")" in the_content[match.end() :]
                for match in matches
            )

            if has_function_call:
                # Replace the entire line with a skip statement
                output_lines.append(
                    f'{indent}pytest.skip("Unresolved placeholder in this step. " '
                    f"+ \", \".join([m.group(0) for m in placeholder_pattern.finditer('{the_content}'])[:3]))"
                )
            else:
                # Placeholder is standalone — replace it directly
                def _handle_match(m: re.Match) -> str:
                    text = m.group(0)
                    return f'pytest.skip("Unresolved placeholder: {text}")'

                new_content = placeholder_pattern.sub(_handle_match, the_content)
                output_lines.append(f"{indent}{new_content}")
        return "\n".join(output_lines)

    @staticmethod
    def _fix_indentation(code: str) -> str:
        """Fix inconsistent indentation inside test functions and class methods.

        The LLM sometimes emits lines without indentation inside function bodies.
        This method detects such lines and applies 4-space indentation.
        """
        lines = code.splitlines()
        updated_lines: list[str] = []
        inside_function = False
        func_indent = 0

        for line in lines:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # Detect function definition
            if re.match(r"^\s*def\s+", line):
                inside_function = True
                func_indent = indent + 4
                updated_lines.append(line)
                continue

            # Detect class definition
            if re.match(r"^\s*class\s+", line):
                inside_function = False
                updated_lines.append(line)
                continue

            # If we're inside a function and the line has less indentation
            # than expected but has content, fix it
            if inside_function and stripped and indent < func_indent:
                # Only fix if the line looks like it should be indented
                # (starts with a known keyword or is a function call)
                if not re.match(r"^\s*(def |class |@|import |from |#|$)", line):
                    updated_lines.append(" " * func_indent + stripped)
                    continue

            updated_lines.append(line)

        return "\n".join(updated_lines)

    @staticmethod
    def _flatten_inner_functions(code: str) -> str:
        """Remove nested 'def inner():' style wrappers and move their decorators up.

        Handles the common case where the LLM wraps test logic inside a short
        inner function (e.g. ``def inner():`` or ``def run_test():``) followed
        by a call to that function.  The inner function's body is unindented
        and placed directly inside the outer test function.
        """
        lines = code.splitlines()
        updated_lines: list[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Detect a test function that is immediately followed by a nested
            # function definition (not another test, class, or top-level block).
            if stripped.startswith("def test_") and "(" in stripped:
                updated_lines.append(line)
                i += 1

                # Look for a nested function (more indented than the test def)
                while i < len(lines):
                    next_line = lines[i]
                    next_stripped = next_line.strip()
                    next_indent = len(next_line) - len(next_line.lstrip())

                    # If we hit another test, class, or top-level block, stop
                    if (
                        next_stripped.startswith("def test_")
                        or next_stripped.startswith("class ")
                        or next_stripped.startswith("import ")
                        or next_stripped.startswith("from ")
                        or (next_indent <= 0 and next_stripped)
                    ):
                        break

                    # Detect nested function definition
                    if next_stripped.startswith("def ") and next_indent > 0:
                        # Collect decorators above the nested function
                        decorator_lines: list[str] = []
                        j = i - 1
                        while j >= 0 and lines[j].strip().startswith("@pytest.mark.evidence"):
                            decorator_lines.insert(0, lines[j].strip())
                            j -= 1

                        # Get the nested function name
                        func_name = next_stripped[4:].split("(", 1)[0].strip()

                        # Add decorators to the outer test
                        base_indent = " " * (len(line) - len(line.lstrip()))
                        for d_line in decorator_lines:
                            updated_lines.append(f"{base_indent}{d_line}")

                        # Skip the nested function def line
                        i += 1

                        # Process the body of the nested function
                        nested_indent = next_indent
                        while i < len(lines):
                            body_line = lines[i]
                            body_stripped = body_line.strip()
                            body_indent = len(body_line) - len(body_line.lstrip())

                            # End of nested function (back to nested_indent or less)
                            if body_stripped and body_indent <= nested_indent:
                                break

                            # Skip the call to the inner function
                            if body_indent == nested_indent and body_stripped.startswith(func_name + "("):
                                i += 1
                                continue

                            # Unindent the body to the outer test level
                            if body_stripped:
                                updated_lines.append(base_indent + body_line.lstrip())
                            else:
                                updated_lines.append("")
                            i += 1
                        continue

                    # Not a nested function — just a regular line in the test body
                    updated_lines.append(next_line)
                    i += 1
                continue

            updated_lines.append(line)
            i += 1

        return "\n".join(updated_lines)

    @staticmethod
    def _inject_import(code: str, import_line: str) -> str:
        """Insert an import at the very top of the generated file.

        Always ensures the import is at module level (column 0), even if a
        malformed copy already exists somewhere deeper in the file.
        """
        lines = code.splitlines()

        # Remove any existing copy of this import line (with or without whitespace)
        stripped_target = import_line.strip()
        lines = [ln for ln in lines if ln.strip() != stripped_target]

        insert_at = 0
        if lines and lines[0].startswith("from __future__ import"):
            insert_at = 1
            while insert_at < len(lines) and not lines[insert_at].strip():
                insert_at += 1
        lines.insert(insert_at, import_line)
        return "\n".join(lines)

    @staticmethod
    def _rewrite_page_references_in_class_methods(code: str) -> str:
        """Replace bare `page.` references with `self.page.` inside instance methods."""
        rewritten_lines: list[str] = []
        inside_class = False
        is_test_class = False
        class_indent = 0
        inside_instance_method = False
        method_indent = 0

        for line in code.splitlines():
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            if stripped.startswith("class "):
                inside_class = True
                class_indent = indent
                inside_instance_method = False
                class_name = stripped[6:].split(":", 1)[0].split("(", 1)[0].strip()
                is_test_class = class_name.startswith("Test") or class_name.endswith("Test")
            elif inside_class and stripped and indent <= class_indent and not stripped.startswith("#"):
                inside_class = False
                is_test_class = False
                inside_instance_method = False

            if inside_class and not is_test_class and stripped.startswith("def "):
                signature = stripped.split("(", maxsplit=1)[1] if "(" in stripped else ""
                inside_instance_method = signature.startswith("self,") or signature.startswith("self)")
                method_indent = indent
            elif inside_instance_method and stripped and indent <= method_indent and not stripped.startswith("#"):
                inside_instance_method = False

            if inside_instance_method and "page." in line and "self.page." not in line:
                line = re.sub(r"\bpage\.", "self.page.", line)

            if inside_instance_method:
                # Check if evidence_tracker is a method parameter — if so, DON'T convert
                # to self.evidence_tracker (it's passed as an argument, not an instance attr)
                method_sig = ""
                if "(" in stripped and ")" in stripped:
                    method_sig = stripped.split("(", 1)[1].split(")")[0]
                has_evidence_tracker_param = "evidence_tracker" in method_sig

                if not has_evidence_tracker_param:
                    line = re.sub(r"\bevidence_tracker\.", "self.evidence_tracker.", line)

                line = re.sub(
                    r"\bdismiss_consent_overlays\(\s*page\s*\)",
                    "dismiss_consent_overlays(self.page)",
                    line,
                )
                line = line.replace("(page)", "(self.page)")
                line = line.replace("Page(", "self.page(")

            rewritten_lines.append(line)

        return "\n".join(rewritten_lines)

    @staticmethod
    def _inject_consent_helper(code: str) -> str:
        """Inject a lightweight consent-dismiss helper and call it after navigation."""
        helper_name = "dismiss_consent_overlays"
        if helper_name not in code:
            helper_block = """

def dismiss_consent_overlays(page: Page) -> None:
    candidate_selectors = [
        "button:has-text('Consent')",
        "button:has-text('Accept')",
        "button:has-text('Continue')",
        "button:has-text('OK')",
        "button:has-text('Got it')",
        "button:has-text('I Agree')",
        "button:has-text('Agree')",
        "button[aria-label='Close']",
        "button[aria-label='close']",
    ]
    for selector in candidate_selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                locator.click(timeout=500)
                page.wait_for_timeout(200)
                break
        except Exception:
            continue
"""
            insert_after = "from playwright.sync_api import Page, expect"
            if insert_after in code:
                code = code.replace(insert_after, insert_after + helper_block, 1)
            else:
                code = helper_block + "\n" + code

        lines = code.splitlines()
        updated_lines: list[str] = []
        for line in lines:
            updated_lines.append(line)
            stripped = line.strip()
            indent = line[: len(line) - len(line.lstrip())]

            # Skip injection if the line is already a call to the helper
            if f"{helper_name}(" in stripped:
                continue

            if stripped.startswith("page.goto(") or stripped.startswith("evidence_tracker.navigate("):
                # Check if next line is already a call to avoid duplicates
                updated_lines.append(f"{indent}{helper_name}(page)")

        return "\n".join(updated_lines)

    @staticmethod
    def _ensure_test_navigation(code: str) -> str:
        """Inject an initial navigation to the first known URL if a test lacks navigation."""
        pages_block = re.search(r"# PAGES_NEEDED:\n((?:# https?://.*\n?)+)", code)
        if not pages_block:
            return code

        first_url = re.search(r"https?://[^\s\n]+", pages_block.group(1))
        if not first_url:
            return code

        url = first_url.group(0)
        lines = code.splitlines()
        updated_lines: list[str] = []

        inside_test = False
        test_has_nav = False

        for line in lines:
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]

            if stripped.startswith("def test_"):
                inside_test = True
                test_has_nav = False
                updated_lines.append(line)
                continue

            if inside_test:
                if stripped.startswith("def ") or (line.strip() == "" and indent == ""):
                    # End of test function or start of next
                    if not test_has_nav:
                        # Insert nav at the start of the previous test block
                        # This is complex to do in a single pass, so we'll use a simpler approach
                        pass
                    inside_test = False

                if "navigate(" in stripped or "goto(" in stripped:
                    test_has_nav = True

            updated_lines.append(line)

        # Simpler approach: find test functions and inject nav if missing
        final_code = "\n".join(updated_lines)

        def _inject_nav(match: re.Match[str]) -> str:
            body = match.group(2)
            if "navigate(" in body or "goto(" in body:
                return match.group(0)

            indent = "    "
            nav_line = f'\n{indent}evidence_tracker.navigate("{url}")\n{indent}dismiss_consent_overlays(page)'
            return f"{match.group(1)}{nav_line}{body}"

        # Match test function signature and capture its body
        return re.sub(
            r"(def test_\w+\(page: Page, evidence_tracker\) -> None:)(.*?(?=\n\n|\ndef |\Z))",
            _inject_nav,
            final_code,
            flags=re.S,
        )
