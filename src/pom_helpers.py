"""POM-mode helpers for placeholder resolution.

Extracted from ``placeholder_orchestrator.py``. Handles Page Object Model
artifact generation, import statements, instantiation lines, and converting
placeholder tokens into POM method calls.
"""

from __future__ import annotations

import logging

from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, ScrapedPage

logger = logging.getLogger(__name__)

# R-004: Minimum elements for a useful page object.
# Pages with very few elements are usually 404s, empty states, or noise.
MIN_PAGE_OBJECT_ELEMENTS = 3

_page_object_builder = PageObjectBuilder()


def build_page_object_artifacts(
    scraped_pages: list[ScrapedPage],
    *,
    pom_mode: bool = False,
) -> list[GeneratedPageObject]:
    """Return page object artifacts generated from scraped pages.

    When ``pom_mode`` is enabled, page objects are built with
    ``use_evidence_tracker=True`` so generated methods delegate to
    ``self.tracker.click()`` / ``self.tracker.fill()`` etc.

    R-004 FIX: Filter out low-quality page objects that have fewer than
    MIN_PAGE_OBJECT_ELEMENTS meaningful elements. Pages with only 2-3 elements
    (e.g., 404 pages, empty states) produce catch-all GeneratedPage classes
    that add noise to test imports.
    """
    generated_objects: list[GeneratedPageObject] = []

    for scraped_page in scraped_pages:
        generated_obj = _page_object_builder.build_page_object(
            scraped_page,
            file_path=_page_object_builder.get_default_file_path(scraped_page.url),
            use_evidence_tracker=pom_mode,
        )

        if generated_obj.class_name == "GeneratedPage" and scraped_page.element_count < MIN_PAGE_OBJECT_ELEMENTS:
            has_interactive = any(
                str(e.get("role", "")).lower() in ("button", "link", "textbox", "checkbox", "menuitem")
                for e in scraped_page.elements
            )
            if not has_interactive:
                logger.debug(
                    "Skipping low-quality page object '%s' for '%s' (%d elements, no interactive elements)",
                    generated_obj.class_name,
                    scraped_page.url,
                    scraped_page.element_count,
                )
                continue

        generated_objects.append(generated_obj)

    return generated_objects


def build_pom_url_map(page_objects: list[GeneratedPageObject]) -> dict[str, GeneratedPageObject]:
    """Build a mapping from URL to page object for POM mode resolution."""
    url_map: dict[str, GeneratedPageObject] = {}
    for po in page_objects:
        url_map[po.url] = po
    return url_map


def build_pom_imports(page_objects: list[GeneratedPageObject]) -> list[str]:
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


def build_pom_instantiation(
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


def get_pom_instance_name(url: str | None, page_objects: list[GeneratedPageObject]) -> str | None:
    """Return the POM instance variable name for the given URL.

    Returns None if no page object is found for the URL.
    """
    if not url:
        return None
    for po in page_objects:
        if po.url == url:
            return po.module_name.replace("-", "_")
    return None


def get_pom_method_call(
    action: str,
    description: str,
    resolved_selector: str,
    pom_instance_name: str,
    fill_value: str = "",
) -> str | None:
    """Generate a POM method call for the given action.

    In POM mode:
    - CLICK -> {instance}.click("label")
    - FILL -> {instance}.fill("label", "value")
    - GOTO/URL -> page.goto(url) (navigation stays direct)
    - ASSERT -> evidence_tracker.assert_visible() (assertions stay direct)
    """
    if action == "ASSERT":
        return None
    if action in {"GOTO", "URL"}:
        return None

    label = description
    if action == "CLICK":
        return f"{pom_instance_name}.click({label!r})"
    if action == "FILL":
        return f"{pom_instance_name}.fill({label!r}, {fill_value!r})"

    return None


__all__ = [
    "build_page_object_artifacts",
    "build_pom_imports",
    "build_pom_instantiation",
    "build_pom_url_map",
    "get_pom_instance_name",
    "get_pom_method_call",
]
