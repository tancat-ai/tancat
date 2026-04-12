"""Primary intelligent generation pipeline for the Streamlit app."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney
from src.placeholder_resolver import PlaceholderResolver
from src.scraper import PageScraper
from src.semantic_candidate_ranker import SemanticCandidateRanker
from src.skeleton_parser import SkeletonParser
from src.test_generator import TestGenerator


@dataclass
class PipelineRunResult:
    """Captured metadata for the most recent pipeline run."""

    skeleton_code: str
    final_code: str
    pages_to_scrape: list[str]
    scraped_pages: dict[str, list[dict[str, str]]]
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
        self.page_object_builder = PageObjectBuilder()
        self.semantic_ranker = SemanticCandidateRanker(getattr(test_generator, "client", None))
        self.last_result: PipelineRunResult | None = None

    async def run_pipeline(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        consent_mode: str = "auto-dismiss",
    ) -> str:
        """Execute the full intelligent pipeline and return final code."""
        expected_test_count = self._count_conditions(conditions)
        prepared_conditions = self._prepare_conditions_for_generation(conditions)
        skeleton_code = await self.test_generator.generate_skeleton(
            user_story,
            prepared_conditions,
            target_urls=target_urls,
        )
        skeleton_error = self.parser.validate_skeleton(skeleton_code)
        if skeleton_error:
            raise ValueError(skeleton_error)

        placeholders = self.parser.parse_placeholders(skeleton_code)
        journeys = self.parser.parse_test_journeys(skeleton_code)
        if expected_test_count and len(journeys) != expected_test_count:
            retry_conditions = self._build_retry_conditions(prepared_conditions, expected_test_count)
            skeleton_code = await self.test_generator.generate_skeleton(
                user_story,
                retry_conditions,
                target_urls=target_urls,
            )
            skeleton_error = self.parser.validate_skeleton(skeleton_code)
            if skeleton_error:
                raise ValueError(skeleton_error)
            placeholders = self.parser.parse_placeholders(skeleton_code)
            journeys = self.parser.parse_test_journeys(skeleton_code)
            if len(journeys) != expected_test_count:
                raise ValueError(
                    "Skeleton output did not generate one test function per acceptance criterion. "
                    f"Expected {expected_test_count}, received {len(journeys)}."
                )

        page_requirements = self.parser.parse_page_requirements(skeleton_code)
        pages_to_scrape = self._build_candidate_urls(
            seed_urls=target_urls or [],
            page_requirements=page_requirements,
            journeys=journeys,
            user_story=user_story,
            conditions=conditions,
        )
        scraped_data = await self.scraper.scrape_all(pages_to_scrape) if pages_to_scrape else {}
        scraped_page_records = self._build_scraped_page_records(pages_to_scrape, scraped_data)
        generated_page_objects = self._build_page_object_artifacts(scraped_page_records)
        final_code = await self._replace_placeholders_sequentially(
            skeleton_code=skeleton_code,
            journeys=journeys,
            page_requirements=page_requirements,
            seed_urls=target_urls or [],
            scraped_data=scraped_data,
        )
        final_code = self._normalise_generated_code(final_code, consent_mode=consent_mode)
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
            page_requirements=page_requirements,
            journeys=journeys,
            scraped_page_records=scraped_page_records,
            generated_page_objects=generated_page_objects,
            unresolved_placeholders=unresolved,
        )
        return final_code

    @staticmethod
    def _count_conditions(conditions: str) -> int:
        """Return the number of non-empty condition lines."""
        return len([line.strip() for line in conditions.splitlines() if line.strip()])

    def _prepare_conditions_for_generation(self, conditions: str) -> str:
        """Return reinforced condition text that emphasizes one test per condition."""
        condition_lines = [line.strip() for line in conditions.splitlines() if line.strip()]
        normalized_lines: list[str] = []

        for index, line in enumerate(condition_lines, start=1):
            stripped_line = re.sub(r"^\d+[.)]\s*", "", line).strip()
            normalized_lines.append(f"{index}. {stripped_line}")

        total_count = len(normalized_lines)
        if total_count == 0:
            return conditions

        return (
            f"There are exactly {total_count} test conditions below.\n"
            f"Generate EXACTLY {total_count} pytest test functions.\n"
            "Generate ONE test function per condition.\n"
            "Do NOT combine multiple conditions into one test.\n"
            "Name the tests in order such as test_01_..., test_02_..., test_03_....\n\n" + "\n".join(normalized_lines)
        )

    @staticmethod
    def _build_retry_conditions(prepared_conditions: str, expected_test_count: int) -> str:
        """Return a stricter condition prompt for a one-time skeleton retry."""
        return (
            prepared_conditions
            + "\n\nCRITICAL CORRECTION:\n"
            + f"The previous answer did not produce exactly {expected_test_count} separate pytest test functions.\n"
            + "Regenerate the file with one test function per numbered condition and do not merge them."
        )

    @staticmethod
    def _build_scraped_page_records(
        pages_to_scrape: list[str],
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> list[ScrapedPage]:
        """Return typed scraped-page records in journey order."""
        scraped_page_records: list[ScrapedPage] = []

        for url in pages_to_scrape:
            elements = scraped_data.get(url, [])
            scraped_page_records.append(
                ScrapedPage(
                    url=url,
                    element_count=len(elements),
                    elements=elements,
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
    ) -> str:
        """Resolve placeholders step by step while tracking the active page for each test."""
        duplicate_selectors = self._get_duplicate_selectors(scraped_data)
        lines = skeleton_code.splitlines()
        line_resolutions: dict[int, list[tuple[str, str, str]]] = {}
        all_placeholder_uses = self.parser.parse_placeholder_uses(skeleton_code)
        fallback_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)

        for journey in journeys:
            current_url = self._select_initial_page_url(journey, page_requirements, seed_urls, scraped_data)

            for step in journey.steps:
                if current_url is None:
                    current_url = self._select_fallback_page_url(page_requirements, seed_urls, scraped_data)

                for placeholder in step.placeholders:
                    resolved_value, next_url = await self._resolve_placeholder_for_page(
                        placeholder.action,
                        placeholder.description,
                        current_url,
                        scraped_data,
                    )
                    line_resolutions.setdefault(placeholder.line_number, []).append(
                        (placeholder.token, placeholder.action, resolved_value)
                    )

                    if placeholder.action in {"GOTO", "URL"} and next_url:
                        current_url = next_url
                    elif placeholder.action == "CLICK" and next_url:
                        current_url = next_url

        resolved_tokens = {
            (line_number, token)
            for line_number, replacements in line_resolutions.items()
            for token, _action, _resolved_value in replacements
        }
        for placeholder in all_placeholder_uses:
            resolution_key = (placeholder.line_number, placeholder.token)
            if resolution_key in resolved_tokens:
                continue

            resolved_value, _next_url = await self._resolve_placeholder_for_page(
                placeholder.action,
                placeholder.description,
                fallback_url,
                scraped_data,
            )
            line_resolutions.setdefault(placeholder.line_number, []).append(
                (placeholder.token, placeholder.action, resolved_value)
            )

        final_lines: list[str] = []
        for line_number, line in enumerate(lines, start=1):
            updated_line = line
            for token, action, resolved_value in line_resolutions.get(line_number, []):
                updated_line = self._replace_token_in_line(
                    updated_line,
                    action,
                    token,
                    resolved_value,
                    duplicate_selectors,
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
    ) -> str:
        """Replace a single placeholder token within a code line."""
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        selector_value = resolved_value.strip("'\"")
        prefer_visible = action == "CLICK"
        prefer_first = action == "CLICK" and selector_value in duplicate_selectors

        if "pytest.skip" in resolved_value:
            return line.replace(token, resolved_value) if stripped != token else f"{indent}{resolved_value}"

        if action == "CLICK":
            selector_literal = resolved_value
            if prefer_visible and ":visible" not in selector_value:
                selector_literal = repr(f"{selector_value}:visible")
            if stripped == token:
                locator_expression = f"page.locator({selector_literal})"
                if prefer_first:
                    locator_expression += ".first"
                return f"{indent}{locator_expression}.click()"
            locator_only_patterns = (
                f"page.locator({token})",
                f"self.page.locator({token})",
            )
            if stripped in locator_only_patterns:
                replaced_line = line.replace(token, selector_literal)
                if prefer_first:
                    replaced_line = replaced_line.replace(
                        f"locator({selector_literal})",
                        f"locator({selector_literal}).first",
                    )
                return replaced_line + ".click()"
            replaced_line = line.replace(token, selector_literal)
            if prefer_first:
                replaced_line = replaced_line.replace(
                    f"locator({selector_literal})",
                    f"locator({selector_literal}).first",
                )
            return replaced_line

        if action == "ASSERT":
            if stripped == token:
                return f"{indent}expect(page.locator({resolved_value})).to_be_visible()"
            locator_only_patterns = (
                f"page.locator({token})",
                f"self.page.locator({token})",
            )
            if stripped in locator_only_patterns:
                page_ref = "self.page" if stripped.startswith("self.page") else "page"
                return f"{indent}expect({page_ref}.locator({resolved_value})).to_be_visible()"
            return line.replace(token, resolved_value)

        if action == "FILL":
            if stripped == token:
                return f'{indent}page.locator({resolved_value}).fill("")'
            locator_only_patterns = (
                f"page.locator({token})",
                f"self.page.locator({token})",
            )
            if stripped in locator_only_patterns:
                return line.replace(token, resolved_value) + '.fill("")'
            return line.replace(token, resolved_value)

        if action in {"GOTO", "URL"}:
            if stripped == token:
                return f"{indent}page.goto({resolved_value})"
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
        required_urls = [page_requirement.url for page_requirement in page_requirements]
        placeholder_descriptions = [
            placeholder.description for journey in journeys for placeholder in journey.placeholders
        ]
        concepts = self._extract_route_concepts([user_story, conditions, *placeholder_descriptions])
        return list(dict.fromkeys(seed_urls + required_urls + self._build_common_path_candidates(seed_urls, concepts)))

    @staticmethod
    def _extract_route_concepts(texts: list[str]) -> set[str]:
        """Return high-level page journey concepts mentioned by the requirements."""
        combined_text = " ".join(text.lower() for text in texts if text)
        concepts: set[str] = {"home"}

        if any(term in combined_text for term in ("product", "products", "item", "catalog", "shop", "store")):
            concepts.add("products")
        if "cart" in combined_text or "basket" in combined_text:
            concepts.add("cart")
        if any(term in combined_text for term in ("checkout", "check out", "place order", "payment", "order")):
            concepts.add("checkout")

        return concepts

    @staticmethod
    def _build_common_path_candidates(seed_urls: list[str], concepts: set[str]) -> list[str]:
        """Construct common route URLs from the supplied starting pages."""
        candidates: list[str] = []
        if not seed_urls:
            return candidates

        for seed_url in seed_urls:
            parsed = urlparse(seed_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}/"
            if "products" in concepts:
                candidates.append(urljoin(base_url, "products"))
            if "cart" in concepts:
                candidates.append(urljoin(base_url, "view_cart"))
            if "checkout" in concepts:
                candidates.append(urljoin(base_url, "checkout"))

        return list(dict.fromkeys(candidates))

    async def _resolve_placeholder_for_page(
        self,
        action: str,
        description: str,
        current_url: str | None,
        scraped_data: dict[str, list[dict[str, str]]],
    ) -> tuple[str, str | None]:
        """Resolve one placeholder using the active page first, then fall back to known pages."""
        scoped_pages = self._build_scoped_pages(current_url, scraped_data)

        if action in {"GOTO", "URL"}:
            resolved_url = self.resolver.resolve_url(description, scoped_pages or scraped_data)
            if resolved_url:
                return repr(resolved_url), resolved_url
            error_msg = f"Locator for '{description}' not found on scraped pages."
            return f'pytest.skip("{error_msg}")', None

        matched_element = await self._find_best_element_for_current_page(action, description, current_url, scoped_pages)
        if matched_element is None:
            matched_element = await self._find_best_element_for_current_page(
                action, description, current_url, scraped_data
            )

        if matched_element is not None:
            selector = repr(str(matched_element.get("selector", "")).strip())
            next_url = self._infer_next_page_url(action, description, matched_element, scraped_data)
            return selector, next_url

        error_msg = f"Locator for '{description}' not found on scraped pages."
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
    ) -> str | None:
        """Infer the next active page after a resolved step when navigation is implied."""
        href = str(matched_element.get("href", "")).strip()
        if action == "CLICK" and href:
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
    def _normalise_generated_code(code: str, consent_mode: str = "auto-dismiss") -> str:
        """Apply small deterministic fixes to common skeleton-generation mistakes."""
        fixed_code = code

        if "pytest.skip(" in fixed_code and "import pytest" not in fixed_code:
            fixed_code = TestOrchestrator._inject_import(fixed_code, "import pytest")

        fixed_code = re.sub(r"(def __init__\(self,\s*page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
        fixed_code = re.sub(r"(def test_[A-Za-z0-9_]*\(page:\s*)([A-Za-z_][A-Za-z0-9_]*)", r"\1Page", fixed_code)
        fixed_code = re.sub(r"(?<=:\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)
        fixed_code = re.sub(r"(?<=->\s)(?:Plan|Payable|Note)\b", "Page", fixed_code)
        fixed_code = TestOrchestrator._rewrite_page_references_in_class_methods(fixed_code)
        if consent_mode == "auto-dismiss":
            fixed_code = TestOrchestrator._inject_consent_helper(fixed_code)
        return fixed_code

    @staticmethod
    def _inject_import(code: str, import_line: str) -> str:
        """Insert an import near the top of the generated file."""
        lines = code.splitlines()

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
        "button:has-text('I Agree')",
        "button:has-text('Agree')",
    ]
    for selector in candidate_selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                locator.click(timeout=2000)
                page.wait_for_timeout(500)
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
            if stripped.startswith("page.goto("):
                updated_lines.append(f"{indent}dismiss_consent_overlays(page)")

        return "\n".join(updated_lines)
