# `src/citation_verifier.py`

## High-Level Purpose

The **attribution logic** for Test-to-Document Traceability (16b Phase 3).
Attaches `source_refs` to every criterion, using the **hybrid mechanism**
(D3): the LLM proposes a verbatim quote and a page; deterministic code
*verifies* the quote against the page text. The LLM does the semantic work
(finding *which* sentences justify a boundary); the code does the trust work
(proving the quote is real). An unverified citation never stands.

Two entry points for the two ways criteria are created:

```
paste path (user typed numbered criteria)          document mode (policy PDF)
└─ attach_paste_citations()                        └─ verify_document_citations()
   the criterion IS the line → auto-cite,          LLM proposes quote+page →
   no LLM                                            code verifies → proven /
                                                     corrected-page / ⚠
```

**The three outcomes** of the document-mode check (the heart of the module):
1. **Proven** — quote found on the cited page → `kind="cited"`
2. **Corrected** — quote found on a *different* page → the LLM got the page
   wrong; the code fixes it and logs the correction → `kind="cited"`
3. **⚠ Unresolved** — quote found nowhere (or none emitted) → `kind="unresolved"`,
   no justification. Advisory, never blocking (D9).

## Module Metadata

- **Lines:** ~330
- **Imports:** `logging`, `typing`, `src.rag_store`, `src.source_refs`
- **Specs:** `docs/specs/FEATURE_SPEC_test_to_document_traceability.md` (D3, D4, D6, D7, D8, D9, D12)
- **Shipped:** 2026-09-02

## Public API

### `attach_paste_citations(criteria: list[Any], source_text: str) -> list[Any]`
The **deterministic paste path**. When the user types numbered criteria, each
criterion *is* a line of the user's own text — no LLM needed. Each criterion
gets one `SourceRef` with `doc="user-input"`, `kind="cited"`, and the verbatim
line as the quote (truncated to `MAX_QUOTE_CHARS`). Mutates and returns the
same list.

### `verify_document_citations(criteria: list[Any], page_chunks: list[DocChunk], llm_citations: dict[str, list[dict[str, Any]]]) -> list[Any]`
The **hybrid verification** (D3). Verifies LLM-proposed citations against
page-tagged chunks and attaches `source_refs` + `justification` to each
criterion.

Args:
- `criteria` — the Criterion objects to annotate
- `page_chunks` — page-tagged `DocChunk`s (from `ingest_pdf_page_aware`)
- `llm_citations` — mapping of criterion ref → list of citation dicts, each
  with keys `"doc"`, `"page"`, `"quote"`, `"heading"`, `"route"`

Behaviour per criterion (see the three outcomes above). Builds three lookups
up front (all keyed by `(source, page)`): the page's text, the whole document's
text, and the chunk's `dedup_key`. On a **proven** citation, the `dedup_key`
is pinned to the ref (D6) so a re-uploaded changed document can be told apart.
The `justification` is built *only* from verified citations (D8) — an
unresolved criterion gets `""`, just the ⚠ (D9).

### `build_llm_citation_prompt(criterion: Any, page_chunks: list[DocChunk]) -> str`
Builds the LLM prompt for citation extraction. Includes the criterion
description and up to 10 page snippets (~200 chars each, to bound prompt
size). Explicitly instructs the LLM to return a **VERBATIM** quote — *"copy
the exact words from the page, do not paraphrase"* — and to return an empty
list if no source is found. The verbatim instruction is what makes the
downstream `verify_quote()` check meaningful: the code can only prove a quote
is real if the LLM was told to give the *exact* words.

## How It Works (internals)

### `verify_document_citations(...)` — the verification
- `_find_page_for_quote(quote, page_chunks, doc)` — scans the doc's chunks and
  returns the page index where the (normalized) quote first appears. Used only
  on the **corrected** path, when the quote is found in the document but not on
  the LLM's claimed page.
- `verify_quote(quote, page_text)` *(from `source_refs`)* — the deterministic
  trust check, called twice per citation: first against the claimed page, then
  against the whole document (only if the first fails).
- `normalize_for_quote_match(text)` *(from `source_refs`)* — normalization both
  operands pass through (see `source_refs.py`).

### `build_llm_citation_prompt(...)` — the prompt builder
- (inline) builds the `[file p.N] snippet` lines and the JSON-format
  instruction. No private helpers — the prompt is assembled in one place.

### `attach_paste_citations(...)` — the paste path
- (inline) no private helpers — the citation is trivial because the criterion
  is already the line.

> **Design note:** this module holds *orchestration* (which criteria get
> citations, the proven/corrected/⚠ decision, justification building) but
> *not* the data model (`SourceRef`, `verify_quote` — in `source_refs.py`) and
> *not* the rendering (`display` — called by `citation_surfaces.py`). The split
> is: model / logic / presentation.
