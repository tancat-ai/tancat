"""POM-mode helpers for placeholder resolution.

Extracted from ``placeholder_orchestrator.py``. Handles Page Object Model
artifact generation, import statements, instantiation lines, and converting
placeholder tokens into POM method calls.
"""

from __future__ import annotations

import logging
import re

from src.page_object_builder import PageObjectBuilder
from src.pipeline_models import GeneratedPageObject, ScrapedPage

logger = logging.getLogger(__name__)

# R-004: Minimum elements for a useful page object.
# Pages with very few elements are usually 404s, empty states, or noise.
MIN_PAGE_OBJECT_ELEMENTS = 3

_INSTANTIATION_RE = re.compile(
    r"^(\s*)([A-Za-z_]\w*)\s*=\s*[A-Za-z_]\w*Page\((?:page)(?:\s*,\s*evidence_tracker)?\)\s*$"
)


def deduplicate_pom_lines(code: str) -> str:
    """Remove duplicated POM imports and per-test page-object instantiations.

    The LLM skeleton frequently emits its own page-object import + instantiation
    block (often with duplicate lines — e.g. ``home_page`` instantiated three
    times), and the pipeline then injects the canonical block on top. Neither
    the "skip if present" injection guards nor the structural re-serialiser
    deduplicate, so duplicates leak into the final file. This pass:

    - keeps the first occurrence of each module-level import line;
    - keeps the first instantiation of each instance variable per test
      function (``var = Class(page, evidence_tracker)`` or legacy
      ``var = Class(page)``).
    """
    lines = code.splitlines()
    out: list[str] = []
    seen_imports: set[str] = set()
    seen_instances: set[str] = set()
    in_function = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("def "):
            in_function = True
            seen_instances = set()
        elif stripped and line[:1] not in (" ", "\t") and not stripped.startswith(("#", "@")):
            # A module-level statement (import, constant, ...) ends any
            # previous function body.
            in_function = False

        if not in_function and (stripped.startswith("from ") or stripped.startswith("import ")):
            norm = re.sub(r"\s+", " ", stripped)
            if norm in seen_imports:
                continue
            seen_imports.add(norm)
            out.append(line)
            continue

        if in_function:
            m = _INSTANTIATION_RE.match(line)
            if m:
                var = m.group(2)
                if var in seen_instances:
                    continue
                seen_instances.add(var)
                out.append(line)
                continue

        out.append(line)

    return "\n".join(out)


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
    # resolved_selector arrives repr'd (e.g. 'a[href="/x"]') from the resolver, or
    # as a pytest.skip(...) expression when no element matched. Only pass a real
    # selector through — deferring to the runtime matcher for unresolved ones.
    selector_ok = bool(resolved_selector) and not str(resolved_selector).startswith("pytest.skip")
    if action == "CLICK":
        if selector_ok:
            return f"{pom_instance_name}.click({label!r}, selector={_selector_literal(resolved_selector)})"
        return f"{pom_instance_name}.click({label!r})"
    if action == "FILL":
        if selector_ok:
            return (
                f"{pom_instance_name}.fill({label!r}, {fill_value!r}, selector={_selector_literal(resolved_selector)})"
            )
        return f"{pom_instance_name}.fill({label!r}, {fill_value!r})"

    return None


def _selector_literal(value: str) -> str:
    """Return *value* as a Python string literal.

    The resolution phase already repr()s selectors; guard against raw callers
    so a bare ``#submit`` becomes ``'#submit'`` rather than broken Python.
    """
    v = str(value)
    if v.startswith(("'", '"')) or v.startswith(("pytest.skip", "expect(")):
        return v
    return repr(v)


__all__ = [
    "build_page_object_artifacts",
    "build_pom_imports",
    "build_pom_instantiation",
    "build_pom_url_map",
    "get_pom_instance_name",
    "get_pom_method_call",
]
