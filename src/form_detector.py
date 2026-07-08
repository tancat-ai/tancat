"""Form detection and element classification utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Selector constants (extracted from journey_scraper.py)
# ---------------------------------------------------------------------------

PRODUCT_SELECTORS: list[str] = [
    "a[href*='/product_details/']",
    "a[href*='/product/']",
    ".product-item a[href*='/product']",
    ".product-link",
    ".product-title a",
    ".products a[href*='product_details']",
    "[data-product-id]",
]

ADD_TO_CART_SELECTORS: list[str] = [
    'button:has-text("Add to cart")',
    "button.btn-default.cart",
    'button[type="submit"]',
    "input[type='submit']",
    "a.btn.add-to-cart",
    "a.add-to-cart",
    ".add-to-cart",
    "[data-action='add-to-cart']",
    "a[href*='add-to-cart']",
]

CONTINUE_SHOPPING_SELECTORS: list[str] = [
    'button:has-text("Continue Shopping")',
    "button.btn-success.close-modal",
    ".continue-shopping",
    "[data-action='continue-shopping']",
    'a:has-text("Continue Shopping")',
    ".modal-close",
    ".close-btn",
]


@dataclass
class FormField:
    """Represents a detected form field."""

    tag: str
    field_type: str
    selector: str
    name: str
    placeholder: str


class FormDetector:
    """Detect and classify form elements on a page."""

    @staticmethod
    def classify_input(raw_type: str, element: dict[str, Any]) -> str:
        """Map an input's type attribute to a canonical category."""
        type_map: dict[str, str] = {
            "email": "email",
            "password": "password",
            "tel": "phone",
            "number": "number",
            "date": "date",
            "checkbox": "checkbox",
            "radio": "radio",
            "file": "file",
            "hidden": "hidden",
            "submit": "submit",
            "button": "button",
            "reset": "reset",
        }
        return type_map.get(raw_type.lower(), "text")

    @staticmethod
    def identify_submit_button(elements: list[dict[str, Any]]) -> str | None:
        """Return the best submit button selector from a list of elements."""
        for sel in ADD_TO_CART_SELECTORS:
            for el in elements:
                if el.get("selector") == sel or sel in el.get("css_selectors", []):
                    return el.get("selector")
        # Fallback: first element with submit-like text
        for el in elements:
            text = (el.get("text") or "").lower()
            if any(w in text for w in ("submit", "add", "buy", "checkout", "proceed")):
                return el.get("selector")
        return None

    @staticmethod
    def detect_forms(elements: list[dict[str, Any]]) -> list[list[FormField]]:
        """Group scraped elements into form structures."""
        form_fields: list[FormField] = []
        for el in elements:
            tag = el.get("tag_name", "").lower()
            if tag not in ("input", "select", "textarea"):
                continue
            raw_type = el.get("input_type", "text")
            form_fields.append(
                FormField(
                    tag=tag,
                    field_type=FormDetector.classify_input(raw_type, el),
                    selector=el.get("selector", ""),
                    name=el.get("name", ""),
                    placeholder=el.get("placeholder", ""),
                )
            )
        # Group consecutive fields into forms (simple heuristic)
        return [form_fields] if form_fields else []

    @staticmethod
    def discover_selector(elements: list[dict[str, Any]], description: str) -> str | None:
        """Find the best selector for a described element."""
        best: str | None = None
        best_score = -1
        for el in elements:
            score = 0
            text = (el.get("text") or "").lower()
            name = (el.get("name") or "").lower()
            desc_lower = description.lower()
            if desc_lower in text:
                score += 10
            if desc_lower in name:
                score += 8
            if el.get("has_id"):
                score += 5
            if el.get("has_name"):
                score += 3
            if score > best_score:
                best_score = score
                best = el.get("selector")
        return best if best and best_score > 0 else None
