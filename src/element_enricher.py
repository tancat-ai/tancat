"""Enrich scraped DOM elements with visual and contextual metadata.

This module adds visual attributes (icon detection, bounding box, parent context)
to raw scraped elements so that:
1. The LLM can generate better placeholder descriptions during skeleton generation
2. The PlaceholderResolver can match vague descriptions to elements using visual cues
"""

from __future__ import annotations

from typing import Any


class ElementEnricher:
    """Enrich scraped DOM elements with visual and contextual metadata."""

    __test__ = False

    # Icon font class patterns detected in element CSS classes
    ICON_FONT_PATTERNS = [
        "fa",  # Font Awesome
        "fas",  # Font Awesome Solid
        "far",  # Font Awesome Regular
        "fab",  # Font Awesome Brands
        "fal",  # Font Awesome Light
        "fad",  # Font Awesome Duotone
        "fi",  # Feather Icons
        "bi",  # Bootstrap Icons
        "mdi",  # Material Design Icons
        "ion",  # Ionicons
        "typcn",  # Typicon
        "wico",  # Weather Icons
        "gg",  # GGicons
        "eicon",  # Elementor Icons
        "octicon",  # GitHub Octicons
        "dashicons",  # WordPress Dashicons
        "anticon",  # Ant Design Icons
        "carbon",  # Carbon Icons
    ]

    # Unicode icon character ranges (common in icon fonts)
    UNICODE_ICON_RANGES = [
        (0xE000, 0xF8FF),  # Private Use Area (icon fonts)
        (0xF000, 0xF0FF),  # Font Awesome range
        (0xE800, 0xE8BF),  # Material Icons range
        (0xEA00, 0xEABC),  # Font Awesome extension
    ]

    # CSS classes that indicate an element is purely decorative
    DECORATIVE_CLASSES = [
        "sr-only",
        "visually-hidden",
        "hidden",
        "d-none",
        "invisible",
        "fa-sr-only",
        "not-sr-only",
    ]

    # CSS classes that indicate a hover-reveal overlay pattern
    # (elements inside these containers are often hidden until hover)
    HOVER_REVEAL_PARENT_CLASSES = [
        "product-overlay",
        "overlay-content",
        "tooltip",
        "dropdown-menu",
        "card-overlay",
        "image-overlay",
        "product-image-wrapper",
        "single-products",
        "product-image-wrapper",
    ]

    # CSS selectors for elements that commonly trigger hover-reveal
    HOVER_TRIGGER_CLASSES = [
        "product-card",
        "product-item",
        "product-grid-item",
        "item-wrapper",
        "card",
        "tile",
    ]

    @classmethod
    def enrich_element(
        cls,
        element: dict[str, Any],
        html_snippet: str = "",
        parent_classes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Enrich a single scraped element with visual and contextual metadata.

        Args:
            element: Raw scraped element dict.
            html_snippet: Optional HTML snippet for parent context extraction.
            parent_classes: Optional CSS classes from parent elements.

        Returns:
            Enriched element dict with additional visual fields.
        """
        enriched = dict(element)

        # Detect icon fonts and icon-only elements
        enriched["is_icon"] = cls._detect_is_icon(enriched)
        enriched["icon_classes"] = cls._detect_icon_classes(enriched)
        enriched["icon_unicode"] = cls._detect_icon_unicode(enriched)

        # Detect decorative elements (should be ignored in matching)
        enriched["is_decorative"] = cls._detect_decorative(enriched)

        # Detect hover-reveal elements (inside overlay containers)
        enriched["is_hover_reveal"] = cls._detect_hover_reveal(enriched, html_snippet)

        # Extract parent context from HTML snippet
        enriched["parent_text"] = cls._extract_parent_text(html_snippet) if html_snippet else ""

        # Extract aria/icon label for icon-only elements
        enriched["aria_icon_label"] = cls._extract_aria_icon_label(enriched)

        # Generate a human-readable visual description for LLM prompts
        enriched["visual_description"] = cls._generate_visual_description(enriched)

        return enriched

    @classmethod
    def _detect_is_icon(cls, element: dict[str, Any]) -> bool:
        """Detect whether an element is a pure icon (no meaningful text content)."""
        text = (element.get("text") or "").strip()
        classes = (element.get("classes") or "").lower()
        role = (element.get("role") or "").lower()

        # Pure icon: no text content but has icon-related classes
        if not text and any(icon in classes for icon in cls.ICON_FONT_PATTERNS):
            return True

        # Icon button: role is button/link/icon and text is empty or unicode-only
        if role in {"button", "link", "icon"} and not text:
            return True

        # Text is purely unicode icon characters (from icon fonts)
        if text and cls._is_unicode_icon_text(text):
            return True

        # Element has icon classes AND minimal text (text is likely a label for the icon)
        if any(icon in classes for icon in cls.ICON_FONT_PATTERNS) and text:
            # If text is short (< 30 chars) and element has icon classes, treat as icon+label
            if len(text) < 30:
                return True

        return False

    @classmethod
    def _detect_icon_classes(cls, element: dict[str, Any]) -> str:
        """Extract icon font class names from element CSS classes."""
        classes = (element.get("classes") or "").split()
        icon_classes = [c for c in classes if any(icon in c for icon in cls.ICON_FONT_PATTERNS)]
        return " ".join(icon_classes)

    @classmethod
    def _detect_icon_unicode(cls, element: dict[str, Any]) -> str:
        """Extract unicode icon characters from element text content."""
        text = element.get("text") or ""
        # Find unicode characters in the icon font ranges
        icons = []
        for char in text:
            code = ord(char)
            for start, end in cls.UNICODE_ICON_RANGES:
                if start <= code <= end:
                    icons.append(char)
                    break
        return "".join(icons)

    @classmethod
    def _is_unicode_icon_text(cls, text: str) -> bool:
        """Check if text consists entirely of unicode icon characters."""
        if not text:
            return False
        for char in text:
            is_icon_char = False
            for start, end in cls.UNICODE_ICON_RANGES:
                if start <= ord(char) <= end:
                    is_icon_char = True
                    break
            if not is_icon_char and not char.isspace():
                return False
        return True

    @classmethod
    def _detect_decorative(cls, element: dict[str, Any]) -> bool:
        """Detect whether an element is purely decorative (should be ignored)."""
        classes = (element.get("classes") or "").lower()
        class_list = classes.split()
        return any(dec in class_list for dec in cls.DECORATIVE_CLASSES)

    @classmethod
    def _detect_hover_reveal(
        cls,
        element: dict[str, Any],
        html_snippet: str = "",
    ) -> bool:
        """Detect whether an element is likely hidden inside a hover-reveal overlay.

        This identifies elements that are commonly hidden via CSS (display:none,
        visibility:hidden, opacity:0) and only become visible when the parent
        element receives a mouseenter event — common pattern in e-commerce
        product grids where 'Add to cart' buttons appear on hover.

        Detection criteria:
        1. Element has classes matching hover-reveal parent patterns
        2. Element is inside a parent with overlay-related classes (from html_snippet)
        3. Element is an interactive element (button, link) inside overlay containers
        """
        classes = (element.get("classes") or "").lower()
        selector = (element.get("selector") or "").lower()

        # Check if element classes match hover-reveal patterns
        if any(hrc in classes for hrc in cls.HOVER_REVEAL_PARENT_CLASSES):
            return True

        # Check if selector contains overlay-related patterns
        if any(pattern in selector for pattern in ["overlay", "tooltip", "dropdown"]):
            return True

        # Check HTML snippet for parent overlay context
        if html_snippet:
            # Look for common overlay parent patterns in the HTML
            overlay_indicators = [
                'class="product-overlay',
                'class="overlay-content',
                'class="card-overlay',
                'class="image-overlay',
                'class="single-products',
                'class="product-image-wrapper',
                'class="product_overlay',
                'class="overlay_',
            ]
            for indicator in overlay_indicators:
                if indicator.lower() in html_snippet.lower():
                    # Element is inside an overlay context
                    return True

        return False

    @classmethod
    def _extract_parent_text(cls, html_snippet: str) -> str:
        """Extract visible text from parent elements in the HTML snippet."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_snippet, "html.parser")
        parent_texts: list[str] = []

        # Check common wrapper elements
        for parent_tag in ["li", "div", "span", "td", "th", "figure", "figcaption"]:
            for parent in soup.find_all(parent_tag):
                text = parent.get_text(" ", strip=True)
                if text and len(text) < 200:
                    parent_texts.append(text)

        return " | ".join(parent_texts[:3])  # Limit to 3 parent contexts

    @classmethod
    def _extract_aria_icon_label(cls, element: dict[str, Any]) -> str:
        """Extract aria-label, title, or alt text for icon-only elements."""
        for field in ["aria_label", "title", "alt", "name"]:
            value = (element.get(field) or "").strip()
            if value:
                return value
        return ""

    @classmethod
    def _generate_visual_description(cls, element: dict[str, Any]) -> str:
        """Generate a human-readable visual description of the element.

        This is used in LLM prompts to help the model understand what the
        element looks like, enabling better placeholder descriptions.
        """
        parts: list[str] = []

        # Icon description
        icon_classes = element.get("icon_classes", "")
        icon_unicode = element.get("icon_unicode", "")
        if icon_classes:
            parts.append(f"icon({icon_classes})")
        if icon_unicode:
            parts.append(f"icon-unicode('{icon_unicode}')")

        # Text label
        text = (element.get("text") or "").strip()
        if text:
            parts.append(f'label("{text}")')

        # ARIA/alt label for icon-only elements
        aria_label = element.get("aria_icon_label", "")
        if aria_label and not text:
            parts.append(f'aria-label("{aria_label}")')

        # Role hint
        role = (element.get("role") or "").strip()
        if role and role not in {"", "unknown"}:
            parts.append(f"role({role})")

        # HTML tag
        tag = element.get("selector", "").split("[")[0].split(".")[0].strip("#.")
        if tag and tag not in {"div", "span", ""}:
            parts.append(f"[{tag}]")

        return " ".join(parts) if parts else ""

    @classmethod
    def enrich_batch(
        cls,
        elements: list[dict[str, Any]],
        html_snippets: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Enrich a batch of elements with visual metadata.

        Args:
            elements: List of raw scraped elements.
            html_snippets: Optional mapping of element index -> HTML snippet.

        Returns:
            List of enriched elements.
        """
        html_snippets = html_snippets or {}
        return [cls.enrich_element(elem, html_snippets.get(str(i), "")) for i, elem in enumerate(elements)]

    @classmethod
    def get_hover_reveal_selectors(
        cls,
        elements: list[dict[str, Any]],
    ) -> list[str]:
        """Return selectors for elements identified as hover-reveal.

        This is useful for generating test code that needs to hover over
        parent elements before clicking child elements.
        """
        return [elem["selector"] for elem in elements if elem.get("is_hover_reveal", False)]
