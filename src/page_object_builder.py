"""Build page object modules from scraped page metadata."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from src.file_utils import slugify
from src.pipeline_models import GeneratedPageObject, ScrapedPage


class PageObjectBuilder:
    """Convert scraped pages into deterministic Playwright page object modules."""

    CLASS_NAME_ALIASES = {
        "": "HomePage",
        "cart": "CartPage",
        "checkout": "CheckoutPage",
        "payment": "PaymentPage",
        "product": "ProductPage",
        "products": "ProductsPage",
        "view_cart": "CartPage",
    }

    def build_page_object(
        self,
        scraped_page: ScrapedPage,
        *,
        file_path: str = "",
        class_name: str | None = None,
    ) -> GeneratedPageObject:
        """Return metadata plus source code for a page object module."""
        resolved_class_name = class_name or self._derive_class_name(scraped_page.url)
        module_name = self._to_module_name(resolved_class_name)
        resolved_file_path = file_path or f"generated_tests/pages/{module_name}.py"
        methods = self._build_methods(scraped_page)
        method_names = [method_name for method_name, _source in methods]
        module_source = self._build_module_source(
            class_name=resolved_class_name,
            url=scraped_page.url,
            methods=methods,
            element_count=scraped_page.element_count,
        )

        return GeneratedPageObject(
            class_name=resolved_class_name,
            module_name=module_name,
            file_path=resolved_file_path,
            url=scraped_page.url,
            methods=method_names,
            module_source=module_source,
        )

    def get_default_file_path(self, url: str, *, base_dir: str = "generated_tests/pages") -> str:
        """Return the default file path for a page object generated from a URL."""
        class_name = self._derive_class_name(url)
        module_name = self._to_module_name(class_name)
        return f"{base_dir}/{module_name}.py"

    def _derive_class_name(self, url: str) -> str:
        """Return a deterministic page object class name from a URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        last_segment = path.split("/")[-1] if path else ""
        last_segment = last_segment.removesuffix(".html").removesuffix(".php")
        alias = self.CLASS_NAME_ALIASES.get(last_segment)
        if alias:
            return alias

        if not last_segment:
            return "HomePage"

        words = [part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", last_segment) if part]
        return f"{''.join(words) or 'Generated'}Page"

    @staticmethod
    def _to_module_name(class_name: str) -> str:
        """Convert a class name into a snake_case module name."""
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
        return snake.strip("_")

    def _build_methods(self, scraped_page: ScrapedPage) -> list[tuple[str, str]]:
        """Return generated method names and source snippets for one page."""
        methods: list[tuple[str, str]] = []
        seen_names: set[str] = set()
        selector_counts: dict[str, int] = {}

        for element in scraped_page.elements:
            selector = str(element.get("selector", "")).strip()
            if not selector:
                continue
            selector_counts[selector] = selector_counts.get(selector, 0) + 1

        for element in scraped_page.elements:
            selector = str(element.get("selector", "")).strip()
            if not selector:
                continue

            method_name = self._derive_method_name(element)
            if not method_name or method_name in seen_names:
                continue

            method_source = self._build_method_source(
                method_name,
                selector,
                str(element.get("role", "")).strip().lower(),
                prefer_first=selector_counts.get(selector, 0) > 1,
            )
            methods.append((method_name, method_source))
            seen_names.add(method_name)

        return methods

    def _derive_method_name(self, element: dict[str, object]) -> str:
        """Return a reusable method name for a scraped element."""
        text_candidates = [
            str(element.get("text", "")).strip(),
            str(element.get("aria_label", "")).strip(),
            str(element.get("title", "")).strip(),
            str(element.get("name", "")).strip(),
            str(element.get("id", "")).strip(),
            str(element.get("placeholder", "")).strip(),
        ]
        label = next((candidate for candidate in text_candidates if candidate), "")
        normalized_label = slugify(label)
        role = str(element.get("role", "")).strip().lower()
        href = str(element.get("href", "")).strip().lower()

        if href and "cart" in href:
            return "navigate_to_cart"
        if href and any(term in href for term in ("checkout", "payment", "order")):
            return "proceed_to_checkout"
        if "cart" in normalized_label and role == "a":
            return "navigate_to_cart"
        if any(term in normalized_label for term in ("checkout", "payment", "place_order")):
            return "proceed_to_checkout"
        if normalized_label.startswith("add_to_cart"):
            return "add_item_to_cart"

        base_name = normalized_label or slugify(str(element.get("selector", "")))
        if role in {"input", "email", "password", "search", "text", "textarea"}:
            return f"fill_{base_name}"
        if role == "select":
            return f"select_{base_name}"

        return f"click_{base_name}"

    @staticmethod
    def _build_method_source(method_name: str, selector: str, role: str, *, prefer_first: bool = False) -> str:
        """Return one page object method source block."""
        escaped_selector = repr(selector)
        locator_expression = f"self.page.locator({escaped_selector})"
        if prefer_first:
            locator_expression += ".first"

        if method_name.startswith("fill_"):
            return f"    def {method_name}(self, value: str) -> None:\n        {locator_expression}.fill(value)\n"
        if method_name.startswith("select_"):
            return (
                f"    def {method_name}(self, value: str) -> None:\n        {locator_expression}.select_option(value)\n"
            )
        if role == "a" and method_name.startswith("navigate_to_"):
            return f"    def {method_name}(self) -> None:\n        {locator_expression}.click()\n"
        return f"    def {method_name}(self) -> None:\n        {locator_expression}.click()\n"

    def _build_module_source(
        self,
        *,
        class_name: str,
        url: str,
        methods: list[tuple[str, str]],
        element_count: int,
    ) -> str:
        """Return the final Python module source."""
        method_blocks = "\n".join(method_source.rstrip() for _name, method_source in methods)
        if method_blocks:
            method_blocks = f"\n{method_blocks}\n"
        else:
            method_blocks = (
                "\n    def page_ready(self) -> None:\n"
                "        # No specific interaction methods were derived for this page yet.\n"
                "        pass\n"
            )

        return (
            '"""Auto-generated page object module."""\n\n'
            "from playwright.sync_api import Page\n\n\n"
            f"class {class_name}:\n"
            f'    """Page Object for {url}. Scraped elements: {element_count}."""\n\n'
            f'    URL = "{url}"\n\n'
            "    def __init__(self, page: Page) -> None:\n"
            "        self.page = page\n\n"
            "    def navigate(self) -> None:\n"
            "        self.page.goto(self.URL)\n\n"
            "    def __getattr__(self, name):\n"
            "        def fallback(*args, **kwargs):\n"
            "            import pytest\n"
            "            pytest.skip(f\"Method '{name}' not found on {self.__class__.__name__}. The scraper may have missed this element or its label changed.\")\n"
            "        return fallback\n"
            f"{method_blocks}"
        )
