"""Placeholder resolution orchestration extracted from TestOrchestrator.

Element matching (passes 0-3, B-020 semantic ASSERT) delegated to
``element_matcher.ElementMatcher``. POM helpers to ``pom_helpers``.
Skip insertion to ``skip_manager``. Role mapping to ``role_mapper``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

if TYPE_CHECKING:
    from src.rag_retriever import RAGRetriever

from src.cart_seeding_scraper import CartSeedingScraper
from src.code_postprocessor import replace_token_in_line
from src.element_matcher import ElementMatcher
from src.journey_models import CredentialProfile, ObservedStep, ObservedTrail
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
from src.rag_learn import domain_from_url, site_hash
from src.role_mapper import (
    get_effective_role,
    is_display_role,
    normalise_element_text,
)
from src.scraper import PageScraper
from src.section_scoper import scope_elements
from src.semantic_candidate_ranker import (
    DEFAULT_RESOLUTION_TIMEOUT,
    AsyncGeneratorLike,
    SemanticCandidateRanker,
)
from src.skip_manager import (
    insert_consolidated_skips,
    remove_old_placeholder_skips,
    remove_raw_placeholder_lines,
)
from src.stateful_scraper import StatefulPageScraper
from src.url_inference import infer_next_page_url
from src.url_resolver import UrlResolver, normalize_url
from src.url_utils import (
    build_common_path_candidates,
    extract_route_concepts,
    heuristic_url_from_description,
    is_stateful_cart_checkout_path,
)

logger = logging.getLogger(__name__)


#: Negative-state ASSERT descriptions assert the ABSENCE of an element — the
#: state after a popup closes / an item is removed / something disappears.
#: These resolve to ``toBeHidden`` (Playwright's ``to_be_hidden()`` passes for
#: hidden OR detached nodes). Generic vocabulary, no site-specific lists.
POLARITY_TERMS: tuple[str, ...] = (
    "closed",
    "gone",
    "disappeared",
    "disappears",
    "removed",
    "hidden",
    "dismissed",
    "vanished",
    "no longer",
    "not visible",
    "not shown",
)


def polarity_assertion_type(description: str) -> str | None:
    """Return ``"toBeHidden"`` for negative-state ASSERT descriptions, else None.

    "popup closed" / "item removed" assert the ABSENCE of the element, so the
    emitted assertion must be ``assert_hidden(...)`` — not ``assert_visible``.
    """
    lowered = description.replace("_", " ").lower()
    if any(term in lowered for term in POLARITY_TERMS):
        return "toBeHidden"
    return None


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
        flow_store: Any | None = None,
        *,
        resolution_timeout: float = DEFAULT_RESOLUTION_TIMEOUT,
        enable_thinking: bool | None = False,
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
            flow_store: AI-042 cross-site flow memory store. When ``None``, flow
                resolution is disabled (zero overhead).
            resolution_timeout: Hard limit (seconds) for each resolution LLM call.
            enable_thinking: Thinking-mode switch for the resolution ranker
                (default ``False`` — proven stable for structured pick-from-
                candidates). ``None`` sends nothing (model default). A
                thinking-ON leg passes ``True`` explicitly.
        """
        self._starting_url = starting_url
        self._credential_profile = credential_profile
        self._pom_mode = pom_mode
        self._flow_store = flow_store
        self.resolver = PlaceholderResolver()
        self.scraper = PageScraper()
        self.url_resolver = UrlResolver()
        self._element_matcher = ElementMatcher(
            self.resolver, generator, resolution_timeout=resolution_timeout, enable_thinking=enable_thinking
        )
        self._generated_page_objects: list[GeneratedPageObject] = []
        self.page_object_builder = PageObjectBuilder()
        self.semantic_ranker = SemanticCandidateRanker(
            generator, timeout=resolution_timeout, enable_thinking=enable_thinking
        )
        self._rag_retriever = rag_retriever

    @property
    def pom_mode(self) -> bool:
        """Return whether POM-mode output is enabled."""
        return self._pom_mode

    # ═════════════════════════════════════════════════════════════
    # Scraping helpers
    # ═════════════════════════════════════════════════════════════

    @staticmethod
    def _drop_redirect_duplicates(
        scraped_data: dict[str, list[dict[str, Any]]],
        redirects: dict[str, str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Remove pages whose scrape redirected to, and duplicated, another page.

        Some sites answer unknown routes with HTTP 200 and a redirect to the
        home page (automationexercise /inventory.html, /basket). The bogus key
        then holds home content and can win ASSERT/keyword resolution over the
        real page. SPA pages that the stateful upgrade re-scraped with their own
        content are unaffected: their selectors differ from the redirect target.
        """
        for url, target in redirects.items():
            if url not in scraped_data or target not in scraped_data:
                continue
            own_selectors = {str(e.get("selector", "")) for e in scraped_data[url] if e.get("selector")}
            target_selectors = {str(e.get("selector", "")) for e in scraped_data[target] if e.get("selector")}
            if own_selectors and own_selectors <= target_selectors:
                logger.info("Dropping redirect duplicate '%s' → '%s'", url, target)
                del scraped_data[url]
        return scraped_data

    # HTTP error-page markers from stdlib servers (http.server.SimpleHTTPRequestHandler
    # and friends). Real pages never contain these strings; a page whose scraped text
    # is dominated by them is a 404 error page, not a live page. Site-agnostic —
    # covers any mock/live site served by a stdlib or similarly-worded server.
    _ERROR_PAGE_SIGNALS: tuple[str, ...] = (
        "error code: 404",
        "nothing matches the given uri",
        "file not found",
        "error response",
        "404 not found",
    )

    @staticmethod
    def _is_error_page(elements: list[dict[str, Any]]) -> bool:
        """True when scraped elements are an HTTP error page (404/500 body).

        The stateless/stateful scrapers fetch unknown routes before the
        resolver sees them (concept-driven candidate URLs). A stdlib 404 page
        scrapes to ~5 elements — above the dead-page element threshold — so its
        "Error code: 404" text can win keyword/ASSERT matching over the real
        page's content. Detect the error body by its distinctive markers.
        """
        if not elements:
            return False
        texts = " ".join(str(el.get("text", "")) for el in elements).lower()
        if not texts.strip():
            return False
        # Require at least two distinct markers to avoid false positives on a
        # real page that mentions "file not found" once in body copy.
        hits = sum(1 for signal in PlaceholderOrchestrator._ERROR_PAGE_SIGNALS if signal in texts)
        return hits >= 2

    @staticmethod
    def _drop_dead_pages(
        scraped_data: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Remove pages that scraped to a near-empty shell.

        SPA-hosted sites (saucedemo on GitHub Pages) answer every non-existent
        path with a 2-element 404/app shell; auth-gated redirects render a
        login stub. Such dead pages pollute keyword/navigation resolution —
        e.g. ``/basket`` (2 elements) can out-rank ``/cart.html`` (34 elements)
        in first-match substring logic. Real pages scrape far richer content,
        so a minimal-element threshold is a safe, site-agnostic signal.

        Also drops HTTP error pages (stdlib 404 bodies) whose element count is
        above the threshold but whose content is entirely error text — these
        are concept-candidate URLs that 404ed (B-045 banking-mock surface).
        """
        MIN_LIVE_ELEMENTS = 3
        dead = [url for url, elements in scraped_data.items() if len(elements) < MIN_LIVE_ELEMENTS]
        for url in dead:
            logger.info(
                "Dropping dead page '%s' (%d elements)",
                url,
                len(scraped_data[url]),
            )
            del scraped_data[url]
        # Error-page content drop: catches 404 bodies that pass the element
        # threshold (stdlib error pages scrape to ~5 elements).
        error_pages = [
            url for url, elements in scraped_data.items() if PlaceholderOrchestrator._is_error_page(elements)
        ]
        for url in error_pages:
            logger.info(
                "Dropping error page '%s' (%d elements, HTTP error markers)",
                url,
                len(scraped_data[url]),
            )
            del scraped_data[url]
        return scraped_data

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
        is_stateful_target = is_stateful_cart_checkout_path(parsed.path)
        if is_stateful_target and self._starting_url:
            stateful_scraper = StatefulPageScraper(self._starting_url, credential_profile=self._credential_profile)
            elements = await stateful_scraper.scrape_url(url)
            scraped_data[url] = elements
            if elements:
                return

        elements, error, _final_url = await self.scraper.scrape_url(url)
        # Skip near-empty SPA 404/login-wall shells — they add noise to
        # keyword and navigation resolution, never resolution value.
        if len(elements) < 3:
            if scraped_errors is not None:
                scraped_errors[url] = error or f"Only {len(elements)} element(s) — dead page shell"
            return
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
            if is_stateful_cart_checkout_path(path):
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

            cart_scraper = CartSeedingScraper(
                self._starting_url,
                products_url=products_url,
                credential_profile=self._credential_profile,
            )
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
                    if is_stateful_cart_checkout_path(candidate_path):
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
            if is_stateful_cart_checkout_path(path):
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

        return self._drop_dead_pages(upgraded)

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
        observed_trails: dict[str, ObservedTrail] | None = None,
    ) -> str:
        """Resolve placeholders step by step while tracking the active page for each test."""
        duplicate_selectors = self._get_duplicate_selectors(scraped_data)
        lines = skeleton_code.splitlines()
        line_resolutions: dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]] = {}
        all_placeholder_uses = self._all_placeholder_uses(skeleton_code)
        fallback_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)
        errors = scraped_errors or {}

        observed_trails = observed_trails or {}
        journey_unresolved: dict[str, list[str]] = {}
        # AI-052: tokens skipped under strict scope must never reach the
        # all-pages batch fallback below — that would resurrect exactly the
        # cross-page locator this fix removes.
        strict_skipped_tokens: set[str] = set()

        # 1. Resolve placeholders inside test functions
        for journey in journeys:
            # AI-052 (S2): log the factual trail under PIPELINE_DEBUG (stderr —
            # Python logging is not configured by the Streamlit app).
            # AI-052 (S3): CONSUME it — each step's page is derived from the
            # observation instead of infer_next_page_url's guess.
            trail = observed_trails.get(journey.test_name)
            trail_steps: list[ObservedStep] = trail.steps if trail else []
            if trail_steps:
                trail_urls = " -> ".join(dict.fromkeys(s.to_url for s in trail_steps if s.to_url))
                if os.getenv("PIPELINE_DEBUG", "").strip() == "1":
                    print(f"[resolve] {journey.test_name} observed trail: [{trail_urls}]", flush=True, file=sys.stderr)
            trail_by_token = self._map_trail_to_placeholders(journey, trail_steps)
            # Canonicaliser: trail URLs come straight from page.url (trailing
            # slashes etc.) while scraped_data keys are normalised — resolve
            # every membership check through this map.
            norm_scraped = {normalize_url(k): k for k in scraped_data}

            def canon(url: str | None, _map: dict[str, str] = norm_scraped) -> str | None:
                """Return the actual scraped_data key for url, else None."""
                if not url:
                    return None
                return _map.get(normalize_url(url))

            current_url = self._select_initial_page_url(
                journey,
                page_requirements,
                seed_urls,
                scraped_data,
                lines,
            )
            initial_key = canon(current_url)
            if initial_key:
                current_url = initial_key
            # Anchor for evidenced/unknown steps (AI-052): the last page we have
            # scraped DOM for. Resolution scope never leaves verified pages.
            last_verified_url = initial_key
            # AI-052: set when WE emit a CLICK whose real href targets an
            # unscraped page — the runtime browser will land there, so the next
            # step cannot honestly resolve against the stale verified page.
            pending_evidence: str | None = None
            # AI-052: latches True once OUR emitted path departs from the
            # observed one (href navigation / proven-static override). From
            # then on the trail describes a different journey than the
            # generated test — only our own verified anchor is trustworthy.
            diverged = False
            journey_unresolved[journey.test_name] = []

            last_selector: str | None = None
            last_description: str | None = None
            resolved_steps: list[str] = []
            deferred_asserts: list[dict[str, Any]] = []

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

                    # ── AI-052 S3: observation over inference ──────────────
                    # Where is this step's page? Ask the trail (a browser
                    # fact), not a guesser.
                    obs = trail_by_token.get(placeholder.token)
                    if trail_steps:
                        if pending_evidence:
                            # We emitted a navigation click to an unscraped page
                            # (real href). The scraper followed a different
                            # element, so the trail cannot vouch for this step:
                            # the runtime browser will be on the href target,
                            # which has no scraped DOM → honest skip below.
                            current_url = pending_evidence
                            pending_evidence = None
                        elif diverged:
                            # The trail no longer describes this test's path —
                            # trust only our own verified anchor.
                            if last_verified_url:
                                current_url = last_verified_url
                        else:
                            scoped = self._trail_step_scope_url(obs, canon, last_verified_url)
                            if scoped:
                                current_url = scoped
                                last_verified_url = scoped

                    if action == "GOTO" and obs is not None and obs.to_url:
                        # The scraper already made this exact navigation — use
                        # where it actually landed instead of re-resolving the
                        # URL from keywords/href guessing.
                        observed_target = normalize_url(obs.to_url)
                        line_resolutions.setdefault(placeholder.line_number, []).append(
                            (
                                placeholder.token,
                                action,
                                repr(observed_target),
                                description,
                                fill_value,
                                current_url,
                                None,
                            )
                        )
                        target_key = canon(obs.to_url)
                        if target_key:
                            current_url = target_key
                            last_verified_url = target_key
                            pending_evidence = None
                        else:
                            pending_evidence = obs.to_url
                        continue

                    # AI-052: replay the scraper's PROVEN selector — see the
                    # divergence-aware block after _resolve_placeholder_for_page.

                    if action == "ASSERT":
                        # B-021: Page-state assertions become URL assertions —
                        # resolve immediately (no element matching or LLM needed).
                        if self._is_page_state_assertion(description):
                            resolved_url = self.resolver.resolve_url(
                                description,
                                scraped_data,
                                known_urls=list(scraped_data.keys()),
                            )
                            # Post-login assertions ("logged in", "login
                            # successful") must resolve to the page AFTER auth —
                            # the products/inventory page, not the login page.
                            if resolved_url and any(
                                t in description.lower()
                                for t in ("logged", "login success", "successful login", "authenticated")
                            ):
                                for candidate in ("inventory", "products"):
                                    for url in scraped_data:
                                        if candidate in url.lower():
                                            resolved_url = url
                                            break
                                    else:
                                        continue
                                    break
                            # AI-051: the trail is the source of truth for where
                            # the preceding action landed. When it evidences the
                            # step's page DIFFERS from the one this assertion was
                            # scoped to (e.g. a Login CLICK navigates
                            # home -> /inventory.html, but /inventory.html was
                            # never scraped, so keyword resolution above fell back
                            # to the base URL), assert the OBSERVED landing URL —
                            # a browser fact — not the keyword-inferred one.
                            if (
                                resolved_url
                                and obs is not None
                                and not diverged
                                and pending_evidence is None
                                and obs.to_url
                            ):
                                landing_key = canon(obs.to_url)
                                if landing_key is not None and normalize_url(landing_key) != normalize_url(
                                    resolved_url
                                ):
                                    logger.info(
                                        "AI-051: page-state assert '%s' — asserting observed landing %s (trail to_url), not keyword-inferred %s",
                                        description,
                                        landing_key,
                                        resolved_url,
                                    )
                                    resolved_url = landing_key
                            if resolved_url:
                                resolved_url = normalize_url(resolved_url)
                                line_resolutions.setdefault(placeholder.line_number, []).append(
                                    (
                                        placeholder.token,
                                        action,
                                        f'expect(page).to_have_url("{resolved_url}")',
                                        description,
                                        fill_value,
                                        current_url,
                                        "url",
                                    )
                                )
                                continue
                            # AI-042: flow-memory fallback for page-state asserts —
                            # learned cross-site navigation shape can rescue the
                            # URL when site-specific resolution finds nothing
                            # (mirrors the same fallback in
                            # ``_resolve_placeholder_for_current_page``).
                            if self._flow_store is not None and current_url:
                                from src.flow_memory import flow_resolved_url

                                flow_url = flow_resolved_url(
                                    self._flow_store,
                                    description=description,
                                    from_url=current_url,
                                    scraped_urls=list(scraped_data.keys()) if isinstance(scraped_data, dict) else [],
                                )
                                if flow_url:
                                    flow_url = normalize_url(flow_url)
                                    logger.info("Flow memory resolved URL assertion '%s' → %s", description, flow_url)
                                    line_resolutions.setdefault(placeholder.line_number, []).append(
                                        (
                                            placeholder.token,
                                            action,
                                            f'expect(page).to_have_url("{flow_url}")',
                                            description,
                                            fill_value,
                                            current_url,
                                            "url",
                                        )
                                    )
                                    continue
                        # Defer element-based ASSERT for batch resolution.
                        deferred_asserts.append(
                            {
                                "placeholder": placeholder,
                                "action": action,
                                "description": description,
                                "fill_value": fill_value,
                                "current_url": current_url,
                                "previous_selector": last_selector,
                                "previous_description": last_description,
                            }
                        )
                        continue

                    matched_box: dict[str, Any] = {}
                    resolved_value, next_url, assertion_type = await self._resolve_placeholder_for_page(
                        action=action,
                        description=description,
                        current_url=current_url,
                        scraped_data=scraped_data,
                        scraped_errors=errors,
                        previous_selector=last_selector,
                        previous_description=last_description,
                        resolved_steps=resolved_steps,
                        strict_scope=bool(trail_steps),
                        matched_out=matched_box,
                    )

                    # ── AI-052: divergence-aware replay ────────────────────
                    # The trail's selector_used was PROVEN (successfully clicked
                    # during discovery, error is None). When the resolver picks
                    # a DIFFERENT element:
                    #   • ours navigates via a real href → keep ours (the href
                    #     is evidence; pending_evidence/anchor handle the move);
                    #   • ours has no href (navigation behaviour unknowable —
                    #     e.g. JS-driven links) → replay the PROVEN selector so
                    #     the generated test re-enacts the observed journey;
                    #   • ours found nothing scoped → fall back to the proven
                    #     selector instead of skipping.
                    if (
                        trail_steps
                        and not diverged
                        and action == "CLICK"
                        and obs is not None
                        and obs.error is None
                        and obs.selector_used
                    ):
                        ours = matched_box.get("element")
                        if ours is None:
                            if "pytest.skip" in resolved_value:
                                resolved_value = repr(obs.selector_used)
                                next_url = None
                        else:
                            raw_sel = str(ours.get("selector", "")).strip()
                            robust_sel = build_robust_locator(ours) or raw_sel
                            if obs.selector_used not in {raw_sel, robust_sel} and not next_url:
                                # No href on our pick: we cannot know whether it
                                # navigates. The proven element's behaviour is
                                # recorded in the trail — follow it.
                                resolved_value = repr(obs.selector_used)
                                next_url = None
                                if action != "ASSERT":
                                    assertion_type = None

                    # AI-052: the trail PROVES whether the proven click navigated.
                    # A navigation-intent click that provably stayed put (and our
                    # own pick has no href either) is better emitted as a
                    # navigation to a verified page than as a dead click.
                    proven_static = (
                        trail_steps
                        and not diverged
                        and action == "CLICK"
                        and obs is not None
                        and obs.error is None
                        and not obs.navigated
                        and not next_url
                    )

                    if "pytest.skip" in resolved_value or proven_static:
                        # Navigation-intent fallback: SPA sites render cart/basket
                        # icons without accessible names, so element matching can't
                        # resolve "cart icon"/"cart link". Navigate to the verified
                        # page URL instead of skipping — keeps the page context
                        # advancing through cart → checkout.
                        if action in {"CLICK", "GOTO"} and self._is_navigation_description(description):
                            nav_resolved, nav_next, nav_at = await self._resolve_placeholder_for_page(
                                action="GOTO",
                                description=description,
                                current_url=current_url,
                                scraped_data=scraped_data,
                                scraped_errors=errors,
                                previous_selector=last_selector,
                                previous_description=last_description,
                                resolved_steps=resolved_steps,
                                strict_scope=bool(trail_steps),
                            )
                            if "pytest.skip" not in nav_resolved:
                                resolved_value = nav_resolved
                                next_url = nav_next
                                assertion_type = nav_at
                                action = "GOTO"

                    if "pytest.skip" in resolved_value and trail_steps:
                        # AI-052: under strict scope a skip stays a skip.
                        strict_skipped_tokens.add(placeholder.token)
                        if obs is None or not canon(obs.to_url):
                            # Evidenced/unknown page: skip WITH the honest reason,
                            # recorded inline so it survives to the generated test.
                            resolved_value = (
                                f"pytest.skip(\"next page '{description}' not in scrape inventory "
                                f'- journey did not reach it")'
                            )
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
                            continue
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

                    if trail_steps:
                        # AI-052: advance the verified anchor on OBSERVED,
                        # scraped landings (fact) — never on inferred URLs.
                        if obs is not None and not diverged:
                            landed = canon(obs.to_url)
                            if landed:
                                last_verified_url = landed
                        if next_url and not canon(next_url):
                            # Real href emitted to an unscraped page — the next
                            # step runs (if at all) on that page.
                            pending_evidence = next_url
                            diverged = True
                        elif next_url:
                            # Navigation to a KNOWN page — a verified fact.
                            landed = canon(next_url)
                            if landed:
                                last_verified_url = landed
                                if obs is None or canon(obs.to_url) != landed:
                                    diverged = True
                    elif next_url:
                        current_url = next_url

            # Batch-resolve deferred ASSERT placeholders for this journey
            if deferred_asserts:
                await self._batch_resolve_deferred_asserts(
                    deferred_asserts=deferred_asserts,
                    scraped_data=scraped_data,
                    scraped_errors=errors,
                    fallback_url=fallback_url,
                    line_resolutions=line_resolutions,
                    journey_unresolved=journey_unresolved,
                    journey_name=journey.test_name,
                    strict_scope=bool(trail_steps),
                )

        # 2. Resolve remaining placeholders using fallback context (batched Pass 3)
        resolved_tokens = {
            token
            for replacements in line_resolutions.values()
            for token, _action, _resolved_value, _description, _fill, _url, _at in replacements
        }

        # Collect element-based unresolved placeholders for batch resolution
        batch_requests: list[dict[str, str]] = []
        batch_uses: list[Any] = []

        for use in all_placeholder_uses:
            if use.token in resolved_tokens:
                continue
            if use.token in strict_skipped_tokens:
                continue
            if use.action in ("GOTO", "URL"):
                # GOTO/URL are URL resolution — handle per-use
                continue
            batch_requests.append({"action": use.action, "description": use.description})
            batch_uses.append(use)

        if batch_requests:
            await self._ensure_scraped(fallback_url, scraped_data, scraped_errors)
            # B-028 follow-up: the batch fallback is the LAST chance for leftover
            # placeholders — search ALL scraped pages, not just the fallback URL.
            # Scoping to fallback_url left 'Proceed To Checkout' unresolved even
            # though view_cart was scraped with the checkout button present.
            # (Per-journey resolution stays scoped for precision/speed; the
            # batch pass only runs when placeholders remain unresolved.)
            pages_to_search = scraped_data
            batch_results = await self._element_matcher.find_best_elements_batch(
                requests=batch_requests,
                current_url=fallback_url,
                pages_data=pages_to_search,
            )

            for i, use in enumerate(batch_uses):
                matched = batch_results[i] if i < len(batch_results) else None
                fill_value = ""
                action = use.action
                description = use.description
                if action == "FILL" and ":" in description:
                    parts = description.split(":", 1)
                    description = parts[0]
                    fill_value = parts[1]

                if matched is not None:
                    selector = matched.get("selector", "")
                    at = matched.get("assertion_type")
                    resolved_value = repr(selector) if selector else f'pytest.skip("No match for: {description}")'
                    line_resolutions.setdefault(use.line_number, []).append(
                        (use.token, action, resolved_value, description, fill_value, fallback_url, at)
                    )
                else:
                    journey_name = self._find_journey_for_line(use.line_number, journeys)
                    if journey_name:
                        journey_unresolved.setdefault(journey_name, []).append(description)

        # Handle GOTO/URL placeholders individually
        for use in all_placeholder_uses:
            if use.token in resolved_tokens:
                continue
            if use.action not in ("GOTO", "URL"):
                continue  # already handled in batch above

            fill_value = ""
            action = use.action
            description = use.description
            if action == "FILL" and ":" in description:
                parts = description.split(":", 1)
                description = parts[0]
                fill_value = parts[1]

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

    async def _batch_resolve_deferred_asserts(
        self,
        deferred_asserts: list[dict[str, Any]],
        scraped_data: dict[str, list[dict[str, str]]],
        scraped_errors: dict[str, str] | None,
        fallback_url: str | None,
        line_resolutions: dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]],
        journey_unresolved: dict[str, list[str]],
        journey_name: str,
        strict_scope: bool = False,
    ) -> None:
        """Batch-resolve deferred ASSERT placeholders grouped by page URL.

        ASSERT placeholders are independent — they don't update sequential state
        (last_selector, current_url, resolved_steps). By deferring them and
        batching Pass 3 LLM calls, we avoid N individual LLM calls.
        """
        # Group by current_url
        by_url: dict[str, list[dict[str, Any]]] = {}
        for da in deferred_asserts:
            url = da["current_url"] or fallback_url or ""
            by_url.setdefault(url, []).append(da)

        for url, group in by_url.items():
            await self._ensure_scraped(url, scraped_data, scraped_errors)
            pages_data = self._build_scoped_pages(url, scraped_data)
            if not pages_data and strict_scope:
                # AI-052: the recorded page is not in the scrape inventory —
                # these asserts are unverifiable → honest unresolved, never an
                # all-pages cross-page match.
                for da in group:
                    journey_unresolved.setdefault(journey_name, []).append(da["description"])
                continue
            pages_to_search = pages_data if pages_data else scraped_data

            # Build excluded selectors from the last CLICK/FILL step in the journey.
            # All ASSERTs share the same previous_selector (last interactive action).
            excluded: set[str] | None = None
            for da in group:
                if da["previous_selector"]:
                    excluded = {da["previous_selector"]}
                    for elements in pages_to_search.values():
                        for element in elements:
                            robust = build_robust_locator(element)
                            raw = str(element.get("selector", "")).strip()
                            if robust == da["previous_selector"] or raw == da["previous_selector"]:
                                if robust:
                                    excluded.add(robust)
                                if raw:
                                    excluded.add(raw)
                    break

            batch_requests: list[dict[str, str]] = [
                {"action": da["action"], "description": da["description"]} for da in group
            ]

            batch_results = await self._element_matcher.find_best_elements_batch(
                requests=batch_requests,
                current_url=url,
                pages_data=pages_to_search,
                excluded_selectors=excluded,
            )

            for i, da in enumerate(group):
                placeholder = da["placeholder"]
                action = da["action"]
                description = da["description"]
                fill_value = da["fill_value"]

                matched = batch_results[i] if i < len(batch_results) else None

                if matched is not None:
                    robust_selector = build_robust_locator(matched)
                    if not robust_selector:
                        robust_selector = str(matched.get("selector", "")).strip()
                    selector = repr(robust_selector)
                    assertion_type = matched.get("assertion_type")
                    if action == "ASSERT":
                        assertion_type = polarity_assertion_type(description) or assertion_type

                    line_resolutions.setdefault(placeholder.line_number, []).append(
                        (
                            placeholder.token,
                            action,
                            selector,
                            description,
                            fill_value,
                            url,
                            assertion_type,
                        )
                    )
                else:
                    journey_unresolved.setdefault(journey_name, []).append(description)

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
        strict_scope: bool = False,
        matched_out: dict[str, Any] | None = None,
    ) -> tuple[str, str | None, str | None]:
        """Resolve one placeholder using the active page first, then fall back to known pages.

        Args:
            previous_selector: The selector resolved by the previous interactive step.
            previous_description: The description from the previous interactive step
                (B-014 step-context exclusion).
            resolved_steps: B-020 list of compressed step descriptions for LLM context.
            strict_scope: AI-052 — when True (journeys with an observed trail), NEVER
                fall back to searching all scraped pages. An empty verified scope means
                no evidence for the element → honest skip instead of a cross-page locator.
            matched_out: AI-052 — optional dict; when provided, receives the matched
                element under key ``"element"`` so callers can compare their own
                choice against the trail's proven selector.
        """
        await self._ensure_scraped(current_url, scraped_data, scraped_errors)
        scoped_pages = self._build_scoped_pages(current_url, scraped_data)

        if action in {"GOTO", "URL"}:
            # Step 1: Try UrlResolver
            url_from_resolver = self.url_resolver.resolve(description)
            if url_from_resolver:
                url_from_resolver = normalize_url(url_from_resolver)
                logger.debug("UrlResolver matched '%s' -> %s", description, url_from_resolver)
                return repr(url_from_resolver), url_from_resolver, None

            # Step 2: Try PlaceholderResolver — GOTO navigates anywhere, so
            # search ALL verified pages, not just the current page's scope.
            resolved_url = self.resolver.resolve_url(description, scraped_data)
            if resolved_url:
                resolved_url = normalize_url(resolved_url)
                return repr(resolved_url), resolved_url, None

            # Step 2.5 (AI-042): cross-site flow memory — learned navigation
            # shape rescues otherwise-unresolvable GOTO/URL assertions. Runs
            # after all site-specific resolution (UrlResolver / resolve_url)
            # so flow memory only fills gaps, never overrides site evidence.
            if self._flow_store is not None and current_url:
                from src.flow_memory import flow_resolved_url

                flow_url = flow_resolved_url(
                    self._flow_store,
                    description=description,
                    from_url=current_url,
                    scraped_urls=list(scraped_data.keys()) if isinstance(scraped_data, dict) else [],
                )
                if flow_url:
                    flow_url = normalize_url(flow_url)
                    await self._ensure_scraped(flow_url, scraped_data, scraped_errors)
                    logger.info("Flow memory resolved '%s' → %s (from %s)", description, flow_url, current_url)
                    return repr(flow_url), flow_url, None

            # Step 3: Heuristic fallback
            if current_url:
                heuristic = heuristic_url_from_description(current_url, description)
                if heuristic:
                    heuristic = normalize_url(heuristic)
                    await self._ensure_scraped(heuristic, scraped_data, scraped_errors)
                    return repr(heuristic), heuristic, None

            # Step 4: Try seed URL as last resort
            seed_url = self.url_resolver.get_seed_url()
            if seed_url:
                seed_url = normalize_url(seed_url)
                logger.debug("Falling back to seed URL for '%s': %s", description, seed_url)
                return repr(seed_url), seed_url, None

            error_msg = f"Locator for '{description}' not found on scraped pages."
            if current_url and scraped_errors and current_url in scraped_errors:
                error_msg += f" (Note: scraping {current_url} failed with {scraped_errors[current_url]})"
            return f'pytest.skip("{error_msg}")', None, None

        if scoped_pages:
            pages_to_search = scoped_pages
        elif strict_scope:
            # AI-052: collecting candidates from ALL pages is exactly how a
            # cross-page locator wins (the bug). With an observed trail we know
            # which page the browser was on; if the element isn't evidenced
            # there, skip honestly — never emit a locator for another page.
            error_msg = f"Locator for '{description}' not found on '{current_url}' - page not in scrape inventory."
            print(f"[DEBUG] Strict scope miss: '{description}' (current={current_url})")
            return f'pytest.skip("{error_msg}")', None, None
        else:
            pages_to_search = scraped_data

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
                resolved_url = normalize_url(resolved_url)
                logger.info("URL assertion resolved '%s' → %s", description, resolved_url)
                return f'expect(page).to_have_url("{resolved_url}")', None, "url"
            # AI-042: cross-site flow memory — page-state asserts share GOTO
            # intent; learned navigation shape can rescue the URL when
            # site-specific DOM resolution finds nothing.
            if self._flow_store is not None and current_url:
                from src.flow_memory import flow_resolved_url

                flow_url = flow_resolved_url(
                    self._flow_store,
                    description=description,
                    from_url=current_url,
                    scraped_urls=list(scraped_data.keys()) if isinstance(scraped_data, dict) else [],
                )
                if flow_url:
                    flow_url = normalize_url(flow_url)
                    logger.info("Flow memory resolved URL assertion '%s' → %s", description, flow_url)
                    return f'expect(page).to_have_url("{flow_url}")', None, "url"
            logger.debug("URL assertion failed for '%s' — falling through to element resolution", description)

        excluded = self._build_excluded_selectors(
            action, description, previous_selector, previous_description, pages_to_search
        )

        # RAG retrieval: fetch golden patterns for scoring bonus
        golden_patterns = self._retrieve_golden_patterns(action, description)
        # AI-035 Phase 2: scope the learned-pattern bonus to this site.
        # AI-059 lab hardening: when a lab sentinel is set, use it as the site
        # identity instead of the URL-derived host:port hash. The sentinel is a
        # deterministic hash of a *structured* lab identity (site + input/edit
        # version + story set), so distinct experimental cells stay isolated
        # and reruns of the same cell are comparable. Prefer the identity
        # string (AI059_LAB_SITE_IDENTITY); a raw AI059_LAB_SITE_HASH is also
        # accepted for back-compat. Production runs leave both unset,
        # preserving the existing host:port scoping.
        site = None
        identity = os.environ.get("AI059_LAB_SITE_IDENTITY")
        if identity:
            site = site_hash(identity)
        elif os.environ.get("AI059_LAB_SITE_HASH"):
            site = os.environ["AI059_LAB_SITE_HASH"]
        if site is None and current_url:
            domain = domain_from_url(current_url)
            site = site_hash(domain) if domain else None

        matched_element = await self._element_matcher.find_best_element_for_current_page(
            action,
            description,
            current_url,
            pages_to_search,
            excluded_selectors=excluded or None,
            resolved_steps=resolved_steps,
            golden_patterns=golden_patterns or None,
            site_hash=site,
        )

        if matched_element is not None:
            if matched_out is not None:
                matched_out["element"] = matched_element
            self._verify_page_context(description, matched_element, current_url, scraped_data)

            robust_selector = build_robust_locator(matched_element)
            if not robust_selector:
                robust_selector = str(matched_element.get("selector", "")).strip()
            selector = repr(robust_selector)
            # AI-052: with an observed trail, element scoping must not depend on
            # URL inference at all — the trail drives transitions. The keyword
            # guesser also has a side effect here (_ensure_scraped of a guessed
            # URL), so skip it entirely under strict scope. It remains available
            # as a last-resort hint for non-trail callers until Session 4.
            next_url = None
            if strict_scope:
                # AI-052: evidence only — a real href on the matched element is
                # a fact about where the emitted click navigates. Keyword-based
                # inference stays out of strict scope (deleted in Session 4).
                next_url = self._emitted_navigation_target(matched_element, current_url)
            else:
                next_url = infer_next_page_url(action, description, matched_element, scraped_data, current_url)
                if next_url:
                    await self._ensure_scraped(next_url, scraped_data, scraped_errors)
            assertion_type = matched_element.get("assertion_type") if action == "ASSERT" else None
            # Assertion-state polarity: "popup closed" / "item removed" assert
            # ABSENCE — emit assert_hidden(...) instead of assert_visible(...).
            if action == "ASSERT":
                assertion_type = polarity_assertion_type(description) or assertion_type
            return selector, next_url, assertion_type

        error_msg = f"Locator for '{description}' not found on scraped pages."
        print(
            f"[DEBUG] Failed to find '{description}' (current={current_url}, "
            f"scope={list(pages_to_search.keys())}). Available scraped URLs: {list(scraped_data.keys())}"
        )
        return f'pytest.skip("{error_msg}")', None, None

    def _is_navigation_description(self, description: str) -> bool:
        """True when a description means navigating to a page, not clicking an element.

        SPA sites render cart/basket links as icon elements with no accessible
        name, so text matching can't resolve them. Descriptions like "cart
        icon", "cart link", "go to cart", "shopping cart" signal navigation
        intent and can fall back to a verified page URL. Action-verb
        descriptions ("add to cart", "remove item") are element clicks.
        """
        desc = description.lower()
        if any(verb in desc for verb in ("add", "remove", "delete", "place", "button")):
            return False
        # Cart/basket navigations are the target: "cart icon", "cart link",
        # "shopping cart", "view basket". "Checkout"/"Proceed To Checkout"
        # are button clicks on the cart page — element matching handles them.
        nav_terms = ("link", "icon", "go to", "open", "navigate", "view", "cart", "basket")
        page_targets = ("cart", "basket", "home", "products", "inventory", "login")
        return any(t in desc for t in nav_terms) and any(t in desc for t in page_targets)

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
        self._write_rag_diagnostic(action, description, patterns)
        return patterns if patterns else None

    @staticmethod
    def _write_rag_diagnostic(action: str, description: str, patterns: list[Any]) -> None:
        """Optionally append retrieval details for an AI-059 lab run.

        Diagnostics are opt-in and file-backed so production runs retain their
        existing behavior and cost. The lab runner sets the path per leg.
        """
        path_text = os.environ.get("AI059_RAG_DIAGNOSTICS_PATH", "").strip()
        if not path_text:
            return
        payload = {
            "action": action,
            "description": description,
            "results": [
                {
                    "description": str(getattr(pattern, "description", "")),
                    "selector": str(getattr(pattern, "selector", "")),
                    "action_type": str(getattr(pattern, "action_type", "")),
                    "confidence": float(getattr(pattern, "confidence", 0.0)),
                    "source": str(getattr(pattern, "source", "")),
                    "page": str(getattr(pattern, "page", "")),
                    "site_hash": str(getattr(pattern, "site_hash", "")),
                }
                for pattern in patterns
            ],
        }
        try:
            path = Path(path_text)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError, TypeError, ValueError:
            # Diagnostics must never affect resolution.
            return

    def _is_page_state_assertion(self, description: str) -> bool:
        """Check if an ASSERT description refers to a page state rather than an element.

        B-021: Returns True for descriptions like "home page visible",
        "dress products page", "cart page loaded" — these should be resolved
        as URL assertions (expect(page).to_have_url(...)).

        Only triggers when the description is PURELY about page state — if it
        mentions specific elements (heading, button, link, text, list, table,
        item, name, price, quantity, confirmation), it's an element
        assertion, not a page-state assertion.

        "title" is deliberately NOT an element keyword here: "<page> page
        title" means the title OF that page, which the golden dataset encodes
        as a URL assertion (eval-002 "products page title" / "cart page
        title" → to_have_url). Without this, an LLM-invented
        "{{ASSERT:home page title}}" for a load-style condition falls
        through to element resolution and matches the wrong element.
        "practice form page title" stays an element assertion — it contains
        no page-state term, so the page-state branch below never fires.
        """
        lowered = description.replace("_", " ").lower()

        # Element-level keywords — if present, this is an element assertion,
        # not a page-state assertion, even if page names are also mentioned.
        element_keywords = (
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
            "page loaded",
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
        """Return a page mapping scoped to the current journey URL when available.

        AI-052 contract: returns ``{}`` when ``current_url`` is not a verified
        (scraped) page — callers decide the fallback. Trail-driven callers
        (``strict_scope=True``) treat ``{}`` as honest-skip, never as licence to
        search every page.
        """
        if current_url and current_url in scraped_data:
            return {current_url: scraped_data[current_url]}
        return {}

    @staticmethod
    def _emitted_navigation_target(
        matched_element: dict[str, str],
        current_url: str | None,
    ) -> str | None:
        """Return the real-href navigation target of an emitted CLICK (AI-052).

        Evidence only: the element's own ``href``. Returns ``None`` for
        non-navigation elements (plain buttons, fragments, javascript:), and
        for hrefs that resolve back to the current page.
        """
        href = str(matched_element.get("href", "")).strip()
        if not href or href.startswith(("#", "javascript", "mailto", "tel")):
            return None
        if href.startswith(("http://", "https://")):
            target = href
        elif current_url:
            target = urljoin(current_url, href)
        else:
            return None
        if normalize_url(target.rstrip("/#")) == normalize_url((current_url or "").rstrip("/#")):
            return None
        return target

    @staticmethod
    def _trail_step_scope_url(
        obs: ObservedStep | None,
        canon: Any,
        last_verified_url: str | None,
    ) -> str | None:
        """Return the page a placeholder should resolve against (AI-052 three states).

        ``canon`` maps a raw URL to its actual scraped_data key (or None) —
        trail URLs come from page.url and may differ cosmetically (trailing
        slashes) from the normalised scrape keys.

        - **verified** — the observed step ran on a page we have DOM for →
          scope to it. An action runs on its FROM-page, never its landing page.
        - **step 0** — ``from_url`` is "" by construction; use the landing
          (to_url) page instead.
        - **evidenced / unknown** — no scraped DOM for this step's page → stay
          honest on the last verified page (caller skips if unresolvable there).
        """
        if obs is not None:
            if obs.from_url:
                actual = canon(obs.from_url)
                if actual:
                    return actual
            elif obs.to_url:
                # Step 0: no from-page recorded — the landing page is where
                # this action runs.
                actual = canon(obs.to_url)
                if actual:
                    return actual
        return last_verified_url

    @staticmethod
    def _map_trail_to_placeholders(
        journey: TestJourney,
        trail_steps: list[ObservedStep],
    ) -> dict[str, ObservedStep]:
        """Map skeleton placeholder tokens to their observed trail steps (AI-052 S3).

        The trail was captured from the SAME journey:
        ``_scrape_journeys_statefully`` flattens placeholders in the same order
        (GOTO→"navigate", CLICK/FILL→same, ASSERT→"scrape"). Exact index
        alignment cannot be assumed though — GOTOs that resolved to no URL
        produced no scraping step, and a trailing "final page state" scrape is
        appended — so placeholders are matched to trail steps by
        ``(action, description)`` with a monotonic cursor. Unmatched
        placeholders get no entry → treated as the "unknown" state.
        """
        action_map = {"GOTO": "navigate", "ASSERT": "scrape"}
        mapping: dict[str, ObservedStep] = {}
        cursor = 0
        for step in journey.steps:
            for placeholder in step.placeholders:
                expected_action = action_map.get(placeholder.action, placeholder.action.lower())
                for i in range(cursor, len(trail_steps)):
                    candidate = trail_steps[i]
                    if candidate.action == expected_action and candidate.description == placeholder.description:
                        mapping[placeholder.token] = candidate
                        cursor = i + 1
                        break
        return mapping

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
