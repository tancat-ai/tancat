# `src/citation_surfaces.py`

## High-Level Purpose

The **rendering layer** for Test-to-Document Traceability (16b Phase 4).
Turns the in-memory `source_refs` (built by Phase 3) into what the user
actually sees, across three surfaces (D10):

```
1. test-file # Source: comments   ← the artifact users keep and share (primary)
2. Living Test Plan citation cards ← catches the question BEFORE generation
3. CLI debug query                ← "show me what the machine did" for one criterion
```

One rule across all three: **an unresolved criterion renders the ⚠ everywhere,
never silently omitted** (D9). A trust signal you can click through teaches
the user to stop looking — so the ⚠ stays in their face on purpose.

`PRIVACY_MODE` (D7) runs through all three: when on, citations become
*pointer-only* (doc + page + heading, no quote text). Insurance documents
contain policy numbers and names — a verbatim quote can leak them. One switch,
not a separate "redaction feature."

This module is *presentation only* — it holds no data model and no logic. It
calls `ref.display()` (the string format lives in `source_refs.py`) and lays
the results out differently per surface.

## Module Metadata

- **Lines:** ~250
- **Imports:** `logging`, `typing`, `src.agents.pipeline_state`
- **Specs:** `docs/specs/FEATURE_SPEC_test_to_document_traceability.md` (D7, D9, D10)
- **Shipped:** 2026-09-02

## Public API

### `render_source_comments(criteria: list[Criterion], *, privacy_mode: bool = False) -> str`
The **primary surface** — `# Source:` comments for the exported `.py` file.
The test file is the thing the user keeps and shares, so the citation must be
plain text inside it, interpretable without the tool. One block per criterion
that has `source_refs`; criteria without (the paste path) produce nothing.

Example output:
```
# TC01.03: Max claim amount boundary
#   policy.pdf, PDF p.9 (printed '5') [OCR] — "The maximum claim amount is five thousand pounds."
#   Because: policy.pdf p.9: "The maximum claim amount is five thousand pounds."
```
Each citation line is `#   ` + `ref.display(privacy_mode=...)`. The
`Because:` line (the justification) is omitted in privacy mode. Returns `""`
when no criteria have refs.

### `render_citation_cards(criteria: list[Criterion], *, privacy_mode: bool = False) -> list[dict[str, Any]]`
Structured data for the **Living Test Plan** (Streamlit/CLI). Catches the
question *before* generation, where it's cheapest to act on (edit the
criterion, check the document). Returns a list of dicts, one per criterion
with `source_refs`:

| Key | Meaning |
|-----|---------|
| `ref` | criterion ref (e.g. "TC01.03") |
| `description` | criterion description |
| `citations` | list of `ref.display()` strings |
| `justification` | the "because" string; `""` in privacy mode |
| `has_unresolved` | `True` if any citation is ⚠ (so the UI can flag the card) |
| `privacy_mode` | echo of the mode |

### `render_cli_debug(criteria: list[Criterion], criterion_ref: str, *, privacy_mode: bool = False) -> str`
A **CLI debug dump** of one criterion's citations (follows the
`scripts/debug.py` pattern). Shows every field of every `SourceRef` for the
named criterion: status (`✓ CITED` / `⚠ UNRESOLVED`), doc, page (physical +
printed), heading, quote (omitted in privacy mode), route, and the
truncated `dedup_key`. Ends with the **trust boundary footer**:
```
Trust boundary:
  Quotes = Evidence (verified)
  Justification = Generator's reasoning (unverified text)
```
Returns an `Error: ... not found` string for an unknown ref, and a
"no source references" string when the criterion has none.

### `render_export_note(*, privacy_mode: bool = False) -> str`
The **self-documenting export note** (D7). Exported evidence carries this so
the reader knows whether quotes are present and how to omit them:
- privacy mode: `Source pointers included (quotes omitted — PRIVACY_MODE=1).`
- default: `Source quotes included; set PRIVACY_MODE=1 to omit quotes.`

## How It Works (internals)

All four functions are **inline presenters** with no private helpers — the
deliberate choice is that there is no logic here to document. Each function:
1. filters to criteria that have `source_refs`
2. calls `ref.display(privacy_mode=...)` / `ref.is_unresolved` *(from
   `source_refs`)* for the string + the ⚠ flag
3. lays the results out in the surface's shape (comment block / dict / dump)

> **Design note:** if a "surface" ever needs real logic (e.g. click-through to
> open the local PDF at the cited page, or deep-link into the AI-028
> evidence-search UI), that logic belongs in a new module — not here. The
> spec (D10) marks click-through as optional Phase 4 follow-up precisely so it
> doesn't gate the core rendering.
