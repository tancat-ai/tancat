"""Enrich scraped DOM elements with computed accessibility names from the browser a11y tree.

The browser's `page.accessibility.snapshot()` returns a tree of accessible nodes with
computed names derived from ARIA relationships (aria-labelledby, aria-describedby),
parent label context, SVG <title> children, and implicit roles.  This module merges
those computed names back into the element records produced by PageScraper so that
PlaceholderResolver has more text signals when matching placeholders like
`{{CLICK:View Cart}}` against an icon-only button whose accessible name is "View Cart"
but whose raw HTML attributes contain no such text.

Enrichment is additive only — it never removes or overwrites existing data.  If a node
cannot be matched, the element is left unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AccessibilityEnricher:
    """Merge computed accessible names from an a11y tree into scraped elements."""

    __test__ = False

    # Roles considered "interactive" for document-order matching
    INTERACTIVE_ROLES = {
        "button",
        "link",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "radio",
        "checkbox",
        "switch",
        "textbox",
        "searchbox",
        "combobox",
        "listbox",
        "slider",
        "spinbutton",
        "tab",
        "tabpanel",
    }

    @staticmethod
    def enrich(elements: list[dict[str, Any]], a11y_tree: dict[str, Any]) -> list[dict[str, Any]]:
        """Merge computed accessible names from a11y tree into scraped elements.

        Matching strategy (in priority order):
        1. **Role + name** — if an element has text and role that match an a11y node's
           name and role, link them.
        2. **Document-order** — traverse both trees in document order, matching the Nth
           interactive element to the Nth interactive a11y node.
        3. **href** — link elements can be matched by their href value appearing in
           a11y properties.

        Args:
            elements: List of scraped element dicts (from PageScraper).
            a11y_tree: Root node from ``page.accessibility.snapshot()``.

        Returns:
            The same element list, mutated in place with enriched fields added.
        """
        if not elements or not a11y_tree:
            return elements

        # Flatten the a11y tree into a list of interactive nodes (document order)
        a11y_nodes = AccessibilityEnricher._flatten_a11y_tree(a11y_tree)
        if not a11y_nodes:
            return elements

        # Build lookup indices for role+name and href matching
        role_name_index = AccessibilityEnricher._build_role_name_index(a11y_nodes)
        href_index = AccessibilityEnricher._build_href_index(a11y_nodes)

        # Track which a11y nodes have been consumed (for document-order fallback)
        used_indices: set[int] = set()

        for element in elements:
            if element.get("accessible_name"):
                # Already enriched — skip
                continue

            matched = False

            # --- Strategy 1: Role + name matching ---
            a11y_node = AccessibilityEnricher._match_by_role_and_name(element, role_name_index, used_indices)
            if a11y_node is None:
                # --- Strategy 3: href matching (before document-order) ---
                a11y_node = AccessibilityEnricher._match_by_href(element, href_index, used_indices)

            if a11y_node is None:
                matched = False
            else:
                matched = True
                used_indices.add(id(a11y_node))

            # --- Strategy 2: Document-order matching (fallback) ---
            if not matched:
                a11y_node = AccessibilityEnricher._match_by_document_order(element, a11y_nodes, used_indices)
                if a11y_node is not None:
                    used_indices.add(id(a11y_node))

            # Apply enrichment from matched node
            if a11y_node is not None:
                AccessibilityEnricher._apply_enrichment(element, a11y_node)

        return elements

    # ------------------------------------------------------------------
    # Tree flattening
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_a11y_tree(node: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten the a11y tree into a document-order list of interactive nodes.

        Returns only nodes that have a meaningful name or are interactive by role.
        """
        result: list[dict[str, Any]] = []
        children = node.get("children", [])
        # Also check legacy key name used by older Playwright versions
        if not children:
            children = node.get("childProperties", [])

        for child in children:
            role = (child.get("role") or "").lower()
            name = (child.get("name") or "").strip()

            # Include nodes that are interactive OR have a meaningful accessible name
            if role in AccessibilityEnricher.INTERACTIVE_ROLES or name:
                result.append(child)

            # Recurse into children
            result.extend(AccessibilityEnricher._flatten_a11y_tree(child))

        return result

    # ------------------------------------------------------------------
    # Lookup indices
    # ------------------------------------------------------------------

    @staticmethod
    def _build_role_name_index(
        nodes: list[dict[str, Any]],
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """Build an index of (role, name) -> list of a11y nodes."""
        index: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for node in nodes:
            role = (node.get("role") or "").lower()
            name = (node.get("name") or "").strip().lower()
            if not name:
                continue
            key = (role, name)
            index.setdefault(key, []).append(node)
        return index

    @staticmethod
    def _build_href_index(
        nodes: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Build an index of href value -> list of a11y nodes.

        Hrefs appear in the `properties` array of link nodes.
        """
        index: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            props = node.get("properties", []) + node.get("childProperties", [])
            for prop in props:
                if isinstance(prop, dict) and (prop.get("name") or "").lower() == "url":
                    href_value = (prop.get("value") or "").strip().lower()
                    if href_value:
                        index.setdefault(href_value, []).append(node)
        return index

    # ------------------------------------------------------------------
    # Matching strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _match_by_role_and_name(
        element: dict[str, Any],
        role_name_index: dict[tuple[str, str], list[dict[str, Any]]],
        used_indices: set[int],
    ) -> dict[str, Any] | None:
        """Strategy 1: match scraped element to a11y node by role + accessible name.

        The element's visible text is compared against the a11y node's computed name.
        A role comparison narrows false positives.
        """
        element_text = (element.get("text") or "").strip().lower()
        element_role = (element.get("role") or "").strip().lower()

        if not element_text:
            return None

        # Try exact role + name match first
        key = (element_role, element_text)
        candidates = role_name_index.get(key)

        if candidates:
            for candidate in candidates:
                if id(candidate) not in used_indices:
                    return candidate

        # Fallback: try name-only match (ignore role) — useful when the scraped
        # role differs from the computed a11y role (e.g. raw "a" vs computed "link")
        for role_key, node_list in role_name_index.items():
            if role_key[1] == element_text:
                for candidate in node_list:
                    if id(candidate) not in used_indices:
                        return candidate

        return None

    @staticmethod
    def _match_by_href(
        element: dict[str, Any],
        href_index: dict[str, list[dict[str, Any]]],
        used_indices: set[int],
    ) -> dict[str, Any] | None:
        """Strategy 3: match link elements by their href value."""
        element_href = (element.get("href") or "").strip().lower()
        if not element_href:
            return None

        candidates = href_index.get(element_href)
        if candidates:
            for candidate in candidates:
                if id(candidate) not in used_indices:
                    return candidate

        # Partial href match (path-only comparison)
        from urllib.parse import urlparse

        parsed = urlparse(element_href)
        path = (parsed.path or "/").lower()
        for href_key, node_list in href_index.items():
            if path in href_key.lower():
                for candidate in node_list:
                    if id(candidate) not in used_indices:
                        return candidate

        return None

    @staticmethod
    def _match_by_document_order(
        element: dict[str, Any],
        a11y_nodes: list[dict[str, Any]],
        used_indices: set[int],
    ) -> dict[str, Any] | None:
        """Strategy 2: match by document position (fallback).

        This is intentionally last because ARIA flow relationships can reorder
        the accessibility tree relative to DOM order.  Role+name matching requires
        two signals to agree and is less likely to fire spuriously.
        """
        # Simple heuristic: find the first unused a11y node whose name has any
        # overlap with the element's text or selector.
        element_text = (element.get("text") or "").strip().lower()
        element_selector = (element.get("selector") or "").strip().lower()

        for node in a11y_nodes:
            if id(node) in used_indices:
                continue

            node_name = (node.get("name") or "").strip().lower()
            if not node_name:
                continue

            # Check if the a11y name appears in the element text or selector
            if node_name in element_text or node_name in element_selector:
                return node

        return None

    # ------------------------------------------------------------------
    # Enrichment application
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_enrichment(element: dict[str, Any], a11y_node: dict[str, Any]) -> None:
        """Apply computed fields from an a11y node to a scraped element.

        Rules:
        - ``accessible_name`` is added only if not already present (never overwrite).
        - ``computed_role`` is added unconditionally (a11y role may differ from raw attr).
        - ``aria_describedby`` text is resolved from the node's properties.
        """
        # Add accessible name — don't overwrite existing aria_label
        if not element.get("accessible_name"):
            a11y_name = (a11y_node.get("name") or "").strip()
            if a11y_name:
                element["accessible_name"] = a11y_name

        # Add computed role
        a11y_role = (a11y_node.get("role") or "").strip().lower()
        if a11y_role and a11y_role not in {"", "unknown"}:
            element["computed_role"] = a11y_role

        # Resolve aria-describedby / aria-labelledby text from properties.
        # Prefer describedby > labelledby > label (most specific first).
        props = a11y_node.get("properties", []) + a11y_node.get("childProperties", [])
        for preferred_name in ("describedby", "labelledby", "label"):
            if element.get("aria_describedby"):
                break
            for prop in props:
                if not isinstance(prop, dict):
                    continue
                prop_name = (prop.get("name") or "").lower()
                prop_value = (prop.get("value") or "").strip()
                if prop_name == preferred_name and prop_value:
                    element.setdefault("aria_describedby", prop_value)
