"""16b Phase 4 — Citation surfaces and rendering.

Provides the rendering functions for all three surfaces (D10):
1. **Test-file ``# Source:`` comments** — the artifact users keep and share
2. **Living Test Plan citation cards** — data for Streamlit/CLI display
3. **CLI debug query** — follows the ``scripts/debug.py`` pattern

One rule across all three: an unresolved criterion renders the ⚠ everywhere,
never silently omitted.

PRIVACY_MODE (D7): pointer-only citations in exports (doc + page + heading +
hash, no quote text). Default off.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.pipeline_state import Criterion

logger = logging.getLogger(__name__)


def render_source_comments(
    criteria: list[Criterion],
    *,
    privacy_mode: bool = False,
) -> str:
    """Render ``# Source:`` comments for the exported test file.

    This is the primary surface — the artifact users keep and share.
    Works for CLI-only users; plain text.

    Args:
        criteria: List of Criterion objects (with source_refs populated).
        privacy_mode: If True, pointer-only (no quote text) — D7.

    Returns:
        Multi-line string of ``# Source:`` comments, one block per criterion
        that has source_refs. Criteria without source_refs (paste path with
        no document) produce no comments.

    Example output::

        # TC01.03: Boundary — max claim amount
        #   Source: policy.pdf, PDF p.9 (printed '5') [OCR] — "The maximum claim is £5,000"
        #   Because: Doc p.9 states max £5,000; Doc p.14 states Y = X + £300
        # TC01.04: Boundary — unknown increment
        #   ⚠ policy.pdf: no source found
    """
    lines: list[str] = []

    for criterion in criteria:
        if not criterion.source_refs:
            continue

        # Header line with criterion ref and description
        desc_part = f": {criterion.description}" if criterion.description else ""
        lines.append(f"# {criterion.ref}{desc_part}")

        # Citation lines
        for ref in criterion.source_refs:
            comment = f"#   {ref.display(privacy_mode=privacy_mode)}"
            lines.append(comment)

        # Justification line (only when present)
        if criterion.justification and not privacy_mode:
            lines.append(f"#   Because: {criterion.justification}")

        # Blank line between criteria blocks
        lines.append("")

    return "\n".join(lines).rstrip() + "\n" if lines else ""


def render_citation_cards(
    criteria: list[Criterion],
    *,
    privacy_mode: bool = False,
) -> list[dict[str, Any]]:
    """Render citation card data for the Living Test Plan (Streamlit/CLI).

    Catches the question *before* generation, where it's cheapest to act on.
    Returns structured data that the UI layer renders as expandable cards.

    Args:
        criteria: List of Criterion objects (with source_refs populated).
        privacy_mode: If True, pointer-only (no quote text) — D7.

    Returns:
        List of dicts, one per criterion that has source_refs. Each dict:
        - ``ref``: criterion ref (e.g. "TC01.03")
        - ``description``: criterion description
        - ``citations``: list of citation display strings
        - ``justification``: the "because" string (empty for unresolved)
        - ``has_unresolved``: True if any citation is ⚠
        - ``privacy_mode``: whether this was rendered in privacy mode
    """
    cards: list[dict[str, Any]] = []

    for criterion in criteria:
        if not criterion.source_refs:
            continue

        citations = [ref.display(privacy_mode=privacy_mode) for ref in criterion.source_refs]
        has_unresolved = any(ref.is_unresolved for ref in criterion.source_refs)

        cards.append(
            {
                "ref": criterion.ref,
                "description": criterion.description,
                "citations": citations,
                "justification": "" if privacy_mode else criterion.justification,
                "has_unresolved": has_unresolved,
                "privacy_mode": privacy_mode,
            }
        )

    return cards


def render_cli_debug(
    criteria: list[Criterion],
    criterion_ref: str,
    *,
    privacy_mode: bool = False,
) -> str:
    """Render a CLI debug query for a single criterion's citations.

    Follows the ``scripts/debug.py`` pattern — a human-readable dump of all
    citations for one criterion, suitable for terminal output.

    Args:
        criteria: Full list of Criterion objects.
        criterion_ref: The ref to look up (e.g. "TC01.03").
        privacy_mode: If True, pointer-only (no quote text) — D7.

    Returns:
        Multi-line string with the criterion's citation details.
        Returns an error message if the criterion is not found.
    """
    criterion = None
    for c in criteria:
        if c.ref == criterion_ref:
            criterion = c
            break

    if criterion is None:
        return f"Error: criterion '{criterion_ref}' not found"

    if not criterion.source_refs:
        return f"{criterion.ref}: no source references (paste path or no document)"

    lines: list[str] = [
        f"=== Citations for {criterion.ref} ===",
        f"Description: {criterion.description}",
        f"Type: {criterion.condition_type}",
        f"Priority: {criterion.priority}",
        "",
        "Citations:",
    ]

    for i, ref in enumerate(criterion.source_refs, start=1):
        status = "⚠ UNRESOLVED" if ref.is_unresolved else "✓ CITED"
        lines.append(f"  [{i}] {status}")
        if not ref.is_unresolved:
            lines.append(f"      Doc: {ref.doc}")
            if ref.page_pdf > 0:
                page_str = f"p.{ref.page_pdf}"
                if ref.page_label:
                    page_str += f" (printed '{ref.page_label}')"
                lines.append(f"      Page: {page_str}")
            if ref.heading:
                lines.append(f"      Heading: {ref.heading}")
            if ref.quote and not privacy_mode:
                lines.append(f'      Quote: "{ref.quote}"')
            lines.append(f"      Route: {ref.route}")
            if ref.dedup_key:
                lines.append(f"      Dedup: {ref.dedup_key[:16]}…")
        else:
            if ref.doc:
                lines.append(f"      Doc: {ref.doc}")

    if criterion.justification and not privacy_mode:
        lines.append("")
        lines.append("Justification (generator's reasoning):")
        lines.append(f"  {criterion.justification}")

    lines.append("")
    lines.append("Trust boundary:")
    lines.append("  Quotes = Evidence (verified)")
    lines.append("  Justification = Generator's reasoning (unverified text)")

    return "\n".join(lines)


def render_export_note(*, privacy_mode: bool = False) -> str:
    """Render the self-documenting export note (D7).

    Exported evidence carries a note explaining whether quotes are included
    and how to omit them.

    Args:
        privacy_mode: Current privacy mode state.

    Returns:
        The note string.
    """
    if privacy_mode:
        return "Source pointers included (quotes omitted — PRIVACY_MODE=1)."
    return "Source quotes included; set PRIVACY_MODE=1 to omit quotes."
