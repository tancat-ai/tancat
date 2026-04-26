"""Placeholder resolution orchestration extracted from TestOrchestrator."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from src.code_postprocessor import replace_token_in_line
from src.journey_scraper import CartSeedingScraper
from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney
from src.placeholder_resolver import PlaceholderResolver
from src.scraper import PageScraper
from src.semantic_candidate_ranker import SemanticCandidateRanker
from src.stateful_scraper import StatefulPageScraper
from src.url_utils import (
    build_common_path_candidates,
    extract_route_concepts,
    extract_seed_domain,
    filter_urls_to_allowed_domain,
    heuristic_url_from_description,
)

logger = logging.getLogger(__name__)


class PlaceholderOrchestrator:
    """Coordinate placeholder resolution, stateful scraping, and page artifact generation."""

    __test__ = False  # type: ignore[assignment]

    def __init__(self, starting_url: str | None = None) -> None:
        self._starting_url = starting_url
        self.resolver = PlaceholderResolver()
        self.scraper = PageScraper()
        self.page_object_builder = PageObjectBuilder()
        self.semantic_ranker = SemanticCandidateRanker(None)

    async def _ensure_scraped(
        self,
        url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
    ) -> None:
        """Scrape the URL once and cache into scraped_data."""
        if not url or url in scraped_data:
            return

        parsed = urlparse(url)  # type: ignore[name-defined]
        is_stateful_target = parsed.path.rstrip("/") in {"/view_cart", "/checkout"}  # type: ignore[name-defined]
        if is_stateful_target and self._starting_url:
            stateful_scraper = StatefulPageScraper(self._starting_url)
            elements = await stateful_scraper.scrape_url(url)
            scraped_data[url] = elements
            if elements:
                return

        elements, error, _final_url = await self.scraper.scrape_url(url)
        scraped_data[url] = elements
        if error and scraped_errors is not None:
            scraped_errors[url] = error

    async def _upgrade_stateful_pages(
        self,
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, list[dict[str, str]]]:
        """Replace stateless scrapes with session-backed scrapes where needed."""
        if not self._starting_url:
            return scraped_data

        upgraded = dict(scraped_data)

        # Phase 1: Cart/checkout pages
        cart_checkout_targets: list[str] = []
        for url in scraped_data:
            parsed = urlparse(url)  # type: ignore[name-defined]
            path = parsed.path.rstrip("/")
            if path in {"/view_cart", "/checkout"}:
                cart_checkout_targets.append(url)

        if cart_checkout_targets:
            logger.info(
                "Journey-aware scrape: %d cart/checkout page(s) targeted ",
                len(cart_checkout_targets),
            )

            absolute_targets: list[str] = []
            for url in cart_checkout_targets:
                if url.startswith(("http://", "https://")):
                    absolute_targets.append(url)
                else:
                    absolute_targets.append(urljoin(self._starting_url, url))  # type: ignore[name-defined]

            cart_scraper = CartSeedingScraper(self._starting_url)
            cart_map = await cart_scraper.scrape_cart_pages(absolute_targets)
            for url in cart_checkout_targets:
                normalized_url = url if url.startswith(("http://", "https://")) else urljoin(self._starting_url, url)
                existing = scraped_data.get(url, [])
                candidate = cart_map.get(normalized_url, [])
                if len(candidate) > len(existing):
                    upgraded[url] = candidate
                    logger.info(
                        "Journey scrape improved '%s': %d → %d elements",
                        url,
                        len(existing),
                        len(candidate),
                    )

        # Phase 2: Known session-dependent URL patterns (non-cart)
        stateful_targets: list[str] = []
        for url in scraped_data:
            parsed = urlparse(url)  # type: ignore[name-defined]
            path = parsed.path.rstrip("/")
            if path in {"/view_cart", "/checkout"}:
                continue
            stateful_targets.append(url)

        # Phase 3: Pages that scraped to 0 elements
        for url, elements in scraped_data.items():
            if len(elements) == 0 and url not in stateful_targets:
                logger.info(
                    "Page '%s' scraped to 0 elements — scheduling stateful re-scrape",
                    url,
                )
                stateful_targets.append(url)

        if stateful_targets:
            logger.info(
                "Stateful re-scrape: %d page(s) targeted",
                len(stateful_targets),
            )

            stateful_scraper = StatefulPageScraper(self._starting_url)
            stateful_map = await stateful_scraper.scrape_urls(stateful_targets)
            for url in stateful_targets:
                existing = scraped_data.get(url, [])
                candidate = stateful_map.get(url, [])
                if len(candidate) > len(existing):
                    upgraded[url] = candidate
                    logger.info(
                        "Stateful scrape improved '%s': %d → %d elements",
                        url,
                        len(existing),
                        len(candidate),
                    )

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
                    url=redir_map.get(url, url),
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
        all_placeholder_uses = self._all_placeholder_uses(skeleton_code)
        fallback_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)
        errors = scraped_errors or {}

        journey_unresolved: dict[str, list[str]] = {}

        # 1. Resolve placeholders inside test functions
        for journey in journeys:
            current_url = self._select_initial_page_url(journey, page_requirements, seed_urls, scraped_data)
            journey_unresolved[journey.test_name] = []

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

                    if "pytest.skip" in resolved_value:
                        journey_unresolved[journey.test_name].append(placeholder.description)
                    else:
                        line_resolutions.setdefault(placeholder.line_number, []).append(
                            (placeholder.token, placeholder.action, resolved_value, placeholder.description)
                        )

                    if next_url:
                        current_url = next_url

        # 2. Resolve remaining placeholders using fallback context
        resolved_tokens = {
            token
            for replacements in line_resolutions.values()
            for token, _action, _resolved_value, _description in replacements
        }

        for use in all_placeholder_uses:
            if use.token in resolved_tokens:
                continue

            journey_name = self._find_journey_for_line(use.line_number, journeys)
            if journey_name:
                resolved_value, _ = await self._resolve_placeholder_for_page(
                    action=use.action,
                    description=use.description,
                    current_url=fallback_url,
                    scraped_data=scraped_data,
                    scraped_errors=errors,
                )
                if "pytest.skip" in resolved_value:
                    journey_unresolved.setdefault(journey_name, []).append(use.description)
                else:
                    line_resolutions.setdefault(use.line_number, []).append(
                        (use.token, use.action, resolved_value, use.description)
                    )
            else:
                resolved_value, _ = await self._resolve_placeholder_for_page(
                    action=use.action,
                    description=use.description,
                    current_url=fallback_url,
                    scraped_data=scraped_data,
                    scraped_errors=errors,
                )
                line_resolutions.setdefault(use.line_number, []).append(
                    (use.token, use.action, resolved_value, use.description)
                )

        # 3. Apply line-level replacements first.
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

        # 5. Insert consolidated pytest.skip() per journey.
        final_lines = self._insert_consolidated_skips(
            final_lines,
            journeys,
            journey_unresolved,
            lines,
        )

        # 6. Remove old per-placeholder skip lines.
        final_lines = self._remove_old_placeholder_skips(final_lines, journeys)

        return "\n".join(final_lines)

    @staticmethod
    def _all_placeholder_uses(code: str) -> list:
        """Parse all placeholder uses from code (delegate to SkeletonParser)."""
        # Import here to avoid circular dependency at module level
        from src.skeleton_parser import SkeletonParser

        parser = SkeletonParser()
        return parser.parse_placeholder_uses(code)

    @staticmethod
    def _remove_old_placeholder_skips(
        lines: list[str],
        journeys: list[TestJourney],
    ) -> list[str]:
        """Filter out old per-placeholder skip lines generated by the skeleton."""
        placeholder_skip_re = re.compile(
            r"""pytest\.skip\(\s*['"]Unresolved placeholder in this step\.\s*\{\{.*?\}\}['"]\s*\)"""
        )
        result_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if placeholder_skip_re.match(stripped):
                continue
            result_lines.append(line)

        return result_lines

    @staticmethod
    def _find_journey_for_line(
        line_number: int,
        journeys: list[TestJourney],
    ) -> str | None:
        """Return the test_name of the journey that contains the given line number."""
        for journey in journeys:
            if journey.start_line <= line_number <= journey.end_line:
                return journey.test_name
        return None

    @staticmethod
    def _insert_consolidated_skips(
        lines: list[str],
        journeys: list[TestJourney],
        journey_unresolved: dict[str, list[str]],
        original_lines: list[str],
    ) -> list[str]:
        """Insert a single consolidated pytest.skip() at the start of each test with unresolved placeholders."""
        skip_messages: dict[str, str] = {}
        for test_name, unresolved_list in journey_unresolved.items():
            if unresolved_list:
                seen: set[str] = set()
                unique_unresolved: list[str] = []
                for desc in unresolved_list:
                    if desc not in seen:
                        seen.add(desc)
                        unique_unresolved.append(desc)
                skip_messages[test_name] = "Skipping: unresolved placeholders for: " + "; ".join(
                    f"'{desc}'" for desc in unique_unresolved
                )

        if not skip_messages:
            return lines

        result_lines: list[str] = []
        inserted_for: set[str] = set()

        for index, line in enumerate(lines):
            result_lines.append(line)
            stripped = line.strip()
            if stripped.startswith("def test_") and "(" in stripped and ":":
                test_name = stripped.split("(")[0].replace("def ", "").strip()
                if test_name in skip_messages and test_name not in inserted_for:
                    next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
                    if next_line.startswith("pytest.skip(") or next_line.startswith("@"):
                        continue

                    indent = "    "
                    skip_line = f"{indent}pytest.skip({skip_messages[test_name]!r})"
                    result_lines.append(skip_line)
                    inserted_for.add(test_name)

        return result_lines

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
        await self._ensure_scraped(current_url, scraped_data, scraped_errors)
        scoped_pages = self._build_scoped_pages(current_url, scraped_data)

        if action in {"GOTO", "URL"}:
            resolved_url = self.resolver.resolve_url(description, scoped_pages or scraped_data)
            if resolved_url:
                return repr(resolved_url), resolved_url
            if current_url:
                heuristic = heuristic_url_from_description(current_url, description)
                if heuristic:
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
