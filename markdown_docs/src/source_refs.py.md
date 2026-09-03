# `src/source_refs.py`

## High-Level Purpose

The **citation data model** for Test-to-Document Traceability (16b Phase 1).
Defines `SourceRef` — the "citation slip" that carries *where* a generated
figure came from: which document, which page, which heading, the exact quote,
the parse route, and whether it was **verified** or **unresolvable**.

This is the vocabulary every other 16b module shares. Phase 2 tags document
chunks with its fields, Phase 3 creates `SourceRef` instances, Phase 4 calls
`ref.display()`. The trust mechanism — `verify_quote()` — lives here too: a
deterministic string search that proves a quote is real, independent of the LLM.

```
Phase 2 (pdf_ingest)      Phase 3 (citation_verifier)      Phase 4 (citation_surfaces)
page-tagged DocChunk  →   creates SourceRef (cited/⚠)  →   renders ref.display()
                         verify_quote() proves the quote
```

**The trust principle (D3):** a proven quote, or an honest ⚠ — never a
confident guess. `kind` is binary (`cited` / `unresolved`); there is no middle
ground, because a middle ground is where a user's trust goes to die.

## Module Metadata

- **Lines:** ~190
- **Imports:** `dataclasses`, `re`
- **Specs:** `docs/specs/FEATURE_SPEC_test_to_document_traceability.md` (D4, D6, D7, D9, D12)
- **Shipped:** 2026-09-02

## Constants

### `MAX_QUOTE_CHARS: int = 240`
Hard cap on quote length, code-enforced after verification (D7). Over-quotes
are truncated; the `SourceRef` keeps doc/page/hash so the pointer survives.

### `MAX_JUSTIFICATION_CHARS: int = 400`
Hard cap on the `justification` field (the "because" string), code-enforced (D8).

## Public API

### `SourceRef` (dataclass)
A single citation linking a criterion to a document location.

| Field | Type | Meaning |
|-------|------|---------|
| `doc` | `str` | Document identity (filename) |
| `page_pdf` | `int` | Physical PDF page index (1-indexed). 0 = not a PDF / unknown |
| `page_label` | `str` | Printed page label (e.g. "5"). "" if none |
| `heading` | `str` | Heading path at the cited location |
| `quote` | `str` | Verified verbatim span (≤ 240 chars). Empty for unresolved |
| `route` | `str` | `"text"` (PyMuPDF) \| `"ocr"` (OCR fallback) |
| `dedup_key` | `str` | Pins the citation to one chunk version (D6) |
| `kind` | `str` | `"cited"` (verified) \| `"unresolved"` (⚠ no source) |

Storing **both** `page_pdf` and `page_label` (D4) handles real-world PDFs where
the physical page and the printed number disagree (front matter, shuffled
assemblies). The trust anchor is the *quote*, not either page number.

#### `SourceRef.is_unresolved` (property) → `bool`
`True` if `kind == "unresolved"`. The ⚠ signal.

#### `SourceRef.display(*, privacy_mode: bool = False) -> str`
Renders the human-readable citation. Three shapes:
- **Cited:** `policy.pdf, PDF p.9 (printed '5') [OCR] — "The maximum claim is £5,000"`
- **Unresolved:** `⚠ policy.pdf: no source found`
- **Privacy mode:** pointer-only, quote omitted — `policy.pdf, PDF p.9 (printed '5') (quote omitted — PRIVACY_MODE)` (D7)

The `[OCR]` tag only shows when `route != "text"` (calibrates trust — an OCR'd
quote is less certain than a text-extracted one). Quotes over the cap are
truncated with `…`.

#### `SourceRef.to_dict() -> dict[str, str]`
Serializes for LangGraph checkpointing / export. `page_pdf` is stringified.

#### `SourceRef.from_dict(data: dict[str, str]) -> SourceRef` (classmethod)
Deserializes. Tolerant of missing fields (defaults applied). `page_pdf` is
coerced back to `int`.

### `normalize_for_quote_match(text: str) -> str`
Normalizes text for quote verification. The threshold policy (D3): **v1 uses
normalized exact match only, no fuzzy fallback** — a false *unresolved* is
honest and visible; a fuzzy false *resolved* is a wrong pointer wearing a green
tick (the worse failure for a trust feature).

Normalizations (in order):
1. Curly quotes → straight (`" "` → `"`, `' '` → `'`)
2. Em/en dashes → hyphen (`— –` → `-`)
3. Case-fold (lowercase)
4. Collapse all whitespace runs to a single space, strip

### `verify_quote(quote: str, page_text: str) -> bool`
The deterministic trust check. Returns `True` if the quote is a **substring**
of the page text after both are normalized. Returns `False` for empty inputs.
No AI — a string search. This is what makes the feature *trustworthy* rather
than just *sounding* trustworthy: the LLM can be wrong, but a substring check
has one right answer.

## How It Works (internals)

### `verify_quote(quote, page_text)` — the trust check
- `normalize_for_quote_match(text)` — the normalization both operands pass through before the substring comparison

### `SourceRef.display()` — the renderer
- `SourceRef.is_unresolved` — short-circuits to the ⚠ shape before any location/quote building

> The module is deliberately small: it holds the *shape* of the answer and the
> *proof* of the quote, but no orchestration. Orchestration (which criteria get
> citations, how the LLM is prompted, how surfaces render) lives in
> `src/citation_verifier.py` and `src/citation_surfaces.py`.
