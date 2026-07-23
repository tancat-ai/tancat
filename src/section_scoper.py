"""Section-aware element scoping for placeholder resolution.

Detects page sections from heading elements and assigns each element to a
section based on document order (``_element_box_index``).  At resolution
time, the placeholder description is parsed for a section hint (e.g.
``"on account page"``, ``"in drivers section"``) and the candidate
haystack is filtered to elements belonging to that section.

Falls back to the full element list when no section hint is found in the
description — zero regressions on sites without sectioned content.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Section:
    """A contiguous region of elements bounded by headings."""

    name: str  # e.g. "Create Your Account"
    heading_role: str  # e.g. "h2"
    heading_index: int  # _element_box_index of the heading
    element_indices: list[int]  # _element_box_index values of child elements


# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------

# Roles that count as section boundaries — h1 through h2.
# h3-h6 are too granular (they split subsections like payment options).
_BOUNDARY_ROLES: frozenset[str] = frozenset({"h1", "h2"})


def _is_section_boundary(element: dict[str, Any]) -> bool:
    """Return True if the element is a section-heading boundary."""
    return str(element.get("role", "")).lower() in _BOUNDARY_ROLES


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------


def detect_sections(elements: list[dict[str, Any]]) -> list[Section]:
    """Detect page sections from heading elements.

    Scans elements sorted by ``_element_box_index`` and groups elements
    under the nearest preceding heading (h1/h2).  Elements before the
    first heading are assigned to a synthetic ``"page"`` section.

    Args:
        elements: List of scraped element dicts (as from the accessibility
            scraper), sorted by document order.

    Returns:
        List of ``Section`` objects, ordered by position on the page.
        Returns an empty list if no headings are found.
    """
    if not elements:
        return []

    # Sort by document order
    sorted_elems = sorted(
        elements,
        key=lambda e: e.get("_element_box_index", 0),
    )

    # Find boundary headings
    headings: list[tuple[int, dict[str, Any]]] = []
    for elem in sorted_elems:
        if _is_section_boundary(elem):
            idx = elem.get("_element_box_index", 0)
            headings.append((idx, elem))

    if not headings:
        return []

    # Build sections: each heading owns elements between itself and the next heading.
    # For the last heading, it owns all remaining elements after it.
    # Elements before the first heading are assigned to the first heading
    # (not a synthetic section) because on many pages (e.g. SPAs) form
    # fields appear before their section heading in the accessibility tree.
    sections: list[Section] = []

    for i, (heading_idx, heading_elem) in enumerate(headings):
        next_heading_idx = headings[i + 1][0] if i + 1 < len(headings) else float("inf")  # type: ignore[list-item]
        # First heading: owns from start up to next heading.
        # Other headings: own from their index up to next heading.
        lower_bound = -1 if i == 0 else heading_idx

        child_indices: list[int] = []
        for elem in sorted_elems:
            elem_idx = elem.get("_element_box_index", 0)
            if lower_bound < elem_idx < next_heading_idx and not _is_section_boundary(elem):
                child_indices.append(elem_idx)

        sections.append(
            Section(
                name=heading_elem.get("text", "").strip(),
                heading_role=heading_elem.get("role", "h2"),
                heading_index=heading_idx,
                element_indices=child_indices,
            )
        )

    logger.debug("Detected %d sections from %d elements", len(sections), len(elements))
    return sections


# ---------------------------------------------------------------------------
# Section name matching
# ---------------------------------------------------------------------------

# Regex patterns to extract section hints from placeholder descriptions.
# Matches: "on account page", "in drivers section", "under vehicles", etc.
_SECTION_HINT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bon\s+([^,]+?)\s+page\b", re.IGNORECASE),
    re.compile(r"\bin\s+([^,]+?)\s+section\b", re.IGNORECASE),
    re.compile(r"\bunder\s+([^,]+?)\s+section\b", re.IGNORECASE),
    re.compile(r"\bin\s+the\s+([^,]+?)\s+section\b", re.IGNORECASE),
    re.compile(r"\bon\s+the\s+([^,]+?)\s+page\b", re.IGNORECASE),
]

# Words to strip from extracted hints.
_HINT_STOP_WORDS: frozenset[str] = frozenset({"the", "a", "an"})

# Normalise section names for fuzzy matching: strip emojis, lowercase, collapse whitespace.
_NORMALISE_RE = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F]"
)


def _normalise_name(name: str) -> str:
    """Normalise a section name for comparison."""
    name = _NORMALISE_RE.sub("", name).lower().strip()
    name = re.sub(r"\s+", " ", name)
    return name


def _extract_section_hint(description: str) -> str | None:
    """Extract a section hint from a placeholder description.

    Returns normalised section name (e.g. ``"account"``) or ``None``.
    """
    for pattern in _SECTION_HINT_PATTERNS:
        match = pattern.search(description)
        if match:
            raw = match.group(1).strip()
            # Strip leading stop words ("the", "a", "an")
            parts = raw.split()
            if parts and parts[0].lower() in _HINT_STOP_WORDS and len(parts) > 1:
                raw = " ".join(parts[1:])
            normalised = _normalise_name(raw)
            if normalised:
                return normalised
    return None


def _match_section_hint(
    hint: str,
    sections: list[Section],
) -> str | None:
    """Match a normalised hint against detected section names.

    Returns the original (unnormalised) section name, or ``None``.
    Uses substring matching: hint must be contained in the section name
    or vice-versa.

    Args:
        hint: Normalised section hint from the placeholder description.
        sections: List of detected ``Section`` objects.
    """
    if not hint:
        return None

    hint_words = set(hint.split())

    # Exact match first
    for section in sections:
        if _normalise_name(section.name) == hint:
            return section.name

    # Substring / word overlap match
    for section in sections:
        section_norm = _normalise_name(section.name)
        if hint in section_norm or section_norm in hint:
            return section.name

    # Word overlap: at least one non-trivial word matches
    for section in sections:
        section_words = set(_normalise_name(section.name).split())
        overlap = hint_words & section_words
        # Filter out very common words
        meaningful_overlap = overlap - {"the", "and", "your", "my", "a", "an"}
        if meaningful_overlap:
            return section.name

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scope_elements(
    description: str,
    all_elements: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    """Filter elements to the section referenced in a placeholder description.

    Extracts a section hint from the description (e.g. "on account page"),
    detects page sections from headings, and returns only elements belonging
    to the matched section.

    Falls back to the full element list when:
    - No section hint is found in the description
    - No headings are detected on the page
    - The hint doesn't match any section

    Args:
        description: Placeholder description (e.g. "Next button on account page").
        all_elements: All scraped elements for the page.

    Returns:
        Tuple of ``(scoped_elements, matched_section_name)``.
        ``matched_section_name`` is ``None`` when full list is returned.
    """
    hint = _extract_section_hint(description)
    if not hint:
        return all_elements, None

    sections = detect_sections(all_elements)
    if not sections:
        return all_elements, None

    matched_name = _match_section_hint(hint, sections)
    if not matched_name:
        logger.debug(
            "Section hint '%s' from description '%s' did not match any section",
            hint,
            description,
        )
        return all_elements, None

    # Build a set of element indices for the matched section
    section = next((s for s in sections if s.name == matched_name), None)
    if section is None:
        return all_elements, None

    section_indices = frozenset(section.element_indices)

    # Also include the heading itself
    section_indices = section_indices | frozenset({section.heading_index})

    scoped = [e for e in all_elements if e.get("_element_box_index", -1) in section_indices]

    logger.debug(
        "Scoped '%s' to section '%s': %d → %d elements",
        description,
        matched_name,
        len(all_elements),
        len(scoped),
    )

    return scoped, matched_name


def build_element_to_section_map(
    elements: list[dict[str, Any]],
) -> dict[int, str]:
    """Build a mapping from element index to section name.

    Useful for debugging or logging which section each resolved element
    belongs to.

    Args:
        elements: All scraped elements for the page.

    Returns:
        Dict mapping ``_element_box_index`` → section name.
    """
    sections = detect_sections(elements)
    if not sections:
        return {}

    mapping: dict[int, str] = {}
    for section in sections:
        for idx in section.element_indices:
            mapping[idx] = section.name
        mapping[section.heading_index] = section.name

    return mapping
