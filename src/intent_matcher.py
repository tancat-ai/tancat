"""Intent-based element filtering for placeholder resolution.

Strategy-registry architecture: each intent category is a standalone
``IntentStrategy`` implementation.  ``IntentMatcher.matches()`` is a
thin dispatcher that iterates registered strategies until one returns
a definitive ``True`` or ``False``.

Extracted from ``placeholder_resolver.py`` — all intent-classification
logic lives here and can be tested in isolation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.semantic_matcher import SemanticMatcher

# ---------------------------------------------------------------------
# Protocol / base class
# ---------------------------------------------------------------------


class IntentStrategy(ABC):
    """A single intent-matching strategy.

    Returns ``True`` when the element should be accepted, ``False`` when
    it should be rejected, or ``None`` when the strategy is indifferent
    (i.e. the intent doesn't fall under its responsibility).
    """

    @abstractmethod
    def match(
        self,
        action: str,
        description: str,
        element: dict[str, Any],
    ) -> bool | None:
        """Return ``True`` / ``False`` / ``None`` (indifferent)."""


# ---------------------------------------------------------------------
# Shared helpers (used by several strategies)
# ---------------------------------------------------------------------


def _all_element_text(element: dict[str, Any]) -> str:
    """Concatenate all searchable text fields of *element*."""
    fields = (
        "selector",
        "text",
        "href",
        "classes",
        "icon_classes",
        "visual_description",
        "parent_text",
        "aria_icon_label",
        "value",
        "data_test",
        "name",
        "placeholder",
        "aria_label",
        "accessible_name",
    )
    return " ".join(str(element.get(f, "")).lower() for f in fields)


def _is_fillable(element: dict[str, Any]) -> bool:
    """Return ``True`` when the scraped element supports text entry."""
    role = str(element.get("role", "")).strip().lower()
    selector = str(element.get("selector", "")).strip().lower()
    name = str(element.get("name", "")).strip().lower()
    element_id = str(element.get("id", "")).strip().lower()

    if role == "hidden":
        return False
    if any(term in name or term in element_id or term in selector for term in ("csrf", "token", "authenticity")):
        return False

    if role in {
        "input",
        "textarea",
        "select",
        "textbox",
        "searchbox",
        "combobox",
        "email",
        "password",
        "text",
        "tel",
        "number",
    }:
        return True
    if selector.startswith(("input", "textarea", "select")):
        return True
    return bool(element.get("name") or element.get("placeholder"))


def _description_words(description: str) -> set[str]:
    """Return tokenised words from *description* longer than 3 characters."""
    return SemanticMatcher.get_words(description)


# ---------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------


class ExactIdStrategy(IntentStrategy):
    """Match when element id / data-test contains description tokens."""

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        element_id = str(element.get("id", "")).lower()
        data_test = str(element.get("data_test", "")).lower()
        id_haystack = f"{element_id} {data_test}"
        desc_words = _description_words(description)
        if any(word in id_haystack for word in desc_words if len(word) > 3):
            return True
        return None


class SemanticFillStrategy(IntentStrategy):
    """Semantic similarity matching for FILL actions on fillable elements."""

    # Form-field keyword maps for explicit field matching.
    FORM_FIELD_MAP: dict[str, set[str]] = {
        "first name": {"first-name", "firstname", "firstName", "first_name", "f-name"},
        "last name": {"last-name", "lastname", "lastName", "last_name", "l-name", "surname"},
        "zip code": {"zip-code", "zipcode", "zipCode", "zip_code", "postal", "postal-code"},
        "email address": {"email", "e-mail", "email-address", "email_address", "mail"},
        "phone number": {"phone", "telephone", "phone-number", "phone_number", "tel"},
        "company": {"company", "company name", "company_name", "business"},
        "address": {"address", "address1", "street", "street-address"},
        "city": {"city", "town"},
        "state": {"state", "province", "region"},
        "country": {"country", "nation"},
    }

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "FILL" or not _is_fillable(element):
            return None

        lowered = description.replace("_", " ").lower()
        all_text = _all_element_text(element)
        element_id = str(element.get("id", "")).lower()
        data_test = str(element.get("data_test", "")).lower()
        name = str(element.get("name", "")).lower()
        placeholder_text = str(element.get("placeholder", "")).lower()
        aria_label = str(element.get("aria_label", "")).lower()
        accessible_name = str(element.get("accessible_name", "")).lower()

        # Semantic similarity against field identifiers
        for field in (element_id, data_test, name, placeholder_text, aria_label, accessible_name):
            if field:
                sim = SemanticMatcher.semantic_similarity(description, field)
                if sim > 0.4:
                    return True

        # Username / Password field matching
        if any(term in lowered for term in ("username", "user name", "user input", "email input")):
            if any(term in all_text for term in ("username", "user-name", "user_name", "email")):
                return True
        if any(term in lowered for term in ("password", "pass input", "pw input")):
            if any(term in all_text for term in ("password", "pass", "passwd")):
                return True

        # Explicit form-field map lookup
        for desc_key, element_ids in self.FORM_FIELD_MAP.items():
            if desc_key in lowered:
                if data_test in element_ids or element_id in element_ids or name in element_ids:
                    return True
                for eid in element_ids:
                    sim = SemanticMatcher.semantic_similarity(description, eid)
                    if sim > 0.5:
                        return True

        return None


class LoginIntentStrategy(IntentStrategy):
    """Login / logout / sign-in intent matching."""

    _LOGIN_TERMS = (
        "login",
        "log-in",
        "signin",
        "sign-in",
        "logout",
        "log-out",
        "signout",
        "sign-out",
        "submit",
    )
    _LOGIN_DESCRIPTION = ("login", "log in", "sign in", "logout", "log out", "sign out")
    _LOGIN_BUTTON_DESCRIPTION = ("login button", "sign in", "log in")
    _LOGIN_BUTTON_TEXT = ("login", "login-button", "login_button", "submit")

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        lowered = description.replace("_", " ").lower()
        all_text = _all_element_text(element)

        # General login/logout guard
        if any(term in lowered for term in self._LOGIN_DESCRIPTION):
            if any(term in all_text for term in self._LOGIN_TERMS):
                return True
            return None  # Don't reject — other strategies may match

        # Login button
        if action == "CLICK" and any(term in lowered for term in self._LOGIN_BUTTON_DESCRIPTION):
            if any(term in all_text for term in self._LOGIN_BUTTON_TEXT):
                return True

        return None


class SubscribeGuardStrategy(IntentStrategy):
    """Prevent subscribe/newsletter elements from matching unrelated intents."""

    def _is_subscribe_element(self, element: dict[str, Any]) -> bool:
        all_text = _all_element_text(element)
        element_id = str(element.get("id", "")).lower()
        return (
            "subscribe" in all_text
            or "newsletter" in all_text
            or element_id in {"subscribe", "susbscribe_email", "newsletter_email"}
        )

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if not self._is_subscribe_element(element):
            return None

        lowered = description.replace("_", " ").lower()
        text = str(element.get("text", "")).lower()

        # Cart / checkout / payment intents should NOT match subscribe elements
        if any(term in lowered for term in ("cart", "checkout", "payment")):
            return False

        # Dismissive actions should NOT match subscribe elements
        if action == "CLICK" and any(
            term in lowered
            for term in (
                "continue shopping",
                "close",
                "dismiss",
                "ok",
                "cancel",
                "popup",
                "modal",
                "confirmation",
            )
        ):
            return False

        # Subscribe element with no visible text should not be clicked
        if action == "CLICK" and not text.strip():
            return False

        return None


class PageStateAssertStrategy(IntentStrategy):
    """Reject element-level matches for page-state assertions.

    R-005 FIX: Also handles vague descriptions like
    "checkout page is loaded and order summary section is visible"
    by detecting page-level intent keywords.
    """

    _PAGE_STATE_TERMS = (
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
        # R-005: Vague page-state patterns
        "page is loaded",
        "page loads",
        "page is visible",
        "page displays",
        "page shows",
    )

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "ASSERT":
            return None
        lowered = description.replace("_", " ").lower()
        if any(term in lowered for term in self._PAGE_STATE_TERMS):
            return False
        return None


class ProductCardStrategy(IntentStrategy):
    """Match product card elements."""

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "CLICK":
            return None
        lowered = description.replace("_", " ").lower()
        if "product card" not in lowered:
            return None
        all_text = _all_element_text(element)
        return any(term in all_text for term in ("product card", "product-card", "card"))


class CartIntentStrategy(IntentStrategy):
    """Cart-related click and text matching."""

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "CLICK":
            return None
        lowered = description.replace("_", " ").lower()
        all_text = _all_element_text(element)
        text = str(element.get("text", "")).lower()
        text_val = str(element.get("text", "")).strip()

        # Cart navigation
        if "cart" in lowered and any(term in lowered for term in ("go", "open", "navigate")):
            return "view_cart" in all_text or 'href="/view_cart"' in all_text or text.strip() == "cart"

        # Add to cart — REJECT cart navigation links (they are not add-to-cart buttons)
        if "add" in lowered and "cart" in lowered:
            if any(term in all_text for term in ("view_cart", "go_to_cart", "cart_link", "cart-icon")):
                return False
            if any(term in all_text for term in ("add to cart", "add-to-cart", "data-product-id", "product_id", "buy")):
                return True
            # "add to cart" intent with no add-to-cart signal -> reject
            return False

        # Add to cart (text-based)
        if any(term in lowered for term in ("add to cart", "addtocart", "add-to-basket")):
            if "add" in all_text and ("cart" in all_text or "basket" in all_text):
                return True
            if text_val:
                sim = SemanticMatcher.semantic_similarity(description, text_val)
                if sim > 0.3:
                    return True

        # Shopping cart link
        if any(term in lowered for term in ("shopping cart", "cart link", "cart icon", "go to cart")):
            return any(
                term in all_text for term in ("cart", "basket", "shopping", "view cart", "go to cart", "shopping-cart")
            )

        return None


class CheckoutIntentStrategy(IntentStrategy):
    """Checkout navigation and order completion."""

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "CLICK":
            return None
        lowered = description.replace("_", " ").lower()
        all_text = _all_element_text(element)

        # Finish / complete order
        if any(term in lowered for term in ("finish", "complete order", "place order", "confirm order")):
            return any(
                term in all_text
                for term in (
                    "finish",
                    "complete",
                    "place order",
                    "confirm order",
                    "submit order",
                    "confirm purchase",
                )
            )

        # Checkout navigation
        if any(term in lowered for term in ("proceed to checkout", "go to checkout", "checkout page")):
            return any(
                term in all_text for term in ("checkout", "check out", "proceed to checkout", "place your order")
            )

        # Checkout CLICK
        if any(term in lowered for term in ("checkout", "check out")):
            if "payment" in all_text and "payment" not in lowered:
                return False
            return any(
                term in all_text
                for term in ("checkout", "check out", "proceed to checkout", "place order", "check_out")
            )

        return None


class CartAssertStrategy(IntentStrategy):
    """Cart / checkout / item ASSERT matching."""

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "ASSERT":
            return None
        lowered = description.replace("_", " ").lower()
        if not ("cart" in lowered or "item" in lowered or "checkout" in lowered):
            return None

        all_text = _all_element_text(element)

        is_content = any(
            term in all_text
            for term in (
                "cart_description",
                "cart_quantity",
                "cart_price",
                "cart_total",
                "cart-summary",
                "summary",
                "product",
                "quantity",
                "price",
                "cart_info",
                "checkout",
                "order",
                "payment",
            )
        )
        if "search" in all_text and "cart" not in all_text:
            return False
        is_nav = str(element.get("role", "")).strip().lower() == "a" and "view_cart" in all_text
        return is_content and not is_nav


class PopupAssertStrategy(IntentStrategy):
    """ASSERT matching for confirmation popups/modals/alerts.

    Handles generic descriptions like:
    - "confirmation popup appears"
    - "product added confirmation popup"
    - "success alert is visible"

    Matches elements that are inside or are modals/dialogs/alerts.
    """

    _POPUP_KEYWORDS = (
        "popup",
        "confirmation popup",
        "confirmation message",
        "success message",
        "success alert",
        "notification",
        "alert message",
        "appears",
        "appearing",
    )

    _POPUP_ELEMENT_SIGNALS = (
        "modal",
        "dialog",
        "popup",
        "overlay",
        "alert",
        "notification",
        "continue shopping",
        "close-modal",
        "close-btn",
        "btn-success",
    )

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "ASSERT":
            return None

        lowered = description.replace("_", " ").lower()
        has_popup_keyword = any(term in lowered for term in self._POPUP_KEYWORDS)
        if not has_popup_keyword:
            return None

        all_text = _all_element_text(element)
        role = str(element.get("role", "")).strip().lower()
        tag = str(element.get("tag", "")).strip().lower()
        classes = str(element.get("classes", "")).lower()
        selector = str(element.get("selector", "")).lower()

        # Match modal/dialog roles
        if role in {"dialog", "alertdialog", "alert", "status"}:
            return True

        # Match elements with modal/dialog classes
        if any(signal in classes or signal in selector or signal in all_text for signal in self._POPUP_ELEMENT_SIGNALS):
            return True

        # Match content elements inside modal-like context
        if tag in {"div", "p", "span", "h2", "h3", "button"}:
            text = str(element.get("text", "")).strip().lower()
            parent_text = str(element.get("parent_text", "")).lower()
            if any(
                term in text or term in parent_text
                for term in ("continue", "close", "confirm", "success", "thank", "added", "order", "purchase")
            ):
                return True

        return None


class GenericAssertStrategy(IntentStrategy):
    """Fallback ASSERT matching for high-level semantic descriptions.

    Handles descriptions like:
    - "added item listed with correct details"
    - "order summary is displayed"
    - "product listings appear"

    Matches elements that represent content displays (tables, lists, headings).
    """

    _CONTENT_DISPLAY_TERMS = (
        "listed",
        "displayed",
        "appear",
        "appears",
        "visible",
        "shown",
        "present",
        "correct details",
        "summary",
        # R-005: Additional vague content indicators
        "is displayed",
        "is visible",
        "are visible",
        "is shown",
        "is present",
        "is listed",
        "section is visible",
        "table is visible",
        "list is visible",
        "with items",
        "with at least",
        "contains",
    )

    _CONTENT_ROLES = {
        "cell",
        "row",
        "columnheader",
        "rowheader",
        "listitem",
        "list",
        "treeitem",
        "region",
        "article",
        "section",
        "heading",
        "paragraph",
        "text",
    }

    _CONTENT_TAGS = {"td", "th", "tr", "li", "ul", "ol", "table", "div", "p", "span", "h1", "h2", "h3"}

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "ASSERT":
            return None

        lowered = description.replace("_", " ").lower()
        has_content_term = any(term in lowered for term in self._CONTENT_DISPLAY_TERMS)
        if not has_content_term:
            return None

        role = str(element.get("role", "")).strip().lower()
        tag = str(element.get("tag", "")).strip().lower()
        text = str(element.get("text", "")).strip()

        # Content display elements with text are good candidates
        if (role in self._CONTENT_ROLES or tag in self._CONTENT_TAGS) and text:
            return True

        return None


class SuccessAssertStrategy(IntentStrategy):
    """Thank-you / order-confirmed / success ASSERT matching.

    Requires BOTH a success/confirmation keyword AND a message-like keyword
    in the description to avoid over-claiming generic "confirmation message"
    assertions that may target cart items or product confirmations.
    """

    _SUCCESS_KEYWORDS = (
        "thank you",
        "thankyou",
        "success",
        "order confirmed",
        "order complete",
    )
    _MESSAGE_KEYWORDS = (
        "confirmation message",
        "success message",
        "success alert",
        "notification",
        "popup",
        "alert message",
        "confirmation popup",
    )
    _SUCCESS_ELEMENT_TEXT = (
        "thank you",
        "thankyou",
        "order confirmed",
        "order complete",
        "order summary",
        "confirmation",
        "success",
    )

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "ASSERT":
            return None
        lowered = description.replace("_", " ").lower()

        # Require BOTH a success keyword AND a message keyword to avoid
        # over-claiming generic "confirmation message" assertions.
        has_success = any(term in lowered for term in self._SUCCESS_KEYWORDS)
        has_message = any(term in lowered for term in self._MESSAGE_KEYWORDS)

        if not (has_success and has_message):
            return None

        all_text = _all_element_text(element)
        return any(term in all_text for term in self._SUCCESS_ELEMENT_TEXT)


class ContinueShoppingStrategy(IntentStrategy):
    """Continue shopping / continue checkout button matching."""

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "CLICK":
            return None
        lowered = description.replace("_", " ").lower()
        all_text = _all_element_text(element)

        if "continue shopping" in lowered:
            return any(term in all_text for term in ("continue shopping", "continue", "shop", "keep shopping"))
        if any(term in lowered for term in ("continue button", "continue checkout")):
            return "continue" in all_text
        return None


class ProductNameStrategy(IntentStrategy):
    """Match elements by product-name word overlap (fallback)."""

    _PRODUCT_INDICATORS = {"add to cart", "click", "button", "link", "select", "choose"}

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action not in {"CLICK", "ASSERT"}:
            return None

        lowered = description.replace("_", " ").lower()
        product_words = [w for w in lowered.split() if w not in self._PRODUCT_INDICATORS and len(w) > 2]
        if len(product_words) < 2:
            return None

        text = str(element.get("text", "")).lower()
        data_test = str(element.get("data_test", "")).lower()
        element_id = str(element.get("id", "")).lower()
        name = str(element.get("name", "")).lower()
        aria_label = str(element.get("aria_label", "")).lower()

        content = " ".join([text, data_test, element_id, name, aria_label])
        matched = sum(1 for pw in product_words if pw in content or pw.replace(" ", "") in content.replace(" ", ""))
        if matched >= max(1, len(product_words) // 2):
            return True
        return None


class VagueSectionAssertStrategy(IntentStrategy):
    """Handle vague ASSERT descriptions about page sections/areas.

    R-005 FIX: Descriptions like
    - "product categories section containing category links like Dress, Jackets"
    - "category page title 'PRODUCT CATEGORIES' is visible"
    - "a list of dress products is displayed on the page"
    - "cart page table is visible with at least one product row"

    These are too abstract for keyword matching but target headings,
    lists, tables, or regions. Match any content-bearing element
    that shares at least 2 content words with the description.
    """

    _SECTION_INDICATORS = (
        "section",
        "containing",
        "with",
        "like",
        "list of",
        "a list",
        "is displayed",
        "is visible",
        "are visible",
        "on the page",
        "table is",
        "with at least",
        "page title",
        "header is",
    )

    def match(self, action: str, description: str, element: dict[str, Any]) -> bool | None:
        if action != "ASSERT":
            return None

        lowered = description.replace("_", " ").lower()
        has_section_intent = any(term in lowered for term in self._SECTION_INDICATORS)
        if not has_section_intent:
            return None

        # Content words from description (minus stop words and section indicators)
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "and",
            "or",
            "in",
            "on",
            "at",
            "to",
            "for",
            "with",
            "by",
            "from",
            "of",
            "visible",
            "displayed",
            "shown",
            "present",
            "section",
            "containing",
            "like",
            "list",
            "page",
            "element",
        }
        desc_words = {w for w in lowered.split() if w not in stop_words and len(w) > 2}
        if len(desc_words) < 2:
            return None

        text = str(element.get("text", "")).strip().lower()
        if not text:
            return None

        element_tokens = set(text.replace("_", " ").replace("-", " ").split())
        overlap = desc_words & element_tokens

        # Require at least 2 content word matches
        if len(overlap) >= min(2, len(desc_words)):
            return True

        return None


# ---------------------------------------------------------------------
# Matcher (thin dispatcher)
# ---------------------------------------------------------------------


class IntentMatcher:
    """Thin dispatcher over registered :class:`IntentStrategy` instances.

    Provides guard-rails that prevent the resolver from latching onto
    irrelevant elements (e.g. newsletter subscribe inputs when the user
    story says "add to cart").
    """

    # Form-field keyword map kept for backwards compatibility with any
    # external code that references ``IntentMatcher.FORM_FIELD_MAP``.
    FORM_FIELD_MAP: dict[str, set[str]] = SemanticFillStrategy.FORM_FIELD_MAP

    def __init__(self, strategies: list[IntentStrategy] | None = None) -> None:
        """Use default strategy registry unless explicit list is supplied."""
        if strategies is None:
            self._strategies: list[IntentStrategy] = [
                ExactIdStrategy(),
                SemanticFillStrategy(),
                LoginIntentStrategy(),
                SubscribeGuardStrategy(),
                PageStateAssertStrategy(),
                ProductCardStrategy(),
                CartIntentStrategy(),
                CheckoutIntentStrategy(),
                CartAssertStrategy(),
                PopupAssertStrategy(),
                GenericAssertStrategy(),
                SuccessAssertStrategy(),
                ContinueShoppingStrategy(),
                ProductNameStrategy(),
                VagueSectionAssertStrategy(),
            ]
        else:
            self._strategies = strategies

    # ------------------------------------------------------------------
    # Public API  (backwards-compatible static method)
    # ------------------------------------------------------------------

    @staticmethod
    def matches(
        action: str,
        description: str,
        element: dict[str, Any],
    ) -> bool:
        """Return ``True`` when *element* fits the likely intent for *action* + *description*."""
        # Use default registry for static callers (backwards compatibility).
        instance = IntentMatcher()
        return instance.match(action, description, element)

    def match(
        self,
        action: str,
        description: str,
        element: dict[str, Any],
    ) -> bool:
        """Iterate strategies until one returns a definitive answer."""
        for strategy in self._strategies:
            result = strategy.match(action, description, element)
            if result is not None:
                return result
        # Default: accept (same behaviour as legacy implementation)
        return True

    # Legacy helpers kept as module-level aliases for backwards compat.
    _all_element_text = staticmethod(_all_element_text)
    _is_fillable = staticmethod(_is_fillable)
