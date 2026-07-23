"""Placeholder resolution orchestration extracted from TestOrchestrator.

Element matching (passes 0-3, B-020 semantic ASSERT) delegated to
``element_matcher.ElementMatcher``. POM helpers to ``pom_helpers``.
Skip insertion to ``skip_manager``. Role mapping to ``role_mapper``.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

if TYPE_CHECKING:
    from src.rag_retriever import RAGRetriever

from src.cart_seeding_scraper import CartSeedingScraper
from src.code_postprocessor import replace_token_in_line
from src.element_matcher import ElementMatcher
from src.journey_models import CredentialProfile
from src.locator_builder import build_robust_locator
from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney
from src.placeholder_resolver import PlaceholderResolver
from src.pom_helpers import (
    build_page_object_artifacts,
    build_pom_imports,
    build_pom_instantiation,
    build_pom_url_map,
    get_pom_instance_name,
    get_pom_method_call,
)
from src.role_mapper import (
    get_effective_role,
    is_display_role,
    normalise_element_text,
)
from src.scraper import PageScraper
from src.section_scoper import scope_elements
from src.semantic_candidate_ranker import AsyncGeneratorLike, SemanticCandidateRanker
from src.skip_manager import (
    insert_consolidated_skips,
    remove_old_placeholder_skips,
    remove_raw_placeholder_lines,
)
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
        rag_retriever: RAGRetriever | None = None,
    ) -> None:
        """Initialise the placeholder resolution orchestrator.

        Args:
            starting_url: Base URL for session-aware scraping.
            credential_profile: Credentials for stateful scraping.
            pom_mode: When True, generate tests using evidence-aware POM classes
                instead of flat ``evidence_tracker`` calls. Assertions remain direct.
            generator: B-020 LLM generator for semantic candidate ranking.
            rag_retriever: Optional RAG retriever for golden-pattern scoring.
                When ``None``, RAG is disabled (zero overhead).
        """
        self._starting_url = starting_url
        self._credential_profile = credential_profile
        self._pom_mode = pom_mode
        self.resolver = PlaceholderResolver()
        self.scraper = PageScraper()
        self.url_resolver = UrlResolver()
        self._element_matcher = ElementMatcher(self.resolver, generator)
        self._generated_page_objects: list[GeneratedPageObject] = []
        self.page_object_builder = PageObjectBuilder()
        self.semantic_ranker = SemanticCandidateRanker(generator)
        self._rag_retriever = rag_retriever

    @property
    def pom_mode(self) -> bool:
        """Return whether POM-mode output is enabled."""
        return self._pom_mode

    # ═════════════════════════════════════════════════════════════
    # Scraping helpers
    # ═════════════════════════════════════════════════════════════

    async def _ensure_scraped(
        self,
        url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None = None,
    ) -> None:
        """Scrape the URL once and cache into scraped_data."""
        if not url or url in scraped_data:
            return

        parsed = urlparse(url)
        is_stateful_target = parsed.path.rstrip("/") in {"/view_cart", "/checkout"}
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
            parsed = urlparse(url)
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
                    absolute_targets.append(urljoin(self._starting_url, url))

            # Try to find a product page URL that has actual product elements
            # (not just category links). Fall back to /products if none found.
            products_url: str | None = None
            for url, _elements in scraped_data.items():
                parsed = urlparse(url)
                path = parsed.path.rstrip("/")
                if any(term in path for term in ("/category_products", "/category/", "/products/", "/inventory")):
                    products_url = url
                    break
            if not products_url:
                products_url = urljoin(self._starting_url, "/products")

            cart_scraper = CartSeedingScraper(self._starting_url, products_url=products_url)
            cart_map = await cart_scraper.scrape_cart_pages(absolute_targets)

            for captured_url, candidate in cart_map.items():
                if not candidate:
                    continue

                matched_url: str | None = None
                for existing_url in scraped_data:
                    existing_parsed = urlparse(existing_url)
                    candidate_parsed = urlparse(captured_url)
                    if existing_parsed.netloc == candidate_parsed.netloc and existing_parsed.path.rstrip(
                        "/"
                    ) == candidate_parsed.path.rstrip("/"):
                        matched_url = existing_url
                        break

                if matched_url is None and candidate:
                    upgraded[captured_url] = candidate
                    logger.info(
                        "Cart-seeded scrape added new URL '%s': %d elements",
                        captured_url,
                        len(candidate),
                    )
                elif matched_url and candidate:
                    existing = scraped_data.get(matched_url, [])
                    candidate_parsed = urlparse(captured_url)
                    candidate_path = candidate_parsed.path.rstrip("/")
                    if candidate_path in {"/view_cart", "/checkout"}:
                        # For cart/checkout pages, ALWAYS prefer cart-seeded data.
                        # An empty cart page may have more elements (promotional content)
                        # than a cart with items, but the seeded data has the correct state
                        # (checkout button, cart table, quantity columns).
                        # Merge: cart-seeded elements take priority; keep unique elements
                        # from the static scrape that don't exist in the seeded data.
                        existing_selectors = {e.get("selector", "") for e in existing}
                        candidate_selectors = {e.get("selector", "") for e in candidate}
                        merged = list(candidate)  # cart-seeded data first
                        for elem in existing:
                            sel = elem.get("selector", "")
                            if sel and sel not in candidate_selectors:
                                merged.append(elem)
                        upgraded[matched_url] = merged
                        logger.info(
                            "Cart-seeded scrape upgraded '%s': %d existing + %d seeded → %d merged",
                            matched_url,
                            len(existing),
                            len(candidate),
                            len(merged),
                        )
                    elif len(candidate) < len(existing):
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
            parsed = urlparse(url)
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

    # ═════════════════════════════════════════════════════════════
    # POM artifact generation (delegates to pom_helpers)
    # ═════════════════════════════════════════════════════════════

    def _build_page_object_artifacts(self, scraped_pages: list[ScrapedPage]) -> list[GeneratedPageObject]:
        generated = build_page_object_artifacts(scraped_pages, pom_mode=self._pom_mode)
        self._generated_page_objects = generated
        return generated

    # ═════════════════════════════════════════════════════════════
    # Main resolution pipeline
    # ═════════════════════════════════════════════════════════════

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

            last_selector: str | None = None
            last_description: str | None = None
            resolved_steps: list[str] = []

            for step in journey.steps:
                if current_url is None:
                    current_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)

                for placeholder in step.placeholders:
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
                        if action in {"CLICK", "FILL"}:
                            last_selector = resolved_value
                            last_description = description
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

            fill_value = ""
            action = use.action
            description = use.description

            if action == "FILL" and ":" in description:
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
                    instance_name = get_pom_instance_name(current_url, self._generated_page_objects)
                    if instance_name:
                        pom_call = get_pom_method_call(
                            action=action,
                            description=description,
                            resolved_selector=resolved_value,
                            pom_instance_name=instance_name,
                            fill_value=fill_value,
                        )
                        if pom_call:
                            indent = line[: len(line) - len(line.lstrip())]
                            wrapped_pattern = re.compile(
                                r'(page\.\w+)\s*\(\s*["\']?' + re.escape(token) + r'["\']?\s*\)'
                            )
                            wrapped_match = wrapped_pattern.search(updated_line)
                            if wrapped_match:
                                updated_line = updated_line.replace(wrapped_match.group(0), pom_call)
                            else:
                                updated_line = updated_line.replace(token, pom_call)
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
        final_lines = insert_consolidated_skips(
            final_lines,
            journeys,
            journey_unresolved,
            lines,
        )

        # 6. Remove old per-placeholder skip lines.
        final_lines = remove_old_placeholder_skips(final_lines, journeys)

        # 7. Remove any remaining raw placeholder lines within test bodies.
        final_lines = remove_raw_placeholder_lines(final_lines)

        return "\n".join(final_lines)

    # ═════════════════════════════════════════════════════════════
    # Resolution engine
    # ═════════════════════════════════════════════════════════════

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
            previous_description: The description from the previous interactive step
                (B-014 step-context exclusion).
            resolved_steps: B-020 list of compressed step descriptions for LLM context.
        """
        await self._ensure_scraped(current_url, scraped_data, scraped_errors)
        scoped_pages = self._build_scoped_pages(current_url, scraped_data)

        if action in {"GOTO", "URL"}:
            # Step 1: Try UrlResolver
            url_from_resolver = self.url_resolver.resolve(description)
            if url_from_resolver:
                logger.debug("UrlResolver matched '%s' -> %s", description, url_from_resolver)
                return repr(url_from_resolver), url_from_resolver, None

            # Step 2: Try PlaceholderResolver
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

        pages_to_search = scoped_pages if scoped_pages else scraped_data

        # 1b: Section-aware scoping — filter elements to the section named
        # in the placeholder description (e.g. "on account page").
        pages_to_search = self._apply_section_scoping(
            action,
            description,
            pages_to_search,
        )

        # B-021: For ASSERT placeholders describing page state ("home page visible",
        # "dress products page"), resolve as URL assertions instead of element matches.
        if action == "ASSERT" and self._is_page_state_assertion(description):
            resolved_url = self.resolver.resolve_url(description, scraped_data, known_urls=list(scraped_data.keys()))
            if resolved_url:
                logger.info("URL assertion resolved '%s' → %s", description, resolved_url)
                return f'expect(page).to_have_url("{resolved_url}")', None, "url"
            logger.debug("URL assertion failed for '%s' — falling through to element resolution", description)

        excluded = self._build_excluded_selectors(
            action, description, previous_selector, previous_description, pages_to_search
        )

        # RAG retrieval: fetch golden patterns for scoring bonus
        golden_patterns = self._retrieve_golden_patterns(action, description)

        matched_element = await self._element_matcher.find_best_element_for_current_page(
            action,
            description,
            current_url,
            pages_to_search,
            excluded_selectors=excluded or None,
            resolved_steps=resolved_steps,
            golden_patterns=golden_patterns or None,
        )

        if matched_element is not None:
            self._verify_page_context(description, matched_element, current_url, scraped_data)

            robust_selector = build_robust_locator(matched_element)
            if not robust_selector:
                robust_selector = str(matched_element.get("selector", "")).strip()
            selector = repr(robust_selector)
            next_url = infer_next_page_url(action, description, matched_element, scraped_data, current_url)
            if next_url:
                await self._ensure_scraped(next_url, scraped_data, scraped_errors)
            assertion_type = matched_element.get("assertion_type") if action == "ASSERT" else None
            return selector, next_url, assertion_type

        error_msg = f"Locator for '{description}' not found on scraped pages."
        print(f"[DEBUG] Failed to find '{description}'. Available scraped URLs: {list(scraped_data.keys())}")
        return f'pytest.skip("{error_msg}")', None, None

    def _retrieve_golden_patterns(
        self,
        action: str,
        description: str,
    ) -> list | None:
        """Retrieve golden patterns from the RAG store for this placeholder.

        Returns ``None`` when RAG is disabled or no patterns match.
        """
        if self._rag_retriever is None:
            return None
        patterns = self._rag_retriever.retrieve(description, action_type=action)
        return patterns if patterns else None

    def _is_page_state_assertion(self, description: str) -> bool:
        """Check if an ASSERT description refers to a page state rather than an element.

        B-021: Returns True for descriptions like "home page visible",
        "dress products page", "cart page loaded" — these should be resolved
        as URL assertions (expect(page).to_have_url(...)).

        Only triggers when the description is PURELY about page state — if it
        mentions specific elements (title, heading, button, link, text, list,
        table, item, name, price, quantity, confirmation), it's an element
        assertion, not a page-state assertion.
        """
        lowered = description.replace("_", " ").lower()

        # Element-level keywords — if present, this is an element assertion,
        # not a page-state assertion, even if page names are also mentioned.
        element_keywords = (
            "title",
            "heading",
            "button",
            "link",
            "text",
            "list",
            "table",
            "item",
            "name",
            "price",
            "quantity",
            "confirmation",
            "popup",
            "message",
            "badge",
            "icon",
            "field",
            "input",
            "label",
            "image",
            "banner",
            "logo",
            "product card",
        )
        if any(kw in lowered for kw in element_keywords):
            return False

        page_state_terms = (
            "home page",
            "landing page",
            "start page",
            "checkout page",
            "products page",
            "product page",
            "cart page",
            "shopping cart page",
            "thank you page",
            "success page",
            "confirmation page",
            "dress products page",
            "page is loaded",
            "page loads",
            "page is visible",
            "page displays",
            "page shows",
            "returned to",
        )
        return any(term in lowered for term in page_state_terms)

    def _build_scoped_pages(
        self,
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, list[dict[str, str]]]:
        """Return a page mapping scoped to the current journey URL when available."""
        if current_url and current_url in scraped_data:
            return {current_url: scraped_data[current_url]}
        return {}

    def _apply_section_scoping(
        self,
        action: str,
        description: str,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> dict[str, list[dict[str, str]]]:
        """Filter each page's elements to the section named in the description.

        Falls back to the full element list when no section hint is found.
        This is a no-op for multi-page sites (each URL has one section).
        The benefit is for eval harness and future SPA support.

        When section scoping narrows the list and the action is interactive
        (CLICK/FILL/SELECT), also applies a hidden-element penalty via
        PlaceholderScorer so that visible candidates within the section
        rank above hidden ones.
        """
        result: dict[str, list[dict[str, str]]] = {}
        for url, elements in pages_data.items():
            scoped, section_name = scope_elements(description, elements)
            result[url] = scoped
            if section_name:
                logger.debug(
                    "Section scoping: '%s' → section '%s' (%d elements)",
                    description,
                    section_name,
                    len(scoped),
                )
        return result

    # ═════════════════════════════════════════════════════════════
    # URL / context helpers
    # ═════════════════════════════════════════════════════════════

    @staticmethod
    def _descriptions_reference_same_element(desc_a: str, desc_b: str) -> bool:
        """Return True when two descriptions likely reference the same element."""
        norm_a = re.sub(r"[_\-]", " ", desc_a).strip().lower()
        norm_b = re.sub(r"[_\-]", " ", desc_b).strip().lower()
        if norm_a in norm_b or norm_b in norm_a:
            return True
        return False

    def _build_excluded_selectors(
        self,
        action: str,
        description: str,
        previous_selector: str | None,
        previous_description: str | None,
        pages_data: dict[str, list[dict[str, str]]],
    ) -> set[str]:
        """Build a set of selectors to exclude for this resolution (B-014).

        For ASSERT: excludes the previous step's selector unless descriptions match.
        For CLICK/FILL: returns empty set.
        """
        if action != "ASSERT" or not previous_selector:
            return set()

        if previous_description and self._descriptions_reference_same_element(previous_description, description):
            return set()

        excluded: set[str] = {previous_selector}
        for elements in pages_data.values():
            for element in elements:
                raw_selector = str(element.get("selector", "")).strip()
                robust = build_robust_locator(element)
                if (robust and robust == previous_selector) or raw_selector == previous_selector:
                    if robust:
                        excluded.add(robust)
                    if raw_selector:
                        excluded.add(raw_selector)

        return excluded

    def _verify_page_context(
        self,
        description: str,
        matched_element: dict[str, str],
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> bool:
        """Verify the resolved locator exists on the current page (B3: page-context validation)."""
        if current_url is None:
            return True

        current_elements = scraped_data.get(current_url, [])
        element_selector = str(matched_element.get("selector", "")).strip()
        if not element_selector:
            return True

        for elem in current_elements:
            if str(elem.get("selector", "")).strip() == element_selector:
                return True

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

    def _build_candidate_urls(
        self,
        seed_urls: list[str],
        page_requirements: list[PageRequirement],
        journeys: list[TestJourney],
        user_story: str,
        conditions: str,
    ) -> list[str]:
        """Return a tightly-scoped list of URLs needed for the current journeys."""
        keywords = [page_requirement.keyword for page_requirement in page_requirements]
        placeholder_descriptions = [
            placeholder.description for journey in journeys for placeholder in journey.placeholders
        ]
        concepts = extract_route_concepts([user_story, conditions, *placeholder_descriptions, *keywords])
        return list(dict.fromkeys(seed_urls + build_common_path_candidates(seed_urls, concepts)))

    # ═════════════════════════════════════════════════════════════
    # Page selection
    # ═════════════════════════════════════════════════════════════

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

    # ═════════════════════════════════════════════════════════════
    # Utility
    # ═════════════════════════════════════════════════════════════

    @staticmethod
    def _extract_fill_text(line: str) -> str | None:
        """Extract the second argument from an evidence_tracker.fill() call."""
        match = re.search(r"fill\(.+?,\s*['\"](.+?)['\"]\)", line)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _all_placeholder_uses(code: str) -> list:
        """Parse all placeholder uses from code (delegate to SkeletonParser)."""
        from src.skeleton_parser import SkeletonParser

        parser = SkeletonParser()
        return parser.parse_placeholder_uses(code)

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

    # ═════════════════════════════════════════════════════════════
    # Backward-compat wrappers (delegate to extracted modules)
    # ═════════════════════════════════════════════════════════════

    # Role mapping wrappers
    def _normalise_element_text(self, element: dict[str, str]) -> str:
        return normalise_element_text(element)

    def _get_effective_role(self, element: dict[str, str]) -> str:
        return get_effective_role(element)

    def _is_display_role(self, element: dict[str, str]) -> bool:
        return is_display_role(element)

    # Element matcher wrappers
    def _pass1_assert_text_match(
        self, action: str, description: str, pages_data: dict[str, list[dict[str, str]]]
    ) -> dict[str, str] | None:
        return self._element_matcher.pass1_assert_text_match(action, description, pages_data)

    def _pass2_structural_match(
        self, action: str, description: str, pages_data: dict[str, list[dict[str, str]]]
    ) -> dict[str, str] | None:
        return self._element_matcher.pass2_structural_match(action, description, pages_data)

    # POM helper wrappers
    def _build_pom_url_map(self, page_objects: list[GeneratedPageObject]) -> dict[str, GeneratedPageObject]:
        return build_pom_url_map(page_objects)

    def _build_pom_imports(self, page_objects: list[GeneratedPageObject]) -> list[str]:
        return build_pom_imports(page_objects)

    def _build_pom_instantiation(
        self, page_objects: list[GeneratedPageObject], *, use_evidence_tracker: bool = True
    ) -> list[str]:
        return build_pom_instantiation(page_objects, use_evidence_tracker=use_evidence_tracker)

    def _get_pom_instance_name(self, url: str | None, page_objects: list[GeneratedPageObject]) -> str | None:
        return get_pom_instance_name(url, page_objects)

    def _get_pom_method_call(
        self,
        action: str,
        description: str,
        resolved_selector: str,
        pom_instance_name: str,
        fill_value: str = "",
    ) -> str | None:
        if not self._pom_mode:
            return None
        return get_pom_method_call(action, description, resolved_selector, pom_instance_name, fill_value)
