"""ARIA snapshot parser — converts Playwright's `aria_snapshot()` YAML output
into the same element dict format used by the rest of the pipeline.

Usage::

    snapshot = page.aria_snapshot(boxes=True)
    elements = parse_aria_snapshot(snapshot)

The parser handles the full YAML grammar produced by Playwright:
    - heading "name" [level=N] [box=x,y,w,h]
    - textbox "name" [box=x,y,w,h]:
      - /placeholder: value
      - text: value
    - combobox "name" [box=x,y,w,h]:
      - option "name" [selected] [box=x,y,w,h]
    - button "name" [box=x,y,w,h]
    - link "name" [box=x,y,w,h]:
      - /url: href
    - radio "name" [box=x,y,w,h]
    - checkbox "name" [box=x,y,w,h]
    - group "name" [box=x,y,w,h]:
    - text: plain text
"""

from __future__ import annotations

import re
from typing import Any


def parse_aria_snapshot(yaml_text: str) -> list[dict[str, Any]]:
    """Parse Playwright's aria_snapshot() YAML into element dicts.

    Args:
        yaml_text: Raw output from ``page.aria_snapshot(boxes=True)``.

    Returns:
        List of element dicts in depth-first order, with the same field
        names as the existing BS4-based scraper output.
    """
    elements: list[dict[str, Any]] = []
    if not yaml_text or not yaml_text.strip():
        return elements

    lines = yaml_text.split("\n")
    # Stack of (indent_level, element_dict) for tracking parent context
    stack: list[tuple[int, dict[str, Any] | None]] = [(-1, None)]

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            continue

        # Compute indentation (2 spaces per level)
        indent = _line_indent(line)

        # Pop stack until we find the parent at a lower indentation
        while stack and stack[-1][0] >= indent:
            stack.pop()

        # Parse the line into a flat element dict
        element = _parse_aria_line(stripped.lstrip())

        if element is None:
            # Check if it's a child property (/placeholder:, /url:, text:, etc.)
            clean = stripped.lstrip()
            if _is_child_property(clean):
                _apply_child_property(clean, stack[-1][1] if stack else None)
                continue
            # Handle "text: value" — could be child of input OR standalone text
            m = re.match(r"-\s*text:\s*(.*)", clean)
            if m:
                val = m.group(1).strip()
                parent = stack[-1][1] if stack else None
                if parent and parent.get("role") in {"textbox", "combobox"}:
                    # Text child of input — store as value
                    parent["value"] = val
                elif val and len(val) >= 3:
                    # Standalone text element
                    elem = _build_element(role="text", name=val, text=val, attrs={})
                    elements.append(elem)
                    stack.append((indent, elem))
                continue

        if element is None:
            continue

        # B-032: If text child of form control, apply as value not element
        parent = stack[-1][1] if stack else None
        if element.get("role") == "text" and parent and parent.get("role") in {"textbox", "combobox"}:
            val = element.get("text", "")
            if val:
                parent["value"] = val
            continue

        # Link to parent
        element["_parent"] = parent

        elements.append(element)
        stack.append((indent, element))

    return elements


# ── Line parsing ────────────────────────────────────────────────


def _line_indent(line: str) -> int:
    """Return the indentation level (2 spaces = 1 level)."""
    spaces = len(line) - len(line.lstrip(" "))
    return spaces // 2


def _is_child_property(stripped: str) -> bool:
    """Check if line is a child property (/placeholder:, /url:, /checked:, /selected:).

    These always belong to the parent element.  ``text: value`` is handled
    separately — it can be either a standalone text element or an input child.
    """
    stripped_clean = stripped.lstrip()
    return bool(re.match(r"-\s*/\w+:", stripped_clean))


def _apply_child_property(stripped: str, parent: dict[str, Any] | None) -> None:
    """Apply a child property line to its parent element."""
    if parent is None:
        return

    # Extract /property: value
    m = re.match(r"-\s*/(\w+):\s*(.*)", stripped)
    if m:
        prop = m.group(1)
        value = m.group(2).strip()
        if prop == "placeholder":
            parent["placeholder"] = value
        elif prop == "url":
            parent["href"] = value
        elif prop == "checked":
            parent["checked"] = True
        elif prop == "selected":
            parent["selected"] = True
        return

    # Extract text: value (child text of input elements)
    m = re.match(r"-\s*text:\s*(.*)", stripped)
    if m and m.group(1).strip():
        # Input value — store as value
        parent["value"] = m.group(1).strip()


def _parse_aria_line(stripped: str) -> dict[str, Any] | None:
    """Parse a single ARIA YAML line into an element dict.

    Returns None for non-element lines (child properties like /placeholder:, /url:).
    """
    # Skip child property lines (/placeholder:, /url:, /checked:, /selected:)
    if _is_child_property(stripped):
        return None

    # Remove leading "- "
    content = re.sub(r"^-\s+", "", stripped)

    # Extract attributes in [key=value] brackets (including [box=x,y,w,h])
    attrs: dict[str, str] = {}
    attr_pattern = re.findall(r"\[([^\]]+)\]", content)
    for attr_str in attr_pattern:
        for pair in attr_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, val = pair.split("=", 1)
                attrs[key.strip()] = val.strip()
            else:
                # Flag attribute like [selected], [checked]
                attrs[pair.strip()] = "true"

    # Remove attribute brackets for role/name/text parsing
    content_no_attrs = re.sub(r"\s*\[[^\]]*\]", "", content)

    # Extract text after colon ("role [attrs]: text content" pattern)
    text_after_colon = ""
    if ":" in content_no_attrs:
        colon_idx = content_no_attrs.find(":")
        before = content_no_attrs[:colon_idx].rstrip()
        after = content_no_attrs[colon_idx + 1 :].strip()
        content_no_attrs = before
        if after:
            text_after_colon = after

    has_children = bool(text_after_colon == "") and stripped.rstrip().endswith(":")

    # Split into parts: first word is role, rest may contain quoted name
    parts = content_no_attrs.split(None, 1)
    if not parts:
        return None

    role = parts[0].lower()

    # Extract quoted name from remaining text
    name = ""
    plain_text = text_after_colon
    if len(parts) > 1:
        remainder = parts[1]
        name_match = re.match(r'"([^"]*)"', remainder)
        if name_match:
            name = name_match.group(1)
            if not plain_text:
                plain_text = remainder[name_match.end() :].strip()
        elif not plain_text:
            plain_text = remainder

    # For "text:" lines without a quoted name, use plain_text as the text
    if role == "text" and not name:
        if not plain_text or len(plain_text) < 3:
            return None
        return _build_element(role=role, name=plain_text, text=plain_text, attrs=attrs)

    # Map ARIA role to our scraper role format
    role_map: dict[str, str] = {
        "heading": "heading",
        "textbox": "textbox",
        "combobox": "combobox",
        "button": "button",
        "link": "link",
        "radio": "radio",
        "checkbox": "checkbox",
        "option": "option",
        "group": "group",
        "generic": "generic",
        "img": "img",
        "list": "list",
        "listitem": "listitem",
        "region": "region",
        "navigation": "navigation",
        "banner": "banner",
        "main": "main",
        "contentinfo": "contentinfo",
        "spinbutton": "spinbutton",
        "searchbox": "searchbox",
        "slider": "slider",
        "switch": "switch",
        "tab": "tab",
        "tabpanel": "tabpanel",
        "dialog": "dialog",
        "alert": "alert",
        "status": "status",
        "log": "log",
        "timer": "timer",
        "progressbar": "progressbar",
        "separator": "separator",
        "text": "text",
    }
    scraper_role = role_map.get(role, role)

    return _build_element(
        role=scraper_role, ar_role=role, name=name, text=plain_text, attrs=attrs, has_children=has_children
    )


def _build_element(
    *,
    role: str,
    ar_role: str = "",
    name: str = "",
    text: str = "",
    attrs: dict[str, str] | None = None,
    has_children: bool = False,
) -> dict[str, Any]:
    """Build an element dict in the standard scraper format."""
    if attrs is None:
        attrs = {}

    # Build CSS selector (best effort from available info)
    selector = _build_selector(role, name, attrs)

    # Extract bounding box
    bbox = _parse_box(attrs.get("box", ""))

    return {
        "selector": selector,
        "text": text or name,
        "role": role,
        "computed_role": ar_role or role,
        "accessible_name": name,
        "href": attrs.get("href", ""),
        "title": "",
        "aria_label": "",
        "data_test": "",
        "name": "",
        "id": "",
        "classes": "",
        "value": "",
        "placeholder": attrs.get("placeholder", ""),
        "is_visible": True,
        "in_modal": False,
        "_aria_level": attrs.get("level", ""),
        "_bbox": bbox,
        "_has_children": has_children,
    }


def _parse_box(box_str: str) -> dict[str, float] | None:
    """Parse '[box=x,y,w,h]' style bounding box."""
    if not box_str:
        return None
    parts = box_str.split(",")
    if len(parts) == 4:
        try:
            return {
                "x": float(parts[0]),
                "y": float(parts[1]),
                "width": float(parts[2]),
                "height": float(parts[3]),
            }
        except ValueError, TypeError:
            return None
    return None


def _build_selector(role: str, name: str, attrs: dict[str, str]) -> str:
    """Build a best-effort CSS selector from ARIA role and name."""
    # Prefer getByRole-compatible notation
    if name:
        # Use role[name="name"] as canonical form
        return f'{role}[name="{name}"]'

    # For elements without name but with a specific tag
    if attrs.get("level"):
        return f"h{attrs['level']}"

    return role
