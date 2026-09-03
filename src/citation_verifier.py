"""16b Phase 3 — Citation attachment and verification.

Implements the hybrid attribution mechanism from the spec:
- **Deterministic paste path:** the criterion IS a line of the user's own
  text → automatic line citation (no LLM).
- **Document mode path:** LLM proposes verbatim quotes per criterion;
  deterministic code verifies every quote (normalized substring match).
  Unverified quotes → search all pages → found → fix citation;
  not found → unresolved ⚠.

Design decisions (D3, D4, D6, D7, D8, D9, D12):
- D3: Hybrid attribution — LLM proposes, code verifies. No tuning knob.
- D4: Trust anchors in the quote, not the page number.
- D6: Every citation stores the chunk's dedup_key.
- D7: Bounded quotes (~240 chars), code-enforced.
- D8: Capped justification (~400 chars), code-enforced.
- D9: Unresolved = advisory, per-figure precision, never blocking.
- D12: director.py pass-through carries the new fields.
"""

from __future__ import annotations

import logging
from typing import Any

from src.rag_store import DocChunk
from src.source_refs import (
    MAX_JUSTIFICATION_CHARS,
    MAX_QUOTE_CHARS,
    SourceRef,
    normalize_for_quote_match,
    verify_quote,
)

logger = logging.getLogger(__name__)


def attach_paste_citations(
    criteria: list[Any],
    source_text: str,
) -> list[Any]:
    """Attach automatic line citations to criteria from the paste path.

    The deterministic paste path (user provides numbered criteria) needs no
    LLM — the criterion IS the line. Each criterion gets a `SourceRef`
    with `kind="cited"` and the verbatim line as the quote.

    Args:
        criteria: List of Criterion objects (from _criteria_from_text).
        source_text: The full pasted/typed requirements text.

    Returns:
        The same criteria list, with `source_refs` populated for each.
    """
    for criterion in criteria:
        # Find the criterion's source line in the text
        source_line = criterion.source_text or criterion.description
        # Truncate to MAX_QUOTE_CHARS (D7)
        quote = source_line[:MAX_QUOTE_CHARS]

        ref = SourceRef(
            doc="user-input",
            page_pdf=0,
            page_label="",
            heading="",
            quote=quote,
            route="text",
            dedup_key="",
            kind="cited",
        )
        criterion.source_refs = [ref]

    return criteria


def verify_document_citations(
    criteria: list[Any],
    page_chunks: list[DocChunk],
    llm_citations: dict[str, list[dict[str, Any]]],
) -> list[Any]:
    """Verify LLM-proposed citations against page-tagged document chunks.

    The hybrid mechanism (D3):
    1. LLM emits, per criterion, one or more citations each containing a
       verbatim quote from the page-tagged material.
    2. Deterministic code verifies every quote:
       - Quote found in the cited page's text → citation stands.
       - Quote not found on the cited page → search ALL pages → found →
         fix the citation (log correction); not found → unresolved ⚠.
       - No citation emitted by the LLM → unresolved.

    Args:
        criteria: List of Criterion objects.
        page_chunks: Page-tagged DocChunks from ingest_pdf_page_aware.
        llm_citations: Mapping of criterion ref → list of citation dicts,
            each with keys: "doc", "page", "quote", "heading", "route".

    Returns:
        The criteria list with `source_refs` and `justification` populated.
    """
    # Build page lookup: page index → chunk text
    page_text_map: dict[tuple[str, int], str] = {}
    for chunk in page_chunks:
        key = (chunk.source, chunk.page)
        page_text_map[key] = chunk.text

    # Build full text per doc for all-page search
    doc_full_text: dict[str, str] = {}
    for chunk in page_chunks:
        doc_full_text.setdefault(chunk.source, "")
        doc_full_text[chunk.source] += chunk.text + "\n"

    # Build dedup_key lookup: (source, page) → dedup_key
    dedup_map: dict[tuple[str, int], str] = {}
    for chunk in page_chunks:
        dedup_map[(chunk.source, chunk.page)] = chunk.dedup_key

    for criterion in criteria:
        ref_id = criterion.ref
        llm_refs = llm_citations.get(ref_id, [])

        source_refs: list[SourceRef] = []

        if not llm_refs:
            # No citation emitted by LLM → unresolved (D9)
            source_refs.append(
                SourceRef(
                    doc="",
                    kind="unresolved",
                )
            )
        else:
            for llm_ref in llm_refs:
                quote = llm_ref.get("quote", "")
                doc = llm_ref.get("doc", "")
                page = int(llm_ref.get("page", 0) or 0)
                heading = llm_ref.get("heading", "")
                route = llm_ref.get("route", "text")

                if not quote:
                    # Empty quote → unresolved
                    source_refs.append(
                        SourceRef(
                            doc=doc,
                            page_pdf=page,
                            heading=heading,
                            route=route,
                            kind="unresolved",
                        )
                    )
                    continue

                # Step 1: Verify quote on the cited page
                page_key = (doc, page)
                page_text = page_text_map.get(page_key, "")
                verified = verify_quote(quote, page_text)

                corrected_page = page
                if not verified:
                    # Step 2: Search ALL pages of the doc
                    full_text = doc_full_text.get(doc, "")
                    if verify_quote(quote, full_text):
                        # Found in the doc but not on the cited page → fix
                        corrected_page = _find_page_for_quote(
                            quote,
                            page_chunks,
                            doc,
                        )
                        logger.info(
                            "Citation corrected: %s — page %d → %d",
                            ref_id,
                            page,
                            corrected_page,
                        )
                        verified = True

                if verified:
                    # Truncate quote to MAX_QUOTE_CHARS (D7)
                    bounded_quote = quote[:MAX_QUOTE_CHARS]
                    source_refs.append(
                        SourceRef(
                            doc=doc,
                            page_pdf=corrected_page,
                            page_label="",
                            heading=heading,
                            quote=bounded_quote,
                            route=route,
                            dedup_key=dedup_map.get((doc, corrected_page), ""),
                            kind="cited",
                        )
                    )
                else:
                    # Not found anywhere → unresolved ⚠ (D9)
                    source_refs.append(
                        SourceRef(
                            doc=doc,
                            page_pdf=page,
                            heading=heading,
                            route=route,
                            kind="unresolved",
                        )
                    )

        criterion.source_refs = source_refs

        # Justification (D8): only generated when citations verify
        has_verified = any(not r.is_unresolved for r in source_refs)
        if has_verified:
            # Build a short justification from the verified citations
            just_parts = []
            for r in source_refs:
                if not r.is_unresolved and r.quote:
                    loc = f"{r.doc} p.{r.page_pdf}" if r.page_pdf > 0 else r.doc
                    just_parts.append(f'{loc}: "{r.quote[:80]}"')
            justification = "; ".join(just_parts[:3])
            # Cap at MAX_JUSTIFICATION_CHARS (D8)
            criterion.justification = justification[:MAX_JUSTIFICATION_CHARS]
        else:
            # Unresolved → no justification, just the ⚠ (D9)
            criterion.justification = ""

    return criteria


def _find_page_for_quote(
    quote: str,
    page_chunks: list[DocChunk],
    doc: str,
) -> int:
    """Find the page index where a quote was found (for correction)."""
    normalized_quote = normalize_for_quote_match(quote)
    for chunk in page_chunks:
        if chunk.source != doc:
            continue
        if normalized_quote in normalize_for_quote_match(chunk.text):
            return chunk.page
    return 0


def build_llm_citation_prompt(
    criterion: Any,
    page_chunks: list[DocChunk],
) -> str:
    """Build the LLM prompt for citation extraction (D3 hybrid mechanism).

    The LLM must emit, per criterion, one or more citations each containing
    a **verbatim quote** from the page-tagged material. The prompt includes
    the criterion description and a snippet of each relevant page.

    Args:
        criterion: The Criterion to find citations for.
        page_chunks: Page-tagged DocChunks (used to build page snippets).

    Returns:
        The LLM prompt string.
    """
    # Build page snippets (limit to ~200 chars per page for prompt size)
    page_snippets: list[str] = []
    for chunk in page_chunks:
        snippet = chunk.text[:200].replace("\n", " ")
        page_snippets.append(f"[{chunk.source} p.{chunk.page}] {snippet}")

    # Limit to 10 page snippets to control prompt size
    snippets_text = "\n".join(page_snippets[:10])

    prompt = (
        f"Find the source of this test criterion in the document pages below.\n\n"
        f"Criterion: {criterion.description}\n\n"
        f"Document pages (snippets):\n{snippets_text}\n\n"
        f"Respond with JSON. For each citation, provide a VERBATIM quote "
        f"(copy the exact words from the page, do not paraphrase). "
        f"If you cannot find a source, return an empty list.\n\n"
        f'Format: {{"citations": [{{"doc": "filename", "page": 1, '
        f'"quote": "exact verbatim text", "heading": "section name", '
        f'"route": "text"}}]}}\n'
    )
    return prompt
