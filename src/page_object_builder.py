"""Build page object modules from scraped page metadata."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from src.file_utils import slugify
from src.pipeline_models import GeneratedPageObject, ScrapedPage

# Click method injected into POM classes — allows home_page.click('Dress category link')
# to resolve to click_dress_category_link() or fall back to self.page.locator().click().
# Two versions: one for evidence tracker (uses self.tracker) and one for plain POMs.
_CLICK_METHOD_SOURCE_ET = (
    "    def click(self, description: str) -> None:\n"
    '        """Click by semantic description — resolve to POM method or delegate to tracker."""\n'
    "        import re\n"
    "        clean = description.lower().strip().strip(chr(39) + chr(34))\n"
    "        method_name = 'click_' + re.sub(r'[^a-z0-9]', '_', clean)\n"
    "        method_name = re.sub(r'_+', '_', method_name).strip('_')\n"
    "        # Use dir() to avoid triggering __getattr__ which calls pytest.skip()\n"
    "        # Search click_ methods AND navigate_ methods (e.g. navigate_to_cart)\n"
    "        action_methods = {m for m in dir(self) if m.startswith('click_') or m.startswith('navigate_')}\n"
    "        if method_name in action_methods:\n"
    "            getattr(self, method_name)()\n"
    "            return\n"
    "        # Partial match: score action methods by keyword overlap.\n"
    "        # Remove noise words (link, button, section, navigation, category, page, etc.)\n"
    "        # and action prefixes (click, navigate) so that click_view_cart and\n"
    "        # navigate_to_cart are scored equally on their semantic content.\n"
    "        noise = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from',\n"
    "                'of', 'and', 'or', 'link', 'button', 'section', 'navigation',\n"
    "                'category', 'page', 'header', 'popup', 'menu', 'item', 'list',\n"
    "                'click', 'navigate'}\n"
    "        desc_parts = [p for p in method_name.split('_') if p and p not in noise]\n"
    "        # Build a set of navigate_ targets so we can prefer them over\n"
    "        # click_ methods when both exist for the same action\n"
    "        navigate_targets = {m[len('navigate_'):] for m in action_methods if m.startswith('navigate_')}\n"
    "        best_method, best_score = None, 0\n"
    "        # Sort so navigate_ methods come after click_ — then use >= to prefer\n"
    "        # navigate_ on ties (they have +1 bonus).\n"
    "        for method in sorted(action_methods, key=lambda m: not m.startswith('navigate_')):\n"
    "            score = sum(1 for p in desc_parts if p in method)\n"
    "            if score < 1:\n"
    "                continue\n"
    "            # Prefer navigate_ methods — they use a[href=...] locators which\n"
    "            # are more reliable than click_ methods that may match headings.\n"
    "            if method.startswith('navigate_'):\n"
    "                score += 1\n"
    "            if score > best_score:\n"
    "                best_method, best_score = method, score\n"
    "        if best_method:\n"
    "            getattr(self, best_method)()\n"
    "            return\n"
    "        # Last resort: use page.locator with text matching (fast-fail).\n"
    "        # Avoids delegating to evidence_tracker with a raw description\n"
    "        # which Playwright tries as a CSS selector and hangs on 5s timeout.\n"
    "        self.page.locator('text=' + description).first.click(timeout=3000)\n"
)

_CLICK_METHOD_SOURCE_PLAIN = (
    "    def click(self, description: str) -> None:\n"
    '        """Click by semantic description — resolve to POM method or fall back to page.locator."""\n'
    "        import re\n"
    "        clean = description.lower().strip().strip(chr(39) + chr(34))\n"
    "        method_name = 'click_' + re.sub(r'[^a-z0-9]', '_', clean)\n"
    "        method_name = re.sub(r'_+', '_', method_name).strip('_')\n"
    "        # Use dir() to avoid triggering __getattr__ which calls pytest.skip()\n"
    "        action_methods = {m for m in dir(self) if m.startswith('click_') or m.startswith('navigate_')}\n"
    "        if method_name in action_methods:\n"
    "            getattr(self, method_name)()\n"
    "            return\n"
    "        # Partial match: score action methods by keyword overlap.\n"
    "        # Remove action prefixes (click, navigate) so methods are scored on semantic content.\n"
    "        noise = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from',\n"
    "                'of', 'and', 'or', 'link', 'button', 'section', 'navigation',\n"
    "                'category', 'page', 'header', 'popup', 'menu', 'item', 'list',\n"
    "                'click', 'navigate'}\n"
    "        desc_parts = [p for p in method_name.split('_') if p and p not in noise]\n"
    "        best_method, best_score = None, 0\n"
    "        for method in sorted(action_methods, key=lambda m: not m.startswith('navigate_')):\n"
    "            score = sum(1 for p in desc_parts if p in method)\n"
    "            if score < 1:\n"
    "                continue\n"
    "            if method.startswith('navigate_'):\n"
    "                score += 1\n"
    "            if score > best_score:\n"
    "                best_method, best_score = method, score\n"
    "        if best_method:\n"
    "            getattr(self, best_method)()\n"
    "            return\n"
    "        # Last resort: use page.locator with text matching\n"
    "        self.page.locator('text=' + description).first.click(timeout=3000)\n"
)


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
        use_evidence_tracker: bool = False,
    ) -> GeneratedPageObject:
        """Return metadata plus source code for a page object module.

        Args:
            scraped_page: Scraped page metadata to build from.
            file_path: Override default file path.
            class_name: Override auto-derived class name.
            use_evidence_tracker: When True, generate evidence-aware POM methods
                that delegate to ``EvidenceTracker`` instead of raw ``page.locator()``.
        """
        resolved_class_name = class_name or self._derive_class_name(scraped_page.url)
        module_name = self._to_module_name(resolved_class_name)
        resolved_file_path = file_path or f"generated_tests/pages/{module_name}.py"
        methods = self._build_methods(scraped_page, use_evidence_tracker=use_evidence_tracker)
        method_names = [method_name for method_name, _source in methods]
        module_source = self._build_module_source(
            class_name=resolved_class_name,
            url=scraped_page.url,
            methods=methods,
            element_count=scraped_page.element_count,
            use_evidence_tracker=use_evidence_tracker,
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
        # Filter out parts that are purely numeric to avoid invalid identifiers like "1Page"
        words = [part for part in words if not part.isdigit()]
        if not words:
            return "GeneratedPage"
        return f"{''.join(words)}Page"

    @staticmethod
    def _to_module_name(class_name: str) -> str:
        """Convert a class name into a snake_case module name."""
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
        return snake.strip("_")

    def _build_methods(
        self,
        scraped_page: ScrapedPage,
        *,
        use_evidence_tracker: bool = False,
    ) -> list[tuple[str, str]]:
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
                use_evidence_tracker=use_evidence_tracker,
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
    def _build_method_source(
        method_name: str,
        selector: str,
        role: str,
        *,
        prefer_first: bool = False,
        use_evidence_tracker: bool = False,
    ) -> str:
        """Return one page object method source block.

        Args:
            method_name: The generated method name.
            selector: The locator selector string.
            role: The ARIA role of the element.
            prefer_first: Use ``.first`` when duplicate selectors exist.
            use_evidence_tracker: Generate evidence-aware method delegating to
                ``self.tracker`` instead of ``self.page.locator()``.
        """
        if use_evidence_tracker:
            return PageObjectBuilder._build_evidence_method_source(method_name, selector, role)
        # Existing page.locator() path (backward compatible)
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

    @staticmethod
    def _build_evidence_method_source(
        method_name: str,
        selector: str,
        role: str,
    ) -> str:
        """Return an evidence-aware method source block delegating to EvidenceTracker.

        The generated methods use ``self.tracker.click()``, ``self.tracker.fill()``,
        etc., so that every interaction is captured in the sidecar evidence JSON.
        """
        label = method_name.replace("click_", "").replace("fill_", "").replace("select_", "").replace("_", " ")

        if method_name.startswith("fill_"):
            return (
                f"    def {method_name}(self, value: str) -> None:\n"
                f"        self.tracker.fill({selector!r}, value, label={label!r})\n"
            )
        if method_name.startswith("select_"):
            # EvidenceTracker doesn't have a native select; use click as fallback
            return (
                f"    def {method_name}(self, value: str) -> None:\n"
                f"        self.tracker.fill({selector!r}, value, label={label!r})\n"
            )
        if role == "a" and method_name.startswith("navigate_to_"):
            return f"    def {method_name}(self) -> None:\n        self.tracker.click({selector!r}, label={label!r})\n"
        return f"    def {method_name}(self) -> None:\n        self.tracker.click({selector!r}, label={label!r})\n"

    def _build_module_source(
        self,
        *,
        class_name: str,
        url: str,
        methods: list[tuple[str, str]],
        element_count: int,
        use_evidence_tracker: bool = False,
    ) -> str:
        """Return the final Python module source.

        Args:
            class_name: Page object class name.
            url: Page URL.
            methods: List of (method_name, source) tuples.
            element_count: Number of scraped elements.
            use_evidence_tracker: Generate evidence-aware module with
                ``EvidenceTracker`` dependency injection.
        """
        method_blocks = "\n".join(method_source.rstrip() for _name, method_source in methods)
        if method_blocks:
            method_blocks = f"\n{method_blocks}\n"
        else:
            method_blocks = (
                "\n    def page_ready(self) -> None:\n"
                "        # No specific interaction methods were derived for this page yet.\n"
                "        pass\n"
            )

        if use_evidence_tracker:
            imports = (
                '"""Auto-generated page object module."""\n\n'
                "from playwright.sync_api import Page\n"
                "from src.evidence_tracker import EvidenceTracker\n\n\n"
            )
            init_code = (
                "    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:\n"
                "        self.page = page\n"
                "        self.tracker = tracker\n\n"
            )
            navigate_code = "    def navigate(self) -> None:\n        self.tracker.navigate(self.URL)\n\n"
        else:
            imports = '"""Auto-generated page object module."""\n\nfrom playwright.sync_api import Page\n\n\n'
            init_code = "    def __init__(self, page: Page) -> None:\n        self.page = page\n\n"
            navigate_code = "    def navigate(self) -> None:\n        self.page.goto(self.URL)\n\n"

        return (
            f"{imports}"
            f"class {class_name}:\n"
            f'    """Page Object for {url}. Scraped elements: {element_count}."""\n\n'
            f'    URL = "{url}"\n\n'
            f"{init_code}"
            f"{navigate_code}"
            + (_CLICK_METHOD_SOURCE_ET if use_evidence_tracker else _CLICK_METHOD_SOURCE_PLAIN)
            + "\n"
            "    def __getattr__(self, name):\n"
            "        def fallback(*args, **kwargs):\n"
            "            import pytest\n"
            "            pytest.skip(f\"Method '{name}' not found on {self.__class__.__name__}. The scraper may have missed this element or its label changed.\")\n"
            "        return fallback\n"
            f"{method_blocks}"
        )
