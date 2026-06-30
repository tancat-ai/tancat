"""Placeholder resolution orchestration extracted from TestOrchestrator."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from src.code_postprocessor import replace_token_in_line
from src.journey_models import CredentialProfile
from src.journey_scraper import CartSeedingScraper
from src.locator_builder import build_robust_locator
from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney
from src.placeholder_resolver import PlaceholderResolver
from src.scraper import PageScraper
from src.semantic_candidate_ranker import AsyncGeneratorLike, SemanticCandidateRanker
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

# B-016: Display roles for ASSERT role filtering.
# These are leaf-level ARIA roles that present information to the user.
# Interactive roles (button, link, textbox) are excluded — ASSERT descriptions
# like "cart badge" should not match cart links by keyword overlap.
DISPLAY_ROLES = frozenset(
    {
        "heading",
        "paragraph",
        "text",
        "status",
        "alert",
        "listitem",
        "cell",
        "columnheader",
        "rowheader",
        "image",
        "strong",
        "em",
        "caption",
        "figure",
        "label",  # <label> elements present form field descriptions
        "generic",  # <span>, <div> — common containers for text content
    }
)

# B-016: Maximum score gap between best display-role element and global top
# before we fall back to non-display elements. Tunable after UAT.
ROLE_FALLBACK_GAP = 3


class PlaceholderOrchestrator:
    """Coordinate placeholder resolution, scraping, and page artifact generation.

    When ``pom_mode`` is enabled, the orchestrator generates tests that import and use
    evidence-aware Page Object Model classes instead of flat ``evidence_tracker`` calls.
    Assertions remain as direct ``evidence_tracker`` calls regardless of POM mode.
    """

    __test__ = False  # type: ignore[assignment]

    def __init__(
        self,
        starting_url: str | None = None,
        credential_profile: CredentialProfile | None = None,
        pom_mode: bool = False,
        generator: AsyncGeneratorLike | None = None,
    ) -> None:
        """Initialise the placeholder resolution orchestrator.

        Args:
            starting_url: Base URL for session-aware scraping.
            credential_profile: Credentials for stateful scraping.
            pom_mode: When True, generate tests using evidence-aware POM classes
                instead of flat ``evidence_tracker`` calls. Assertions remain direct.
            generator: B-020 LLM generator for semantic candidate ranking.
                Pass a configured ``LLMClient`` (which conforms to
                ``AsyncGeneratorLike``) to enable LLM-assisted ASSERT resolution.
                When ``None``, the semantic ranker's ``choose_best_candidate``
                returns ``None`` immediately and ASSERT resolution falls back to
                mechanical ``toBeVisible``.
        """
        self._starting_url = starting_url
        self._credential_profile = credential_profile
        self._pom_mode = pom_mode
        self.resolver = PlaceholderResolver()
        self.scraper = PageScraper()
        self.page_object_builder = PageObjectBuilder()
        self.semantic_ranker = SemanticCandidateRanker(generator)
        self.url_resolver = UrlResolver()
        self._generated_page_objects: list[GeneratedPageObject] = []

    @property
    def pom_mode(self) -> bool:
        """Return whether POM-mode output is enabled."""
        return self._pom_mode

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

            # Merge cart-seeded data for ALL URLs the scraper captured.
            # This includes:
            # - /view_cart and /checkout (replaces empty-cart data with seeded data)
            # - /product_details/* (contains transient popup elements from the capture step)
            # - The home page and category pages (may have richer data after interaction)
            for captured_url, candidate in cart_map.items():
                if not candidate:
                    continue

                # Find the matching URL in scraped_data (handle fragment differences)
                matched_url: str | None = None
                for existing_url in scraped_data:
                    existing_parsed = urlparse(existing_url)
                    candidate_parsed = urlparse(captured_url)
                    # Match on BOTH domain and path — don't mix data from different sites
                    if existing_parsed.netloc == candidate_parsed.netloc and existing_parsed.path.rstrip(
                        "/"
                    ) == candidate_parsed.path.rstrip("/"):
                        matched_url = existing_url
                        break

                if matched_url is None and candidate:
                    # URL not in scraped_data — add it directly.
                    # This captures transient pages (e.g., product detail with popup)
                    # that the journey scraper didn't visit but the cart-seeded scraper did.
                    upgraded[captured_url] = candidate
                    logger.info(
                        "Cart-seeded scrape added new URL '%s': %d elements",
                        captured_url,
                        len(candidate),
                    )

                elif matched_url and candidate:
                    existing = scraped_data.get(matched_url, [])
                    # For cart/checkout: always replace (seeded > empty)
                    # For product detail pages: merge popup elements if we have fewer
                    candidate_parsed = urlparse(captured_url)  # noqa: PLC1101
                    candidate_path = candidate_parsed.path.rstrip("/")
                    if candidate_path in {"/view_cart", "/checkout"}:
                        if candidate and len(candidate) > len(existing):
                            # Only replace if cart-seeded data is richer than what we already have.
                            # This prevents empty/low-quality scrapes from overwriting good data.
                            upgraded[matched_url] = candidate
                            logger.info(
                                "Cart-seeded scrape replaced '%s': %d → %d elements",
                                matched_url,
                                len(existing),
                                len(candidate),
                            )
                    elif len(candidate) < len(existing):
                        # Product detail pages: merge popup elements from the capture step
                        # The cart-seeded scrape has fewer elements because it captured
                        # the page during interaction (with popup overlay), not a full static scrape.
                        # We merge elements that contain modal/popup indicators.
                        existing_selectors = {e.get("selector", "") for e in existing}
                        merged = list(existing)
                        for elem in candidate:
                            sel = elem.get("selector", "")
                            if sel and sel not in existing_selectors:
                                merged.append(elem)
                                existing_selectors.add(sel)
                        if len(merged) > len(existing):
                            upgraded[matched_url] = merged
                            logger.info(
                                "Cart-seeded scrape merged '%s': %d → %d elements (%d new)",
                                matched_url,
                                len(existing),
                                len(merged),
                                len(merged) - len(existing),
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
        """Return page object artifacts generated from scraped pages.

        When ``pom_mode`` is enabled, page objects are built with
        ``use_evidence_tracker=True`` so generated methods delegate to
        ``self.tracker.click()`` / ``self.tracker.fill()`` etc.
        """
        generated_objects: list[GeneratedPageObject] = []

        for scraped_page in scraped_pages:
            generated_objects.append(
                self.page_object_builder.build_page_object(
                    scraped_page,
                    file_path=self.page_object_builder.get_default_file_path(scraped_page.url),
                    use_evidence_tracker=self._pom_mode,
                )
            )

        self._generated_page_objects = generated_objects
        return generated_objects

    # ── POM mode helpers ──────────────────────────────────────────

    def _build_pom_url_map(self, page_objects: list[GeneratedPageObject]) -> dict[str, GeneratedPageObject]:
        """Build a mapping from URL to page object for POM mode resolution.

        Returns a dict where keys are the page URLs and values are the
        corresponding GeneratedPageObject instances.
        """
        url_map: dict[str, GeneratedPageObject] = {}
        for po in page_objects:
            url_map[po.url] = po
        return url_map

    def _build_pom_imports(self, page_objects: list[GeneratedPageObject]) -> list[str]:
        """Generate import statements for POM mode test files.

        Returns lines like::
            from pages.home_page import HomePage
        """
        imports: list[str] = []
        for po in page_objects:
            module_name = po.module_name
            class_name = po.class_name
            imports.append(f"from pages.{module_name} import {class_name}")
        return imports

    def _build_pom_instantiation(
        self,
        page_objects: list[GeneratedPageObject],
        *,
        use_evidence_tracker: bool = True,
    ) -> list[str]:
        """Generate POM instance instantiation lines for test functions.

        In evidence-aware POM mode (default), generates lines like::
            home_page = HomePage(page, evidence_tracker)

        In legacy mode::
            home_page = HomePage(page)
        """
        lines: list[str] = []
        for po in page_objects:
            class_name = po.class_name
            instance_name = po.module_name.replace("-", "_")
            if use_evidence_tracker:
                lines.append(f"{instance_name} = {class_name}(page, evidence_tracker)")
            else:
                lines.append(f"{instance_name} = {class_name}(page)")
        return lines

    def _get_pom_instance_name(self, url: str | None, page_objects: list[GeneratedPageObject]) -> str | None:
        """Return the POM instance variable name for the given URL.

        Returns None if no page object is found for the URL.
        """
        if not url:
            return None
        for po in page_objects:
            if po.url == url:
                return po.module_name.replace("-", "_")
        return None

    def _get_pom_method_call(
        self,
        action: str,
        description: str,
        resolved_selector: str,
        pom_instance_name: str,
        fill_value: str = "",
    ) -> str | None:
        """Generate a POM method call for the given action.

        Returns the method call string, or None if POM mode is not active
        or if the action should remain as a direct evidence_tracker call.

        In POM mode:
        - CLICK -> {instance}.click("label")
        - FILL -> {instance}.fill("label", "value")
        - GOTO/URL -> page.goto(url) (navigation stays direct)
        - ASSERT -> evidence_tracker.assert_visible() (assertions stay direct)
        """
        if not self._pom_mode:
            return None

        # ASSERT always remains as direct evidence_tracker call
        if action == "ASSERT":
            return None

        # GOTO/URL remain as direct page.goto
        if action in {"GOTO", "URL"}:
            return None

        label = description
        if action == "CLICK":
            return f"{pom_instance_name}.click({label!r})"
        if action == "FILL":
            return f"{pom_instance_name}.fill({label!r}, {fill_value!r})"

        return None

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
        # B-020: 7th element is assertion_type (str | None)
        line_resolutions: dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]] = {}
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

            # B-014: track the last interactive selector for ASSERT exclusion
            last_selector: str | None = None
            last_description: str | None = None
            # B-020: track resolved step history for LLM semantic context
            resolved_steps: list[str] = []

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

                    resolved_value, next_url, assertion_type = await self._resolve_placeholder_for_page(
                        action=action,
                        description=description,
                        current_url=current_url,
                        scraped_data=scraped_data,
                        scraped_errors=errors,
                        previous_selector=last_selector,
                        previous_description=last_description,
                        resolved_steps=resolved_steps,
                    )

                    if "pytest.skip" in resolved_value:
                        journey_unresolved[journey.test_name].append(description)
                        # Do NOT add failed resolutions to line_resolutions —
                        # only the consolidated skip at the test top should appear.
                    else:
                        line_resolutions.setdefault(placeholder.line_number, []).append(
                            (
                                placeholder.token,
                                action,
                                resolved_value,
                                description,
                                fill_value,
                                current_url,
                                assertion_type,
                            )
                        )
                        # Track selector for ASSERT exclusion — only CLICK/FILL set the bar
                        if action in {"CLICK", "FILL"}:
                            last_selector = resolved_value
                            last_description = description
                        # B-020: record step for LLM context (CLICK/FILL only)
                        if action in {"CLICK", "FILL"}:
                            selector_short = resolved_value.strip("'\"")
                            resolved_steps.append(f"{action}: {description} -> {selector_short}")

                    if next_url:
                        current_url = next_url

        # 2. Resolve remaining placeholders using fallback context
        resolved_tokens = {
            token
            for replacements in line_resolutions.values()
            for token, _action, _resolved_value, _description, _fill, _url, _at in replacements
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
                resolved_value, _, assertion_type = await self._resolve_placeholder_for_page(
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
                        (use.token, action, resolved_value, description, fill_value, fallback_url, assertion_type)
                    )
            else:
                resolved_value, _, assertion_type = await self._resolve_placeholder_for_page(
                    action=action,
                    description=description,
                    current_url=fallback_url,
                    scraped_data=scraped_data,
                    scraped_errors=errors,
                )
                if "pytest.skip" not in resolved_value:
                    line_resolutions.setdefault(use.line_number, []).append(
                        (use.token, action, resolved_value, description, fill_value, fallback_url, assertion_type)
                    )

        # 3. Apply line-level replacements first.
        final_lines: list[str] = []
        for line_number, line in enumerate(lines, start=1):
            updated_line = line
            for (
                token,
                action,
                resolved_value,
                description,
                fill_value,
                current_url,
                assertion_type,
            ) in line_resolutions.get(line_number, []):
                if self._pom_mode and action in {"CLICK", "FILL"}:
                    instance_name = self._get_pom_instance_name(current_url, self._generated_page_objects)
                    if instance_name:
                        pom_call = self._get_pom_method_call(
                            action=action,
                            description=description,
                            resolved_selector=resolved_value,
                            pom_instance_name=instance_name,
                            fill_value=fill_value,
                        )
                        if pom_call:
                            # Preserve indentation and replace token with POM call
                            indent = line[: len(line) - len(line.lstrip())]
                            # Check if token is wrapped in a page.*() call (LLM emitted page.click("{{CLICK:...}}") instead of bare placeholder)
                            wrapped_pattern = re.compile(
                                r'(page\.\w+)\s*\(\s*["\']?' + re.escape(token) + r'["\']?\s*\)'
                            )
                            wrapped_match = wrapped_pattern.search(updated_line)
                            if wrapped_match:
                                # Replace the entire function call, not just the token
                                updated_line = updated_line.replace(wrapped_match.group(0), pom_call)
                            else:
                                updated_line = updated_line.replace(token, pom_call)
                            # If the line was JUST the token, we need to ensure it has the indent
                            if updated_line.strip() == pom_call:
                                updated_line = f"{indent}{pom_call}"
                            continue

                updated_line = replace_token_in_line(
                    updated_line,
                    action,
                    token,
                    resolved_value,
                    duplicate_selectors,
                    description,
                    fill_value=fill_value,
                    assertion_type=assertion_type or "toBeVisible",
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

        # 7. Remove any remaining raw placeholder lines within test bodies.
        # These are covered by the consolidated skip at the test top, and
        # leaving them would cause code_normalizer to convert them into
        # additional pytest.skip('{{...}}') lines after this function returns.
        final_lines = self._remove_raw_placeholder_lines(final_lines)

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
        """Filter out old per-placeholder skip lines generated by code_normalizer.

        Removes lines like:
        - pytest.skip('Unresolved placeholder in this step. {{CLICK:...}}')
        - pytest.skip('{{ASSERT:Product categories are visible}}')
        - pytest.skip("{{CLICK:Proceed to checkout button}}")

        These are left over when the orchestrator fails to resolve a placeholder
        and code_normalizer replaces the raw token with a pytest.skip() call.
        The consolidated skip inserted by _insert_consolidated_skips() replaces these.
        """
        # Match pytest.skip('{{ACTION:description}}') - raw placeholder token
        raw_placeholder_skip_re = re.compile(r"""pytest\.skip\(\s*['"]\{\{[A-Z_]+:.*?\}\}['"]\s*\)""")
        # Match pytest.skip('Unresolved placeholder in this step. {{...}}')
        unresolved_skip_re = re.compile(
            r"""pytest\.skip\(\s*['"]Unresolved placeholder in this step\.\s*\{\{.*?\}\}['"]\s*\)"""
        )
        result_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if raw_placeholder_skip_re.match(stripped):
                continue
            if unresolved_skip_re.match(stripped):
                continue
            result_lines.append(line)

        return result_lines

    @staticmethod
    def _remove_raw_placeholder_lines(lines: list[str]) -> list[str]:
        """Remove any remaining raw {{ACTION:description}} placeholder lines.

        After resolution, any surviving raw placeholder tokens are covered by
        the consolidated skip at the test top. Removing them prevents
        code_normalizer from converting them into additional pytest.skip()
        lines later in the pipeline.
        """
        raw_placeholder_re = re.compile(r"^\s*\{\{[A-Z_]+:.*?\}\}\s*$")
        result_lines: list[str] = []

        for line in lines:
            if raw_placeholder_re.match(line):
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
        """Insert a single consolidated pytest.skip() at the start of each test with unresolved placeholders.

        The skip is placed AFTER any consent-dismiss or POM-instantiation lines,
        so that dismiss_consent_overlays(page) still runs before the skip.
        """
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

                    # Scan ahead to find where dismiss_consent_overlays is called,
                    # then insert the skip AFTER it so consent dismiss still runs.
                    insert_after = index
                    for scan_idx in range(index + 1, min(index + 15, len(lines))):
                        scan_stripped = lines[scan_idx].strip()
                        if "pytest.skip(" in scan_stripped:
                            # Already has a skip - don't insert another
                            inserted_for.add(test_name)
                            break
                        if "dismiss_consent_overlays(" in scan_stripped and not scan_stripped.startswith("pytest."):
                            insert_after = scan_idx

                    if test_name not in inserted_for:
                        # Insert skip line after the consent dismiss block
                        indent_line = (
                            " " * (len(lines[insert_after]) - len(lines[insert_after].lstrip()))
                            if insert_after > index
                            else indent
                        )
                        result_lines.append(f"{indent_line}{skip_line.strip()}")
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

    def _build_excluded_selectors(
        self,
        action: str,
        description: str,
        previous_selector: str | None,
        previous_description: str | None,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> set[str]:
        """Build a set of selectors to exclude for this resolution.

        For ASSERT: excludes the previous step's selector unless descriptions match
        (meaning the test is asserting the same element's state).
        For CLICK/FILL: returns empty set (no exclusion needed).
        """
        if action != "ASSERT" or not previous_selector:
            return set()

        # Allow reuse if descriptions reference the same element.
        # Use a strict containment check: one description must be contained
        # in the other (normalised), or they share ≥ 75% of content words.
        # This prevents false reuse like "add to cart for Backpack" matching
        # "Backpack name in cart" — those describe different elements.
        if previous_description and self._descriptions_reference_same_element(previous_description, description):
            return set()

        # Find all selector forms for the previously resolved element
        excluded: set[str] = {previous_selector}
        for elements in pages_data.values():
            for element in elements:
                raw_selector = str(element.get("selector", "")).strip()
                robust = build_robust_locator(element)
                # Match against both robust locator and raw selector
                if (robust and robust == previous_selector) or raw_selector == previous_selector:
                    if robust:
                        excluded.add(robust)
                    if raw_selector:
                        excluded.add(raw_selector)

        return excluded

    @staticmethod
    def _descriptions_reference_same_element(desc_a: str, desc_b: str) -> bool:
        """Return True when two descriptions likely reference the same element.

        Uses strict containment: one normalised description must be contained
        within the other. This catches 'login button' vs 'login button is
        disabled' but NOT 'add to cart for Backpack' vs 'Backpack name in cart'.
        """
        norm_a = re.sub(r"[_\-]", " ", desc_a).strip().lower()
        norm_b = re.sub(r"[_\-]", " ", desc_b).strip().lower()

        # Direct containment — strongest signal
        if norm_a in norm_b or norm_b in norm_a:
            return True

        return False

    async def _resolve_placeholder_for_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
        previous_selector: str | None = None,
        previous_description: str | None = None,
        resolved_steps: list[str] | None = None,
    ) -> tuple[str, str | None, str | None]:
        """Resolve one placeholder using the active page first, then fall back to known pages.

        Args:
            previous_selector: The selector resolved by the previous interactive step.
            previous_description: The description from the previous interactive step.
                Used for B-014 step-context exclusion: an ASSERT should not resolve
                to the same element as the preceding CLICK/FILL unless the descriptions
                semantically reference the same element.
            resolved_steps: B-020 list of compressed step descriptions for LLM context.
        """
        await self._ensure_scraped(current_url, scraped_data, scraped_errors)
        scoped_pages = self._build_scoped_pages(current_url, scraped_data)

        if action in {"GOTO", "URL"}:
            # Step 1: Try UrlResolver (keyword → URL mapping from scraped URLs)
            url_from_resolver = self.url_resolver.resolve(description)
            if url_from_resolver:
                logger.debug("UrlResolver matched '%s' -> %s", description, url_from_resolver)
                return repr(url_from_resolver), url_from_resolver, None

            # Step 2: Try PlaceholderResolver (scraped element matching)
            resolved_url = self.resolver.resolve_url(description, scoped_pages or scraped_data)
            if resolved_url:
                return repr(resolved_url), resolved_url, None

            # Step 3: Heuristic fallback
            if current_url:
                heuristic = heuristic_url_from_description(current_url, description)
                if heuristic:
                    await self._ensure_scraped(heuristic, scraped_data, scraped_errors)
                    return repr(heuristic), heuristic, None

            # Step 4: Try seed URL as last resort
            seed_url = self.url_resolver.get_seed_url()
            if seed_url:
                logger.debug("Falling back to seed URL for '%s': %s", description, seed_url)
                return repr(seed_url), seed_url, None

            error_msg = f"Locator for '{description}' not found on scraped pages."
            if current_url and scraped_errors and current_url in scraped_errors:
                error_msg += f" (Note: scraping {current_url} failed with {scraped_errors[current_url]})"
            return f'pytest.skip("{error_msg}")', None, None

        # When scoped_pages is empty (current_url not in scraped_data), fall back to
        # ALL scraped pages. The "no fallback" rule prevents using wrong-page elements
        # when the current page HAS data. But when scoped_pages is empty due to URL
        # normalization differences (trailing slash, query params, etc.), we must
        # search all pages to find the element.
        pages_to_search = scoped_pages if scoped_pages else scraped_data

        # B-014: build excluded selectors for ASSERT
        excluded = self._build_excluded_selectors(
            action, description, previous_selector, previous_description, pages_to_search
        )

        matched_element = await self._find_best_element_for_current_page(
            action,
            description,
            current_url,
            pages_to_search,
            excluded_selectors=excluded or None,
            resolved_steps=resolved_steps,
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
            # B-020: extract assertion_type from matched_element for ASSERT actions
            assertion_type = matched_element.get("assertion_type") if action == "ASSERT" else None
            return selector, next_url, assertion_type

        error_msg = f"Locator for '{description}' not found on scraped pages."
        print(f"[DEBUG] Failed to find '{description}'. Available scraped URLs: {list(scraped_data.keys())}")
        return f'pytest.skip("{error_msg}")', None, None

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

    def _get_effective_role(self, element: dict[str, str]) -> str:
        """Resolve ARIA role: computed_role (CDP AX tree) -> raw role (HTML attr/tag).

        B-016: computed_role is set by the accessibility enricher (AI-024) and
        contains the proper computed ARIA role. Falls back to the raw ``role``
        field which is the HTML role attribute or tag-name fallback.
        """
        return str(element.get("computed_role") or element.get("role", "")).strip().lower()

    # Implicit ARIA role mapping for HTML tags.
    # Used when computed_role is unavailable (e.g. journey scraper enrichment fails).
    _TAG_TO_ROLE: dict[str, str] = {
        "a": "link",
        "abbr": "text",
        "address": "paragraph",
        "article": "article",
        "aside": "complementary",
        "b": "strong",
        "bdi": "text",
        "bdo": "text",
        "blockquote": "blockquote",
        "button": "button",
        "caption": "caption",
        "cite": "text",
        "code": "text",
        "data": "text",
        "dd": "definition",
        "del": "deletion",
        "details": "group",
        "dfn": "text",
        "div": "generic",
        "dl": "list",
        "dt": "term",
        "em": "em",
        "embed": "embed",
        "fieldset": "group",
        "figure": "figure",
        "footer": "contentinfo",
        "h1": "heading",
        "h2": "heading",
        "h3": "heading",
        "h4": "heading",
        "h5": "heading",
        "h6": "heading",
        "header": "banner",
        "hr": "separator",
        "i": "em",
        "img": "image",
        "input": "textbox",  # simplified — type determines actual role
        "ins": "insertion",
        "kbd": "text",
        "label": "label",
        "legend": "legend",
        "li": "listitem",
        "main": "main",
        "mark": "text",
        "nav": "navigation",
        "ol": "list",
        "output": "status",
        "p": "paragraph",
        "picture": "generic",
        "pre": "text",
        "progress": "progressbar",
        "q": "text",
        "rb": "text",
        "rp": "text",
        "rt": "text",
        "rtc": "text",
        "ruby": "text",
        "s": "deletion",
        "samp": "text",
        "section": "region",
        "select": "listbox",  # simplified
        "small": "text",
        "span": "generic",
        "strong": "strong",
        "sub": "text",
        "sup": "text",
        "table": "table",
        "tbody": "rowgroup",
        "td": "cell",
        "textarea": "textbox",
        "tfoot": "rowgroup",
        "th": "columnheader",  # simplified — scope determines row/column
        "thead": "rowgroup",
        "time": "text",
        "tr": "row",
        "u": "text",
        "ul": "list",
        "var": "text",
    }

    def _is_display_role(self, element: dict[str, str]) -> bool:
        """Check if an element's effective role is a display (non-interactive) role.

        B-016: Used for ASSERT role filtering. Resolution priority:
        1. ``computed_role`` from CDP AX tree enrichment (authoritative when present)
        2. ``role`` field — if it's a known ARIA role name (not a tag name), use it
        3. ``tag`` field — mapped through implicit ARIA role table
        4. ``role`` field as tag name — mapped through implicit ARIA role table

        The scraper stores tag names in the ``role`` field when no explicit
        role attribute exists. The enricher writes ``computed_role`` from the
        AX tree but often fails to match elements, leaving it None.
        """
        # 1. computed_role from CDP AX tree — authoritative
        computed = str(element.get("computed_role", "")).strip().lower()
        if computed:
            return computed in DISPLAY_ROLES

        # 2. raw role field — could be explicit ARIA role or tag-name fallback
        raw_role = str(element.get("role", "")).strip().lower()

        # 3. tag field if available
        tag = str(element.get("tag", "")).strip().lower()

        # Check if raw_role is an explicit ARIA role (not a tag name)
        if raw_role in DISPLAY_ROLES:
            return True

        # Map via tag name (tag field first, then role-as-tag fallback)
        effective_tag = tag if tag else raw_role
        mapped_role = self._TAG_TO_ROLE.get(effective_tag, "")
        return mapped_role in DISPLAY_ROLES

    def _pass0_exact_text_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 0 — exact text match for ASSERT descriptions wrapped in quotes.

        B-020: When the skeleton emits ASSERT:"exact text here", strip the quotes
        and do literal string equality against element text. This bypasses all
        scoring and LLM calls for the simple "verify text is X" case.
        """
        if action != "ASSERT":
            return None

        # Strip surrounding quotes if present
        text = description
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            text = text[1:-1]
        if not text:
            return None

        norm_target = text.strip().lower()
        if len(norm_target) < 2:
            return None

        for elements in pages_data.values():
            for element in elements:
                norm_text = self._normalise_element_text(element)
                if norm_text == norm_target:
                    return element

        return None

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

        REGRESSION FIX (2026-05-17): When the description contains action verbs
        (add, remove, place, buy, etc.), require the element text to contain at
        least one of those action words. This prevents "Add to cart button" from
        matching the "View Cart" link just because both contain the word "cart".
        """
        if action not in {"CLICK", "FILL"}:
            return None

        norm_description = description.lower()

        # Check if the description contains action verbs — these need stricter matching
        desc_words = set(norm_description.split())
        has_action_verb = bool(desc_words & PlaceholderResolver.ACTION_VERBS)

        for elements in pages_data.values():
            for element in elements:
                norm_text = self._normalise_element_text(element)
                if len(norm_text) >= 3 and norm_text in norm_description:
                    # When action verbs are present, require the element text to
                    # contain at least one action word from the description.
                    # This prevents "cart" in "View Cart" from beating "Add to cart"
                    # when the description is "Add to cart button next to Blue Top".
                    if has_action_verb:
                        text_words = set(norm_text.split())
                        action_words_in_desc = desc_words & PlaceholderResolver.ACTION_VERBS
                        if not (text_words & action_words_in_desc):
                            # Element text lacks the action verb — skip it
                            continue
                    return element

        return None

    def _pass1_assert_text_match(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, str] | None:
        """Pass 1 (ASSERT) — match text-bearing elements whose label appears in the description.

        Requires the element text to contain at least 2 of the description's content words
        to avoid false positives like "Summary" matching "cart summary" when "Cart Summary"
        exists on a different page.
        """
        if action != "ASSERT":
            return None

        norm_description = description.lower()
        desc_words = set(norm_description.split())

        # Stop words that are too common to be useful for matching
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "and",
            "or",
            "but",
            "not",
            "in",
            "on",
            "at",
            "to",
            "for",
            "with",
            "by",
            "from",
            "of",
            "as",
            "into",
            "through",
            "page",
            "element",
            "visible",
            "displayed",
            "shown",
        }
        desc_content_words = desc_words - stop_words

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

        # If description has multiple content words, require multi-word match
        requires_multi_word = len(desc_content_words) >= 2

        for elements in pages_data.values():
            for element in elements:
                # B-016: check computed_role (CDP AX tree) first, then raw role, then tag
                effective_role = str(element.get("computed_role") or element.get("role", "")).strip().lower()
                tag = str(element.get("tag", "")).strip().lower()
                if effective_role not in text_bearing_roles and tag not in text_bearing_tags:
                    continue
                norm_text = self._normalise_element_text(element)
                if len(norm_text) >= 3 and norm_text in norm_description:
                    if requires_multi_word:
                        # Require the element text to contain at least 2 content words from description
                        elem_words = set(norm_text.lower().replace("_", " ").split())
                        overlap = elem_words & desc_content_words
                        if len(overlap) < 2:
                            continue
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
                # B-016: for ASSERT, prefer display elements over interactive ones
                if action == "ASSERT" and not self._is_display_role(element):
                    continue
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

    @staticmethod
    def _is_excluded(element: dict[str, str], excluded_selectors: set[str]) -> bool:
        """Check if an element should be excluded from consideration."""
        raw = str(element.get("selector", "")).strip()
        if raw in excluded_selectors:
            return True
        robust = build_robust_locator(element)
        if robust and robust in excluded_selectors:
            return True
        return False

    async def _find_best_element_for_current_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        pages_data: dict[str, list[dict[str, str]]],
        excluded_selectors: set[str] | None = None,
        resolved_steps: list[str] | None = None,
    ) -> dict[str, str] | None:
        """Return the best element match across the supplied page mapping.

        IMPORTANT: Collects candidates from ALL pages first, then selects the global
        best match. This prevents returning a low-quality match from an early page
        when a much better match exists on a later page (e.g., finding a cart page
        element for "username input" instead of the login page element).

        Args:
            excluded_selectors: Selectors to exclude from consideration. Used by
                B-014 step-context: prevents ASSERT from resolving to the same
                element as the preceding CLICK/FILL step.
            resolved_steps: B-020 list of compressed prior step descriptions.
        """
        # B-020 Pass 0 — exact text match for ASSERT:"exact text"
        pass0_result = self._pass0_exact_text_match(action, description, pages_data)
        if pass0_result is not None:
            if not excluded_selectors or not self._is_excluded(pass0_result, excluded_selectors):
                self._log_resolve_pass(0, "exact text match", description, pass0_result)
                # Tag with assertion_type for code_postprocessor
                pass0_result["assertion_type"] = "toHaveText"
                pass0_result["expected_value"] = description.strip("'\"")
                return pass0_result
            logger.debug(
                "[RESOLVE] '%s' | pass=0 exact text EXCLUDED (step context)",
                description,
            )

        # Pass 1 — fast text match (CLICK/FILL)
        pass1_result = self._pass1_text_match(action, description, pages_data)
        if pass1_result is not None:
            if not excluded_selectors or not self._is_excluded(pass1_result, excluded_selectors):
                self._log_resolve_pass(1, "text match", description, pass1_result)
                return pass1_result
            logger.debug(
                "[RESOLVE] '%s' | pass=1 text match EXCLUDED (step context)",
                description,
            )

        # Pass 1 — ASSERT text-bearing elements
        pass1_assert = self._pass1_assert_text_match(action, description, pages_data)
        if pass1_assert is not None:
            if not excluded_selectors or not self._is_excluded(pass1_assert, excluded_selectors):
                self._log_resolve_pass(1, "assert text match", description, pass1_assert)
                return pass1_assert
            logger.debug(
                "[RESOLVE] '%s' | pass=1 assert text match EXCLUDED (step context)",
                description,
            )

        # Pass 2 — structural attribute match
        pass2_result = self._pass2_structural_match(action, description, pages_data)
        if pass2_result is not None:
            if not excluded_selectors or not self._is_excluded(pass2_result, excluded_selectors):
                self._log_resolve_pass(2, "structural match", description, pass2_result)
                return pass2_result
            logger.debug(
                "[RESOLVE] '%s' | pass=2 structural match EXCLUDED (step context)",
                description,
            )

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

        # B-014: filter out excluded selectors from scoring candidates
        if excluded_selectors:
            before = len(all_ranked)
            all_ranked = [
                (score, elem) for score, elem in all_ranked if not self._is_excluded(elem, excluded_selectors)
            ]
            if len(all_ranked) < before:
                logger.debug(
                    "[RESOLVE] '%s' | excluded %d candidate(s) (step context)",
                    description,
                    before - len(all_ranked),
                )

        # Sort by score descending so all_ranked[0] is the global best.
        all_ranked.sort(key=lambda x: x[0], reverse=True)

        # B-016: soft role filtering for ASSERT — prefer display-role elements.
        # If the best display-role element scores within ROLE_FALLBACK_GAP of the
        # global top, use it. Otherwise fall back to the global best with a warning.
        if action == "ASSERT" and all_ranked:
            display_ranked = [(s, e) for s, e in all_ranked if self._is_display_role(e)]
            global_top_score_all = all_ranked[0][0]

            if display_ranked:
                best_display_score = display_ranked[0][0]
                gap = global_top_score_all - best_display_score

                if gap <= ROLE_FALLBACK_GAP:
                    # Display element is competitive — use it
                    logger.debug(
                        "[RESOLVE] '%s' | B-016 role filter: using display element "
                        "(score=%s, gap=%d from global top %s)",
                        description,
                        best_display_score,
                        gap,
                        global_top_score_all,
                    )
                    all_ranked = display_ranked
                else:
                    logger.warning(
                        "[RESOLVE] '%s' | B-016 low-confidence fallback: "
                        "best display score=%s is %d below global top=%s — "
                        "using non-display element",
                        description,
                        best_display_score,
                        gap,
                        global_top_score_all,
                    )
            else:
                logger.debug(
                    "[RESOLVE] '%s' | B-016: no display-role candidates, scoring all %d elements",
                    description,
                    len(all_ranked),
                )

        if not all_ranked:
            # No candidates scored at all — for ASSERT, do NOT fall back to a random element.
            # Returning a generic element (e.g., a[href="/"]) for an assertion like
            # "cart page table of added items" produces tests that pass for the wrong reason.
            # It's better to skip the test with a clear message than assert the wrong element.
            return None

        global_top_score = all_ranked[0][0]
        logger.debug(
            "GLOBAL top_score=%s for '%s' (selector=%s)",
            global_top_score,
            description,
            all_ranked[0][1].get("selector", ""),
        )

        # B-020: ASSERT gets a semantic LLM pass with step context.
        # Non-ASSERT actions keep the mechanical shortlist + LLM path.
        if action == "ASSERT":
            return await self._resolve_assert_semantically(
                all_ranked=all_ranked,
                description=description,
                current_url=current_url,
                resolved_steps=resolved_steps,
            )

        # Non-ASSERT: threshold-based shortlist from global ranking.
        threshold = max(1, global_top_score - 2)
        shortlisted = [element for score, element in all_ranked if score >= threshold][:4]

        matched_element = None
        if len(shortlisted) > 1 and action in {"CLICK", "FILL"}:
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
            return matched_element

        # No LLM selection — use top candidate with text validation
        if shortlisted:
            top_candidate = shortlisted[0]
            if self._validate_text_match(top_candidate, description):
                return top_candidate
            logger.info(
                "Top-ranked element '%s' fails text validation for '%s' — skipping (unresolved placeholder).",
                str(top_candidate.get("text", "")).strip(),
                description,
            )
        return None

    async def _resolve_assert_semantically(
        self,
        *,
        all_ranked: list[tuple[float, dict[str, str]]],
        description: str,
        current_url: str | None,
        resolved_steps: list[str] | None = None,
    ) -> dict[str, str] | None:
        """B-020: Resolve ASSERT using LLM semantic ranking with step context.

        Builds a curated candidate pool of display elements + top scorers,
        then delegates to the LLM which selects both the best element and
        the appropriate assertion type.
        """
        # Build candidate pool: top 3 scorers + top 3 display elements (deduplicated)
        seen_selectors: set[str] = set()
        candidate_pool: list[dict[str, Any]] = []

        # Add top scorers first (up to 3)
        for _score, element in all_ranked[:3]:
            sel = element.get("selector", "")
            if sel and sel not in seen_selectors:
                seen_selectors.add(sel)
                candidate_pool.append(element)

        # Add display-role elements (up to 3 more)
        for _score, element in all_ranked:
            if len(candidate_pool) >= 6:
                break
            if self._is_display_role(element):
                sel = element.get("selector", "")
                if sel and sel not in seen_selectors:
                    seen_selectors.add(sel)
                    candidate_pool.append(element)

        logger.debug("[B-020] ASSERT semantic pass for '%s': %d candidates in pool", description, len(candidate_pool))

        if not candidate_pool:
            return None

        # Single candidate — fast path
        if len(candidate_pool) == 1:
            result = dict(candidate_pool[0])
            result["assertion_type"] = "toBeVisible"
            return result

        # LLM semantic ranking with step context
        matched_element = await self.semantic_ranker.choose_best_candidate(
            action="ASSERT",
            description=description,
            current_url=current_url,
            candidates=candidate_pool,
            previous_steps=resolved_steps,
        )

        if matched_element is not None:
            assertion_type = matched_element.get("assertion_type", "toBeVisible")
            logger.info(
                "[B-020] ASSERT '%s' -> selector=%s, assertion_type=%s",
                description,
                matched_element.get("selector", ""),
                assertion_type,
            )
            return matched_element

        # LLM failed — fall back to mechanical top score with toBeVisible default
        logger.warning(
            "[B-020] ASSERT '%s': LLM semantic pass failed, falling back to top scorer",
            description,
        )
        fallback = dict(all_ranked[0][1])
        fallback["assertion_type"] = "toBeVisible"
        return fallback

    @staticmethod
    def _select_page_loaded_candidate(
        candidates: list[dict[str, str]],
        description: str = "",
    ) -> dict[str, str] | None:
        """Pick a stable visible page element for generic "page loaded" assertions.

        Only returns a candidate if the description contains specific keywords that
        we can match against element metadata. For generic descriptions, returns None
        so the placeholder remains unresolved and the test skips with a clear message.
        """
        lowered = description.lower()
        if "cart badge" in lowered or "badge updated" in lowered:
            for candidate in candidates:
                candidate_text = " ".join(
                    str(candidate.get(field, "")).lower()
                    for field in ("selector", "text", "classes", "data_test", "aria_label", "accessible_name")
                )
                if "cart" in candidate_text and ("badge" in candidate_text or str(candidate.get("text", "")).strip()):
                    return candidate

        return None

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
