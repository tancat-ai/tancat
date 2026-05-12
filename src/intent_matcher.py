"""Intent-based element filtering for placeholder resolution.

Extracted from placeholder_resolver.py to separate intent-classification
logic into its own independently testable module.
"""

from __future__ import annotations

from typing import Any

from src.semantic_matcher import SemanticMatcher

__all__ = ["IntentMatcher"]


class IntentMatcher:
    """Determines whether a scraped DOM element fits the user-intent for a step.

    Provides guard-rails that prevent the resolver from latching onto
    irrelevant elements (e.g. newsletter subscribe inputs when the user
    story says "add to cart").
    """

    # Form-field keyword maps used for FILL intent matching.
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

    @staticmethod
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

    @staticmethod
    def _is_fillable(element: dict[str, Any]) -> bool:
        """Return True when the scraped element supports text entry."""
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def matches(
        action: str,
        description: str,
        element: dict[str, Any],
    ) -> bool:
        """Return True when *element* fits the likely intent for *action* + *description*."""
        lowered = description.replace("_", " ").lower()
        all_text = IntentMatcher._all_element_text(element)
        element_id = str(element.get("id", "")).lower()
        data_test = str(element.get("data", "")).lower()
        data_test = str(element.get("data_test", "")).lower()
        name = str(element.get("name", "")).lower()
        placeholder_text = str(element.get("placeholder", "")).lower()
        aria_label = str(element.get("aria_label", "")).lower()
        accessible_name = str(element.get("accessible_name", "")).lower()
        text = str(element.get("text", "")).lower()

        # EXACT ID / DATA-TEST MATCH (high priority)
        id_haystack = f"{element_id} {data_test}"
        desc_words = SemanticMatcher.get_words(description)
        if any(word in id_haystack for word in desc_words if len(word) > 3):
            return True

        # SEMANTIC SIMILARITY for FILL on fillable elements
        if action == "FILL" and IntentMatcher._is_fillable(element):
            for field in (element_id, data_test, name, placeholder_text, aria_label, accessible_name):
                if field:
                    sim = SemanticMatcher.semantic_similarity(description, field)
                    if sim > 0.4:
                        return True

        # LOGIN / LOGOUT guard
        if any(term in lowered for term in ("login", "log in", "sign in", "logout", "log out", "sign out")):
            return any(
                term in all_text
                for term in (
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
            )

        # USERNAME / PASSWORD field matching
        if action == "FILL" and IntentMatcher._is_fillable(element):
            if any(term in lowered for term in ("username", "user name", "user input", "email input")):
                if any(term in all_text for term in ("username", "user-name", "user_name", "email")):
                    return True
            if any(term in lowered for term in ("password", "pass input", "pw input")):
                if any(term in all_text for term in ("password", "pass", "passwd")):
                    return True

        # LOGIN button
        if action == "CLICK" and any(term in lowered for term in ("login button", "sign in", "log in")):
            if any(term in all_text for term in ("login", "login-button", "login_button", "submit")):
                return True

        # SUBSCRIBE / NEWSLETTER guard
        is_subscribe = (
            "subscribe" in all_text
            or "newsletter" in all_text
            or element_id in {"subscribe", "susbscribe_email", "newsletter_email"}
        )
        if any(term in lowered for term in ("cart", "checkout", "payment")):
            if is_subscribe:
                return False
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
            if is_subscribe:
                return False
        if action == "CLICK" and is_subscribe and not text.strip():
            return False

        # PAGE-STATE ASSERTION guard
        if action == "ASSERT" and any(
            term in lowered
            for term in (
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
            )
        ):
            return False

        # Product card
        if action == "CLICK" and "product card" in lowered:
            return any(term in all_text for term in ("product card", "product-card", "card"))

        # Cart navigation
        if action == "CLICK" and "cart" in lowered and any(term in lowered for term in ("go", "open", "navigate")):
            return "view_cart" in all_text or 'href="/view_cart"' in all_text or text.strip() == "cart"

        # Add to cart
        if action == "CLICK" and "add" in lowered and "cart" in lowered:
            return any(
                term in all_text for term in ("add to cart", "add-to-cart", "data-product-id", "product_id", "buy")
            )

        # Add to cart (text-based)
        if action == "CLICK" and any(term in lowered for term in ("add to cart", "addtocart", "add-to-basket")):
            if "add" in all_text and ("cart" in all_text or "basket" in all_text):
                return True
            text_val = str(element.get("text", "")).strip()
            if text_val:
                sim = SemanticMatcher.semantic_similarity(description, text_val)
                if sim > 0.3:
                    return True

        # Finish / complete order
        if action == "CLICK" and any(
            term in lowered for term in ("finish", "complete order", "place order", "confirm order")
        ):
            return any(
                term in all_text
                for term in ("finish", "complete", "place order", "confirm order", "submit order", "confirm purchase")
            )

        # Shopping cart link
        if action == "CLICK" and any(
            term in lowered for term in ("shopping cart", "cart link", "cart icon", "go to cart")
        ):
            return any(
                term in all_text for term in ("cart", "basket", "shopping", "view cart", "go to cart", "shopping-cart")
            )

        # Checkout navigation
        if action == "CLICK" and any(
            term in lowered for term in ("proceed to checkout", "go to checkout", "checkout page")
        ):
            return any(
                term in all_text for term in ("checkout", "check out", "proceed to checkout", "place your order")
            )

        # Form field matching
        if action == "FILL":
            for desc_key, element_ids in IntentMatcher.FORM_FIELD_MAP.items():
                if desc_key in lowered:
                    if data_test in element_ids or element_id in element_ids or name in element_ids:
                        return True
                    for eid in element_ids:
                        sim = SemanticMatcher.semantic_similarity(description, eid)
                        if sim > 0.5:
                            return True

        # Cart / checkout ASSERT
        if action == "ASSERT" and ("cart" in lowered or "item" in lowered or "checkout" in lowered):
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

        # Checkout CLICK
        if action == "CLICK" and any(term in lowered for term in ("checkout", "check out")):
            if "payment" in all_text and "payment" not in lowered:
                return False
            return any(
                term in all_text
                for term in ("checkout", "check out", "proceed to checkout", "place order", "check_out")
            )

        # Thank-you / success ASSERT
        if action == "ASSERT" and any(
            term in lowered for term in ("thank you", "thankyou", "success", "order confirmed", "order complete")
        ):
            return any(
                term in all_text
                for term in (
                    "thank you",
                    "thankyou",
                    "order confirmed",
                    "order complete",
                    "order summary",
                    "confirmation",
                    "success",
                )
            )

        # Continue shopping
        if action == "CLICK" and "continue shopping" in lowered:
            return any(term in all_text for term in ("continue shopping", "continue", "shop", "keep shopping"))
        if action == "CLICK" and any(term in lowered for term in ("continue button", "continue checkout")):
            return "continue" in all_text

        # Product name matching
        if action in {"CLICK", "ASSERT"}:
            product_indicators = {"add to cart", "click", "button", "link", "select", "choose"}
            product_words = [w for w in lowered.split() if w not in product_indicators and len(w) > 2]
            if len(product_words) >= 2:
                content = " ".join([text, data_test, element_id, name, aria_label])
                matched = sum(
                    1 for pw in product_words if pw in content or pw.replace(" ", "") in content.replace(" ", "")
                )
                if matched >= max(1, len(product_words) // 2):
                    return True

        # Default: accept
        return True
