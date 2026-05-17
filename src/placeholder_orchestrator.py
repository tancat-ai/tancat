"""Placeholder resolution orchestration extracted from TestOrchestrator."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from src.code_postprocessor import replace_token_in_line
from src.journey_scraper import CartSeedingScraper, CredentialProfile
from src.locator_builder import build_robust_locator
from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney
from src.placeholder_resolver import PlaceholderResolver
from src.scraper import PageScraper
from src.semantic_candidate_ranker import SemanticCandidateRanker
from src.semantic_matcher import SemanticMatcher
from src.stateful_scraper import StatefulPageScraper
from src.url_inference import infer_next_page_url
from src.url_resolver import UrlResolver
from src.url_utils import (
    build_common_path_candidates,
    extract_route_concepts,
    heuristic_url_from_description,
)

logger = logging.getLogger(__name__)


class PlaceholderOrchestrator:
    """Coordinate placeholder resolution, stateful scraping, and page artifact generation."""

    __test__ = False  # type: ignore[assignment]

    def __init__(
        self,
        starting_url: str | None = None,
        credential_profile: CredentialProfile | None = None,
    ) -> None:
        self._starting_url = starting_url
        self._credential_profile = credential_profile
        self.resolver = PlaceholderResolver()
        self.scraper = PageScraper()
        self.page_object_builder = PageObjectBuilder()
        self.semantic_ranker = SemanticCandidateRanker(None)
        self.url_resolver = UrlResolver()

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
            stateful_scraper = StatefulPageScraper(self._starting_url, credential_profile=self._credential_profile)
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

            stateful_scraper = StatefulPageScraper(self._starting_url, credential_profile=self._credential_profile)
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
        line_resolutions: dict[int, list[tuple[str, str, str, str, str]]] = {}
        all_placeholder_uses = self._all_placeholder_uses(skeleton_code)
        fallback_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)
        errors = scraped_errors or {}

        journey_unresolved: dict[str, list[str]] = {}

        # 1. Resolve placeholders inside test functions
        for journey in journeys:
            current_url = self._select_initial_page_url(
                journey,
                page_requirements,
                seed_urls,
                scraped_data,
                lines,
            )
            journey_unresolved[journey.test_name] = []

            for step in journey.steps:
                if current_url is None:
                    current_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)

                for placeholder in step.placeholders:
                    # Extract value from FILL:desc:value format
                    fill_value = ""
                    action = placeholder.action
                    description = placeholder.description
                    if action == "FILL" and ":" in description:
                        parts = description.split(":", 1)
                        description = parts[0]
                        fill_value = parts[1]

                    resolved_value, next_url = await self._resolve_placeholder_for_page(
                        action=action,
                        description=description,
                        current_url=current_url,
                        scraped_data=scraped_data,
                        scraped_errors=errors,
                    )

                    if "pytest.skip" in resolved_value:
                        journey_unresolved[journey.test_name].append(description)
                    else:
                        line_resolutions.setdefault(placeholder.line_number, []).append(
                            (placeholder.token, action, resolved_value, description, fill_value)
                        )

                    if next_url:
                        current_url = next_url

        # 2. Resolve remaining placeholders using fallback context
        resolved_tokens = {
            token
            for replacements in line_resolutions.values()
            for token, _action, _resolved_value, _description, _ in replacements
        }

        for use in all_placeholder_uses:
            if use.token in resolved_tokens:
                continue

            # Extract value from FILL:desc:value format
            fill_value = ""
            action = use.action
            description = use.description

            if action == "FILL" and ":" in description:
                # Split only on the first colon to handle descriptions that might have colons
                parts = description.split(":", 1)
                description = parts[0]
                fill_value = parts[1]

            journey_name = self._find_journey_for_line(use.line_number, journeys)
            if journey_name:
                resolved_value, _ = await self._resolve_placeholder_for_page(
                    action=action,
                    description=description,
                    current_url=fallback_url,
                    scraped_data=scraped_data,
                    scraped_errors=errors,
                )
                if "pytest.skip" in resolved_value:
                    journey_unresolved.setdefault(journey_name, []).append(description)
                else:
                    if journey_name in journey_unresolved:
                        journey_unresolved[journey_name] = [
                            unresolved for unresolved in journey_unresolved[journey_name] if unresolved != description
                        ]
                    line_resolutions.setdefault(use.line_number, []).append(
                        (use.token, action, resolved_value, description, fill_value)
                    )
            else:
                resolved_value, _ = await self._resolve_placeholder_for_page(
                    action=action,
                    description=description,
                    current_url=fallback_url,
                    scraped_data=scraped_data,
                    scraped_errors=errors,
                )
                line_resolutions.setdefault(use.line_number, []).append(
                    (use.token, action, resolved_value, description, fill_value)
                )

        # 3. Apply line-level replacements first.
        final_lines: list[str] = []
        for line_number, line in enumerate(lines, start=1):
            updated_line = line
            for token, action, resolved_value, description, _fill_value in line_resolutions.get(line_number, []):
                updated_line = replace_token_in_line(
                    updated_line,
                    action,
                    token,
                    resolved_value,
                    duplicate_selectors,
                    description,
                    fill_value=_fill_value,
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
    def _extract_fill_text(line: str) -> str | None:
        """Extract the second argument from an evidence_tracker.fill() call."""
        # Match evidence_tracker.fill(placeholder, "text") or similar
        match = re.search(r"fill\(.+?,\s*['\"](.+?)['\"]\)", line)
        if match:
            return match.group(1)
        return None

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
        """Return a tightly-scoped list of URLs needed for the current journeys.

        Note: page_requirements now contain keywords (not URLs). URL resolution
        happens via UrlResolver (Phase 3). For now, rely on seed_urls + heuristic
        path candidates built from placeholder descriptions and user story context.
        """
        # Collect keywords for logging (actual URL resolution happens in UrlResolver)
        keywords = [page_requirement.keyword for page_requirement in page_requirements]
        placeholder_descriptions = [
            placeholder.description for journey in journeys for placeholder in journey.placeholders
        ]
        concepts = extract_route_concepts([user_story, conditions, *placeholder_descriptions, *keywords])
        return list(dict.fromkeys(seed_urls + build_common_path_candidates(seed_urls, concepts)))

    def _verify_page_context(
        self,
        description: str,
        matched_element: dict[str, str],
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> bool:
        """Verify the resolved locator exists on the current page (B3: page-context validation).

        If the locator was scraped from a different page, log a warning.
        Returns True if the element is valid for the current page context.
        """
        if current_url is None:
            return True

        # Check if the element's selector exists on the current page
        current_elements = scraped_data.get(current_url, [])
        element_selector = str(matched_element.get("selector", "")).strip()
        if not element_selector:
            return True

        for elem in current_elements:
            if str(elem.get("selector", "")).strip() == element_selector:
                return True

        # Cross-page mismatch detected
        # Find which page the element was actually scraped from
        source_url: str | None = None
        for url, elements in scraped_data.items():
            for elem in elements:
                if str(elem.get("selector", "")).strip() == element_selector:
                    source_url = url
                    break
            if source_url:
                break

        logger.warning(
            "Cross-page mismatch: placeholder '%s' resolved to '%s' which exists on '%s' "
            "but current page is '%s'. Element may not be visible at runtime.",
            description,
            element_selector,
            source_url or "unknown",
            current_url,
        )
        return False

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
            # Step 1: Try UrlResolver (keyword → URL mapping from scraped URLs)
            url_from_resolver = self.url_resolver.resolve(description)
            if url_from_resolver:
                logger.debug("UrlResolver matched '%s' -> %s", description, url_from_resolver)
                return repr(url_from_resolver), url_from_resolver

            # Step 2: Try PlaceholderResolver (scraped element matching)
            resolved_url = self.resolver.resolve_url(description, scoped_pages or scraped_data)
            if resolved_url:
                return repr(resolved_url), resolved_url

            # Step 3: Heuristic fallback
            if current_url:
                heuristic = heuristic_url_from_description(current_url, description)
                if heuristic:
                    await self._ensure_scraped(heuristic, scraped_data, scraped_errors)
                    return repr(heuristic), heuristic

            # Step 4: Try seed URL as last resort
            seed_url = self.url_resolver.get_seed_url()
            if seed_url:
                logger.debug("Falling back to seed URL for '%s': %s", description, seed_url)
                return repr(seed_url), seed_url

            error_msg = f"Locator for '{description}' not found on scraped pages."
            if current_url and scraped_errors and current_url in scraped_errors:
                error_msg += f" (Note: scraping {current_url} failed with {scraped_errors[current_url]})"
            return f'pytest.skip("{error_msg}")', None

        # When scoped_pages is empty (current_url not in scraped_data), fall back to
        # ALL scraped pages. The "no fallback" rule prevents using wrong-page elements
        # when the current page HAS data. But when scoped_pages is empty due to URL
        # normalization differences (trailing slash, query params, etc.), we must
        # search all pages to find the element.
        pages_to_search = scoped_pages if scoped_pages else scraped_data
        matched_element = await self._find_best_element_for_current_page(
            action, description, current_url, pages_to_search
        )
        # Do NOT fall back to elements from other pages. Each action must resolve
        # against the CURRENT page context — falling back to elements scraped from a
        # different page produces wrong locators that fail at runtime:
        # - ASSERT: element was already navigated away from (hidden)
        # - CLICK: element exists on home page but action happens on category page
        # - FILL: form field from wrong page context
        # The scraper must capture elements on each page; if resolution fails, the
        # test should skip with a clear message rather than use a wrong locator.

        if matched_element is not None:
            # B3: Verify page context — log warning for cross-page mismatches
            self._verify_page_context(description, matched_element, current_url, scraped_data)

            # _find_best_element_for_current_page() has already selected the element
            # via the priority chain (text → structural → scoring/LLM).
            robust_selector = build_robust_locator(matched_element)
            if not robust_selector:
                robust_selector = str(matched_element.get("selector", "")).strip()
            selector = repr(robust_selector)
            next_url = infer_next_page_url(action, description, matched_element, scraped_data, current_url)
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

    def _validate_text_match(
        self,
        element: dict[str, str] | None,
        description: str,
    ) -> dict[str, str] | None:
        """Validate that the element's visible text plausibly matches the description.

        Returns the element if validation passes, None otherwise.
        """
        if element is None:
            return None
        element_text = str(element.get("text", "")).strip()
        if not element_text:
            # Elements with no text (e.g., icons, images) bypass text validation
            return element
        if self.resolver.text_matches_description(element_text, description):
            return element
        logger.debug(
            "Text validation failed: element '%s' does not match description '%s'",
            element_text,
            description,
        )
        return None

    @staticmethod
    def _log_resolve_pass(
        pass_number: int,
        pass_name: str,
        description: str,
        element: dict[str, str] | None,
    ) -> None:
        if element is None:
            return
        logger.info(
            "[RESOLVE] '%s' | pass=%d (%s) | selector=%s",
            description,
            pass_number,
            pass_name,
            element.get("selector", ""),
        )

    def _normalise_element_text(self, element: dict[str, str]) -> str:
        """Extract and normalise element text for Pass 1 matching.

        Priority: accessible_name → aria_label → text.
        Strips non-ASCII characters (icon fonts), lowercases,
        and strips whitespace.
        """
        raw = (element.get("accessible_name") or element.get("aria_label") or element.get("text", "")).strip()
        return re.sub(r"[^\x00-\x7f]", "", raw).strip().lower()

    def _pass1_text_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 1 — fast text match before scoring.

        Returns the first element whose normalised text is
        contained in the normalised description.
        Only fires for CLICK and FILL — ASSERT tokens for
        page state will not match element text and should
        fall through to the scoring path.

        Minimum element text length of 3 characters prevents
        single-character matches ('a', 'x') producing false wins.
        """
        if action not in {"CLICK", "FILL"}:
            return None

        norm_description = description.lower()

        for elements in pages_data.values():
            for element in elements:
                norm_text = self._normalise_element_text(element)
                if len(norm_text) >= 3 and norm_text in norm_description:
                    return element

        return None

    def _pass1_assert_text_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 1 (ASSERT) — match text-bearing elements whose label appears in the description."""
        if action != "ASSERT":
            return None

        norm_description = description.lower()
        text_bearing_roles = {
            "heading",
            "paragraph",
            "text",
            "status",
            "alert",
            "region",
            "article",
            "listitem",
            "cell",
            "columnheader",
            "rowheader",
        }
        text_bearing_tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "label", "li", "td", "th"}

        for elements in pages_data.values():
            for element in elements:
                role = str(element.get("role", "")).strip().lower()
                tag = str(element.get("tag", "")).strip().lower()
                if role not in text_bearing_roles and tag not in text_bearing_tags:
                    continue
                norm_text = self._normalise_element_text(element)
                if len(norm_text) >= 3 and norm_text in norm_description:
                    return element

        return None

    def _pass2_structural_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 2 — match stable attributes (id, data-test, aria) to description keywords."""
        if action not in {"CLICK", "FILL", "ASSERT"}:
            return None

        desc_words = SemanticMatcher.get_words(description, expand_aliases=False)
        if not desc_words:
            return None

        structural_fields = ("id", "data_test", "aria_label", "accessible_name", "name")

        for elements in pages_data.values():
            for element in elements:
                for field in structural_fields:
                    raw = str(element.get(field, "")).strip()
                    if len(raw) < 2:
                        continue
                    field_words = SemanticMatcher.get_words(raw, expand_aliases=False)
                    overlap = desc_words & field_words
                    if len(overlap) >= 2:
                        return element
                    normalized_field = raw.lower().replace("_", " ").replace("-", " ")
                    if normalized_field in description.lower():
                        return element

        return None

    async def _find_best_element_for_current_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Return the best element match across the supplied page mapping.

        IMPORTANT: Collects candidates from ALL pages first, then selects the global
        best match. This prevents returning a low-quality match from an early page
        when a much better match exists on a later page (e.g., finding a cart page
        element for "username input" instead of the login page element).
        """
        # Pass 1 — fast text match (CLICK/FILL)
        pass1_result = self._pass1_text_match(action, description, pages_data)
        if pass1_result is not None:
            self._log_resolve_pass(1, "text match", description, pass1_result)
            return pass1_result

        # Pass 1 — ASSERT text-bearing elements
        pass1_assert = self._pass1_assert_text_match(action, description, pages_data)
        if pass1_assert is not None:
            self._log_resolve_pass(1, "assert text match", description, pass1_assert)
            return pass1_assert

        # Pass 2 — structural attribute match
        pass2_result = self._pass2_structural_match(action, description, pages_data)
        if pass2_result is not None:
            self._log_resolve_pass(2, "structural match", description, pass2_result)
            return pass2_result

        # Pass 3 — scoring shortlist + semantic ranker (legacy path)
        logger.debug("[RESOLVE] '%s' | pass=3 (scoring)", description)

        # Collect ALL ranked candidates across ALL pages
        all_ranked: list[tuple[float, dict[str, str]]] = []
        for url, elements in pages_data.items():
            ranked_candidates = self.resolver.rank_candidates(action, description, elements)
            all_ranked.extend(ranked_candidates)
            logger.debug(
                "  PAGE %s: %d candidates, top_score=%s",
                url,
                len(ranked_candidates),
                ranked_candidates[0][0] if ranked_candidates else "N/A",
            )

        if not all_ranked:
            if action == "ASSERT" and self._is_page_state_assertion(description):
                return self._select_page_state_candidate(pages_data, description)
            return None

        # Sort by score descending to get the global best match
        all_ranked.sort(key=lambda x: x[0], reverse=True)
        global_top_score = all_ranked[0][0]
        logger.debug(
            "GLOBAL top_score=%s for '%s' (selector=%s)",
            global_top_score,
            description,
            all_ranked[0][1].get("selector", ""),
        )

        # Use a threshold-based shortlist from the global ranking.
        threshold = max(1, global_top_score - 2)
        shortlisted = [element for score, element in all_ranked if score >= threshold][:4]

        matched_element = None
        if len(shortlisted) > 1 and action in {"ASSERT", "CLICK", "FILL"}:
            matched_element = await self.semantic_ranker.choose_best_candidate(
                action=action,
                description=description,
                current_url=current_url,
                candidates=shortlisted,
            )

        # Text validation gate: validate the LLM's choice, then try remaining candidates.
        validated = self._validate_text_match(matched_element, description) if matched_element else None
        if validated is not None:
            return validated

        # LLM's choice failed text validation — try remaining candidates in rank order
        for candidate in shortlisted:
            if self._validate_text_match(candidate, description):
                return candidate

        # Text validation failed all shortlisted candidates — fall back to the LLM's
        # choice anyway but log a warning for diagnostics.
        if matched_element is not None:
            element_text = str(matched_element.get("text", "")).strip()
            logger.warning(
                "LLM-selected element '%s' fails text validation for '%s' — "
                "using anyway (diagnostic review recommended).",
                element_text,
                description,
            )
            if action == "ASSERT":
                return matched_element
            return matched_element

        # No LLM selection — use top candidate with text validation
        if shortlisted:
            top_candidate = shortlisted[0]
            if self._validate_text_match(top_candidate, description):
                return top_candidate
            if action == "ASSERT" and self._is_page_state_assertion(description):
                page_loaded_candidate = self._select_page_loaded_candidate(shortlisted, description)
                if page_loaded_candidate is not None:
                    return page_loaded_candidate
            logger.info(
                "Top-ranked element '%s' fails text validation for '%s' — skipping (unresolved placeholder).",
                str(top_candidate.get("text", "")).strip(),
                description,
            )
        return None

    @staticmethod
    def _is_page_state_assertion(description: str) -> bool:
        """Return True for broad assertions that a named page/state is loaded."""
        lowered = description.lower()
        return any(
            term in lowered
            for term in (
                "page",
                "loaded",
                "badge updated",
                "thank you",
                "success",
                "summary",
            )
        )

    @staticmethod
    def _select_page_state_candidate(
        pages_data: dict[str, list[dict[str, str]]],
        description: str,
    ) -> dict[str, str] | None:
        """Pick a stable visible candidate from the current page for broad page-state assertions."""
        candidates = [element for elements in pages_data.values() for element in elements]
        return PlaceholderOrchestrator._select_page_loaded_candidate(candidates, description)

    @staticmethod
    def _select_page_loaded_candidate(
        candidates: list[dict[str, str]],
        description: str = "",
    ) -> dict[str, str] | None:
        """Pick a stable visible page element for generic "page loaded" assertions."""
        lowered = description.lower()
        if "cart badge" in lowered or "badge updated" in lowered:
            for candidate in candidates:
                candidate_text = " ".join(
                    str(candidate.get(field, "")).lower()
                    for field in ("selector", "text", "classes", "data_test", "aria_label", "accessible_name")
                )
                if "cart" in candidate_text and ("badge" in candidate_text or str(candidate.get("text", "")).strip()):
                    return candidate

        for candidate in candidates:
            role = str(candidate.get("role", "")).strip().lower()
            selector = str(candidate.get("selector", "")).strip()
            if not selector or role in {"hidden", "password", "email", "text", "input"}:
                continue
            if str(candidate.get("is_visible", "true")).lower() == "false":
                continue
            return candidate
        return candidates[0] if candidates else None

    def _select_initial_page_url(
        self,
        journey: TestJourney,
        page_requirements: list[PageRequirement],
        seed_urls: list[str],
        scraped_data: dict[str, list[dict[str, str]]],
        skeleton_lines: list[str] | None = None,
    ) -> str | None:
        """Choose the starting page for one test journey."""
        journey_start_url = self._extract_journey_start_url(journey, skeleton_lines or [])
        if journey_start_url and journey_start_url in scraped_data:
            return journey_start_url

        # Only resolve a GOTO/URL for initial page selection if it appears in the
        # FIRST step of the journey. If the journey starts with CLICK/FILL/ASSERT,
        # the initial page should be the fallback (seed URL), not a GOTO that appears
        # later in the journey.
        if journey.steps:
            first_step = journey.steps[0]
            for placeholder in first_step.placeholders:
                if placeholder.action in {"GOTO", "URL"}:
                    resolved_url = self.resolver.resolve_url(
                        placeholder.description,
                        self._page_requirements_to_pages(page_requirements, scraped_data) or scraped_data,
                    )
                    if resolved_url:
                        return resolved_url
                    break

        return self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)

    @staticmethod
    def _extract_journey_start_url(journey: TestJourney, skeleton_lines: list[str]) -> str | None:
        """Return a per-journey starting URL marker inserted during fragment combine."""
        if not skeleton_lines:
            return None

        marker_prefix = "# JOURNEY_START_URL:"
        scan_index = max(0, journey.start_line - 2)

        while scan_index >= 0:
            stripped = skeleton_lines[scan_index].strip()
            if not stripped:
                break
            if stripped.startswith(marker_prefix):
                return stripped.split(":", 1)[1].strip()
            scan_index -= 1

        return None

    def _page_requirements_to_pages(
        self,
        page_requirements: list[PageRequirement],
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, list[dict[str, str]]] | None:
        """Return scraped data filtered to pages declared in PAGES_NEEDED keywords."""
        if not page_requirements or not scraped_data:
            return None

        filtered: dict[str, list[dict[str, str]]] = {}
        for requirement in page_requirements:
            resolved_url = self.url_resolver.resolve(requirement.keyword)
            if resolved_url and resolved_url in scraped_data:
                filtered[resolved_url] = scraped_data[resolved_url]

        return filtered if filtered else None

    def _select_fallback_page_url(
        self,
        page_requirements: list[PageRequirement],
        seed_urls: list[str],
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> str | None:
        """Return the default page URL to use when no journey-specific page is known."""
        for seed_url in seed_urls:
            if seed_url in scraped_data:
                return seed_url

        for requirement in page_requirements:
            resolved_url = self.url_resolver.resolve(requirement.keyword)
            if resolved_url and resolved_url in scraped_data:
                return resolved_url

        return next(iter(scraped_data), None)
