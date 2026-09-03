"""Test-to-Document Traceability — SourceRef data model (16b Phase 1).

Provides the ``SourceRef`` dataclass that carries provenance for every
criterion: which doc, which page, which heading, which exact quote,
via which parse route, pinned to which chunk version.

Design decisions (D1–D12 from ``FEATURE_SPEC_test_to_document_traceability.md``):

- **D4:** Trust anchors in the verified quote, not the page number.
  Both physical PDF page index and printed page label are stored.
- **D6:** Every citation stores the chunk's ``dedup_key`` — pins the
  citation to one chunk version (handles stale-lingering chunk versions).
- **D7:** Bounded quotes (~240 chars), code-enforced.
- **D9:** Unresolved = advisory, per-figure precision, never blocking.
- **D12:** ``SourceRef`` data model; ``director.py`` pass-through must
  carry the new fields.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Hard cap on quote length (characters). Code-enforced after verification.
MAX_QUOTE_CHARS: int = 240

#: Hard cap on justification length (characters). Code-enforced.
MAX_JUSTIFICATION_CHARS: int = 400


@dataclass
class SourceRef:
    """A single citation linking a criterion to a verified document location.

    ``kind`` is ``"cited"`` when the quote has been verified (found in the
    cited page's text via normalized substring match) and ``"unresolved"``
    when no source was found (advisory ⚠ signal, never blocking).

    Fields:
        doc: Document identity (filename).
        page_pdf: Physical PDF page index (1-indexed). 0 = not a PDF / unknown.
        page_label: Printed page label (e.g. "5"). "" if the page has no label.
        heading: Heading path at the cited location.
        quote: Verified verbatim span (≤ ~240 chars). Empty for unresolved.
        route: Parse route — "text" (PyMuPDF) | "ocr" (OCR fallback).
        dedup_key: Pins the citation to one chunk version (D6).
        kind: "cited" (verified) | "unresolved" (⚠ no source found).
    """

    doc: str = ""
    page_pdf: int = 0
    page_label: str = ""
    heading: str = ""
    quote: str = ""
    route: str = "text"  # "text" | "ocr"
    dedup_key: str = ""
    kind: str = "cited"  # "cited" | "unresolved"

    @property
    def is_unresolved(self) -> bool:
        """True if this citation is an unresolved ⚠ signal."""
        return self.kind == "unresolved"

    def display(self, *, privacy_mode: bool = False) -> str:
        """Render a human-readable citation string.

        Args:
            privacy_mode: If True, pointer-only (no quote text) — D7.

        Returns:
            A string like::

                Doc A, PDF p.9 (printed '5') [OCR] — "The maximum claim is £5,000"

            or (unresolved)::

                ⚠ Doc A: no source found

            or (privacy mode)::

                Doc A, PDF p.9 (printed '5') [text] (quote omitted — PRIVACY_MODE)
        """
        if self.is_unresolved:
            doc_part = f" {self.doc}" if self.doc else ""
            return f"⚠{doc_part}: no source found"

        # Build location part
        location = self.doc or "Unknown doc"
        if self.page_pdf > 0:
            location += f", PDF p.{self.page_pdf}"
            if self.page_label:
                location += f" (printed '{self.page_label}')"

        # Route tag
        route_tag = f" [{self.route}]" if self.route != "text" else ""

        # Quote or pointer-only
        if privacy_mode:
            quote_part = " (quote omitted — PRIVACY_MODE)"
        elif self.quote:
            # Truncate to MAX_QUOTE_CHARS if over cap
            q = self.quote[:MAX_QUOTE_CHARS]
            if len(self.quote) > MAX_QUOTE_CHARS:
                q += "…"
            quote_part = f' — "{q}"'
        else:
            quote_part = ""

        return f"{location}{route_tag}{quote_part}"

    def to_dict(self) -> dict[str, str]:
        """Serialize for checkpointing / export."""
        return {
            "doc": self.doc,
            "page_pdf": str(self.page_pdf),
            "page_label": self.page_label,
            "heading": self.heading,
            "quote": self.quote,
            "route": self.route,
            "dedup_key": self.dedup_key,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> SourceRef:
        """Deserialize from a checkpoint / export dict."""
        return cls(
            doc=data.get("doc", ""),
            page_pdf=int(data.get("page_pdf", 0) or 0),
            page_label=data.get("page_label", ""),
            heading=data.get("heading", ""),
            quote=data.get("quote", ""),
            route=data.get("route", "text"),
            dedup_key=data.get("dedup_key", ""),
            kind=data.get("kind", "cited"),
        )


def normalize_for_quote_match(text: str) -> str:
    """Normalize text for quote verification (D3 + threshold policy).

    v1 uses normalized exact match only (case / whitespace / quote-glyphs).
    No fuzzy fallback — a false unresolved is honest and visible; a fuzzy
    false resolved is a wrong pointer wearing a green tick.

    Normalizations:
        - Case-fold (lowercase)
        - Collapse all whitespace runs to single space
        - Strip
        - Normalize curly quotes to straight quotes
        - Normalize em/en dashes to hyphen
    """
    # Normalize curly quotes
    text = text.replace("\u201c", '"').replace("\u201d", '"')  # " "
    text = text.replace("\u2018", "'").replace("\u2019", "'")  # ' '
    # Normalize dashes
    text = text.replace("\u2014", "-").replace("\u2013", "-")  # — –
    # Case-fold
    text = text.casefold()
    # Collapse whitespace
    import re

    text = re.sub(r"\s+", " ", text).strip()
    return text


def verify_quote(quote: str, page_text: str) -> bool:
    """Verify a verbatim quote against a page's text.

    Args:
        quote: The verbatim span to verify.
        page_text: The full text of the cited page.

    Returns:
        True if the quote is found in the page text (normalized substring match).
    """
    if not quote or not page_text:
        return False
    return normalize_for_quote_match(quote) in normalize_for_quote_match(page_text)
