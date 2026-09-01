# Test-to-Document Traceability (Cited Generation) — "where did this figure come from?"

**Created:** 2026-09-01
**Status:** Spec — Decisions D1–D12 locked (full spec session 2026-09-01). Implementation not started.
**Priority:** High (core of the trust story) — pre-launch
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` → Tier 5 → item **16b** (canonical tracker — phases are checked off there)
**Supersedes:** `docs/specs/SESSION_SPEC_test_to_doc_traceability.md` (2026-08-25 raw session notes — historical)
**Depends on:** AI-055 remaining wiring (per-page OCR into the generation pipeline — Phase 2 merge partner), Phase 3 RAG (shipped), Ingestion Agent + pipeline (existing, **protected files** — sign-off below)

---

## 1. What This Is

A user who sees a generated test with a **boundary test for a figure they've never
seen** must be able to ask **"where did you get that figure from?"** — and have the
generator answer in the shape of:

> *"I picked £500 because Doc A p.9 said X's upper bound is £200, and Doc B p.14
> said Y = X + £300."*

…or honestly say **⚠ no source found** when it can't. Without this, a user *can't*
trust the generator even if it's 99% correct — the 1% they can't explain is the 1%
that makes them nervous. This is the **trust differentiator** made verifiable.

This spec is **cited generation**, not a "show the sources" display feature:

1. **Documents fully feed generation** — whole doc, every page, not just the first
   500 characters (the current ceiling).
2. **Provenance is preserved** — which doc, which page, which heading, which exact
   quote, via which parse route — at the moment the material is consumed.
3. **Every criterion carries its citations** — plus a visible trust boundary between
   *evidence* (verified quotes) and *reasoning* (LLM-generated justification).
4. **Honesty when it can't back a figure** — the ⚠ `unresolved` signal, advisory,
   per-figure precise.

**What this is NOT:**
- Not a display layer over the current pipeline — today's pipeline discards
  provenance at exactly the moment it would be needed (see §2).
- Not figure/table understanding. A chart-as-image is a documented limitation (§11).
- Not a gatekeeper. Unresolved never blocks generation (§8).
- Not a new egress surface. Citations record what already reaches the LLM (§9).

---

## 2. Architecture Findings (code audit 2026-09-01)

There are **three "document doors"**, and they behave very differently:

| Door | What happens today | Consequence for traceability |
|------|--------------------|------------------------------|
| **1. Pasted/typed requirements** (UI Requirements box; `Upload File` → text) | The *only* path that generates criteria today. `parse_requirements_text` → `build_test_plan` (`src/ui_pipeline.py`) → `SpecAnalyzer.analyze` | Citations here are nearly deterministic — a criterion *is* a line of the user's own text |
| **2. Document mode** (`pipeline_graph._parse_document`) | Only `raw_text[:500]` seeds the user story; the rest of the doc produces `change_deltas` which feed **only** the Impact Mapper — never test generation | A boundary figure deep in a 40-page policy **cannot** appear in a test via this door today. Whole-document generation must exist before page-level citations can |
| **3. RAG store** (pre-ingested domain docs) | Chunk text is retrieved at ingestion time as top-10 `domain_terms` and at resolver time for locator scoring — but provenance (`source`/`heading_path`) is **discarded at retrieval** (`RetrievedPattern` keeps none of it) | The material is *in* the system but the "which doc/page" knowledge is thrown away at exactly the moment it's needed |

Additional findings:

- `DocChunk` (`src/rag_store.py`) has `text` / `source` / `heading_path` / `dedup_key`
  — **no `page`, no parse route**.
- `Criterion.source_text` exists but is filled inconsistently: verbatim line in
  `IngestionAgent._criteria_from_text`; a label (`"Acceptance Criteria {idx}"`) in
  `SpecAnalyzer`'s numbered path.
- The AI-055 ingest loop is already **page-aware** (PyMuPDF per page, RapidOCR
  `parse_page` fallback for scans) — page knowledge exists at extraction time and is
  dropped at chunking.
- Chunk-level dedup: unchanged docs re-ingest as a no-op; **changed docs append new
  chunks while stale ones linger by design** (tested behaviour) — version ambiguity
  "Doc A p.9" must be handled (§5, D6).
- The old roadmap premise ("criteria are derived from ingested chunks") was wrong:
  criteria come from the story/pasted text; RAG only enriches loosely. The roadmap
  was corrected alongside this spec.

---

## 3. The Phased Plan (each phase shippable alone)

- [ ] **Phase 1 — Stop discarding provenance.** Add `page` (PDF index + printed
  label) and `route` (`text` | `ocr`) to `DocChunk` (or the page-tagged parse
  output); preserve doc identity through retrieval (`RetrievedPattern` carries it).
  No behaviour change — pure plumbing. Cheap standalone value.
- [ ] **Phase 2 — Whole-document generation.** Merge with AI-055's remaining work
  ("wire per-page OCR into the generation pipeline's direct-doc parse") — **one
  combined change to the protected `pipeline_graph.py`**, so the protected file is
  touched once, not twice. Every page of the uploaded doc feeds criterion
  extraction, each page tagged (doc, page, route). Removes the 500-char ceiling.
- [ ] **Phase 3 — Citations per criterion.** Mechanism (§4) attaches `source_refs`
  + `justification` to every criterion; deterministic paste-path criteria get
  automatic line citations (no LLM).
- [ ] **Phase 4 — Surfaces.** Test-file `# Source:` comments, Living Test Plan
  citation cards, CLI debug query, `PRIVACY_MODE` handling in exports.

Phase 1 and Phase 2 are the critical path for everything else.

---

## 4. Attribution Mechanism — Hybrid (LLM proposes, code verifies)

The LLM must emit, per criterion, one or more citations **each containing a verbatim
quote** from the page-tagged material. Deterministic code then verifies every quote:

1. Quote found in the cited page's text (normalized substring match) → citation stands.
2. Quote not found on the cited page → search **all** pages of the doc; found → fix
   the citation (log the correction); not found → **unresolved** ⚠.
3. No citation emitted by the LLM → unresolved.

Rationale: matches the house rule *"regex first, LLM fallback"* applied to citations —
the LLM does the semantic work (finding *which* sentences justify a boundary), the
deterministic code does the trust work (proving the quotes are real). LLMs hallucinate
citations; an unverified citation must never be shown.

The deterministic paste path (user provides numbered criteria) needs none of this —
the criterion *is* the line; the citation is automatic.

**Threshold policy (dissolves the old "confidence threshold" question).** Resolution
is deterministic quote verification, not a similarity score — there is **no tuning
knob**. v1 uses normalized exact match only (case / whitespace / quote-glyphs), **no
fuzzy fallback**: a false *unresolved* is honest and visible; a fuzzy false *resolved*
is a wrong pointer wearing a green tick — the worse failure for a trust feature. If
the eval harness later shows a high unresolved rate driven by LLM paraphrasing, add a
**conservative** fuzzy fallback (high token-overlap threshold, logged as
"corrected") as a data-driven follow-up.

---

## 5. Page Numbers Can Lie; Quotes Can't

Trust anchors in the **verified quote**, not the page number. Page numbers are
display metadata. This handles real-world messy PDFs:

- **Store both numbers.** Physical PDF page index **and** the printed page label
  (`page.get_label()`). Display *"Doc A, PDF p.9 (printed '5')"* whenever they
  disagree (docs assembled out of order, front matter). No labels → just "p.9".
- **Never assume page order.** The quote-verification fallback searches all pages,
  so shuffled assemblies get found anyway.
- **Honest limit.** If the *scanning itself* was out of order (content genuinely
  misplaced), we cite the true location — the user spotting the oddity is the
  feature working.

**Versioning (chunk dedup interaction).** Re-ingesting an unchanged doc is a no-op
(stable citations). A **changed** doc appends new chunks while stale ones linger, so
"Doc A p.9" alone is ambiguous across versions. Therefore every citation stores the
chunk's `dedup_key` — **required now, not later**. Display can then say *"as ingested
2026-08-25 (content since changed)"*. Document-mode generation parses the **uploaded
file directly** each run, so that path always cites the file as-it-is-today. Future
drift detection ("test generated against policy v2, docs now v3") is enabled by the
stored hash but is a *separate future feature*, not part of this spec.

---

## 6. Data Model

```
SourceRef = {
    doc: str,              # filename / doc identity
    page_pdf: int,         # physical PDF page index (1-indexed)
    page_label: str,       # printed page label ("5"), "" if none
    heading: str,          # heading path at the cited location
    quote: str,            # verified verbatim span (≤ ~240 chars, §9)
    route: "text" | "ocr", # parse route (calibrates trust in the quote)
    dedup_key: str,        # pins the citation to one chunk version (§5)
    kind: "cited" | "unresolved",
}

Criterion gains:
    source_refs: list[SourceRef]
    justification: str     # LLM rationale, ≤ ~400 chars, §7
```

**Pass-through trap:** `Criterion` is recreated in the QA Director
(`src/agents/director.py`). The new fields must be carried there exactly as
`source_text` already is — or citations die at the first hop.

---

## 7. Rationale — the "because" String

Citations prove *where* text came from; the connection ("Y's boundary is 300 *more
than* X's, therefore 500") is an inference. Each criterion carries a short
LLM-generated `justification` grounded in its citations:

> *"Upper bound £5,000: Doc A p.9 states X max £200; Doc B p.14 states Y = X + £300."*

Rules:

- **Visible trust boundary in the UI:** quotes labelled **"Evidence (verified)"**,
  rationale labelled **"Generator's reasoning (unverified text)"**.
- Generated **only when citations verify**; unresolved criteria get no rationale,
  just the ⚠.
- **Hard cap ~400 chars** (code-enforced, like the quote cap).
- **Overhead tracking:** the eval harness records citation+rationale token cost;
  BACKLOG watch item *"citation/rationale overhead — revisit cap, structure, or
  structured refs if token cost/latency creeps."*
- Structured rationale (derived-relations mini proof-language:
  `derived_from: [ref1, ref2], operation: sum`) remains a possible future upgrade;
  the free-text `justification` sits fine alongside it.

---

## 8. Unresolved — Advisory, Never Blocking

- Generate the test anyway; flag it everywhere (plan, test comment, exports).
- **Why advisory:** a trust signal that gatekeeps teaches users to click through it,
  and then a real problem hides behind click-fatigue. The ⚠ lands in the Living Test
  Plan, where a human is already reviewing.
- **Per-figure precision:** *"£300 increment: no source found"*, not *"some of
  TC01.05 is unverified"*.
- A `STRICT_SOURCES` gate is deliberately **not** built until data shows demand.

---

## 9. Privacy — Bounded Quotes + One Umbrella `PRIVACY_MODE`

**Where the information goes (audited):**

| Surface | Local / external | Notes |
|---------|------------------|-------|
| LLM provider (default `openai-local` → llama.cpp :8080) | **Local** | The trust story. A user-configured remote provider is that user's explicit choice |
| RAG store (Milvus Lite files) | Local | Already holds full doc text; citations add nothing new |
| `generated_tests/test_*.py` | Local, **gitignored by house rule** | Would hold `# Source:` comments |
| `run_results.sqlite` / HTML-JSON exports | Local | Can be uploaded by the user anywhere |
| **Jira export** | **External SaaS** | The one silent-ish door → covered by `PRIVACY_MODE` |

Key framing: **citations create no new egress.** Doc text must already reach the LLM
for extraction; a quote is a *record* of what was already sent.

**Decision:** bounded quotes — the **minimum span that justifies the criterion**
(sentence(s) relied on), hard-capped ~240 chars, code-enforced after verification
(over-quotes truncated; ref keeps doc/page/hash).

**`PRIVACY_MODE`** (default off) is deliberately a **vague umbrella flag** whose
behaviour is defined by outcome intent, so future privacy features roll into one
button:

- v1 behaviour: pointer-only citations (doc + page + heading + hash, no text) in
  **exports**.
- Future behaviours that roll in here: quote redaction, egress enforcement, PII
  scrubbing in evidence, no figure crops in exports (§11 preview feature).
- Exported evidence carries a self-documenting note: *"Source quotes included; set
  PRIVACY_MODE=1 to omit quotes."*

Design lineage: B-047 site-hash (no URLs/PII stored) — same instinct, proportionate
application.

**PII nuance:** insurance docs contain policy numbers / names — a verbatim quote can
leak them. Mitigation ladder: the ~240-char cap + "minimum span" rule (reduces
exposure) → `PRIVACY_MODE` pointer-only (eliminates it) → a future pattern-redaction
pass (policy-number scrubbing) rolls into `PRIVACY_MODE` as designed.

---

## 10. Surfaces (in value order)

1. **`# Source:` comment in the exported test** — the artifact users keep and share:
   `# Source: Doc A, PDF p.9 (printed '5') [OCR] — "The maximum claim amount is £5,000"`
   (+ justification line). Works for CLI-only users; plain text.
2. **Living Test Plan citation cards** in Streamlit — hover/expand a criterion.
   Catches the question *before* generation, where it's cheapest to act on.
3. **CLI debug query** — follows the `scripts/debug.py` pattern.

One rule across all three: an unresolved criterion renders the ⚠ everywhere, never
silently omitted.

**Click-through / view-in-context (optional, Phase 4):** open the local PDF at the
cited page, or deep-link into the AI-028 evidence-search UI. Real value, but new
plumbing (per-OS PDF opening / AI-028 integration) — must not gate the phases. v1
citation cards are static: doc + page + quote + route.

---

## 11. Documented Limitation — Figures/Tables-as-Image (Tier 3)

Neither parse route (PyMuPDF, RapidOCR) extracts figure/table *structure*. A boundary
derived from a chart-as-image will correctly end up ⚠ unresolved — the message names
the likely cause when the cited page is image-heavy. **Traceability can only point to
what we extracted.**

Future work (owned by roadmap §16 "Future improvement", not this spec):

- **Figure/table structure extraction** — vision-model pass reading charts/tables
  *as structure* (axis bounds, table cells); extends the OCR tier ladder as an
  opt-in GPU tier.
- **Figure-region preview on unresolved citations** — crop & attach the unreadable
  region; local surfaces only; `PRIVACY_MODE` applies.

---

## 12. Quality Gates & Process

- **Protected files:** `src/agents/pipeline_graph.py` (Phase 2, merged with AI-055
  wiring) and `src/agents/ingestion.py` (Phase 3). **Sign-off obtained via this
  spec (2026-09-01 session); any change beyond D1–D12 needs re-approval.**
- **Eval harness is a required pre-ship gate** for Phases 2–3 (touches
  pipeline/generation files): `python scripts/eval/eval_harness.py run --mode
  static` plus `--min-accuracy 79` before shipping; watch citation+rationale token
  overhead per §7.
- **Verification ladder per house rules:** smoke → pytest → `verify_production.py`
  → eval harness.
- **New modules** (`source_refs` / citation verifier) go in `src/` with full type
  hints, unit tests, and `markdown_docs` entries per AGENTS.md §9.
- **Validation fixtures:** the LV corpus's `cover-and-limits` PDF contains exactly
  one large graphic (524×218) among 99 logos/icons — the canonical in-repo fixture
  for the ⚠ unresolved path. The LV docs are all-text (zero full-page scans), so
  Phase 2's per-page OCR wiring **needs a scanned-PDF test fixture** (committed or
  generated, e.g. a photographed policy page) or the OCR wiring ships unverified.

---

## 13. Dependencies & Session Estimates

**Dependencies:** AI-055 remaining wiring (Phase 2 merge partner), Phase 3 RAG
(shipped), Ingestion Agent + pipeline (protected — sign-off above), B-047 site-hash
privacy precedent (design lineage for §9).

**Estimated sessions:**

| Phase | Sessions |
|-------|----------|
| Phase 1 — provenance plumbing | ~1 |
| Phase 2 — whole-doc generation (shared with AI-055) | ~1–2 |
| Phase 3 — attribution + verification + unresolved | ~2 |
| Phase 4 — surfaces + exports + PRIVACY_MODE | ~1–2 |
| **Total** | **~5–7** |

---

## 14. Decision Log (D1–D12)

| # | Decision |
|---|----------|
| D1 | Full vision (cited generation), phased. Display-only rejected: nothing honest to show today |
| D2 | Four phases; Phase 2 merged with AI-055 wiring — protected file touched once |
| D3 | Hybrid attribution: LLM proposes verbatim quotes, code verifies; unverified citations never shown |
| D4 | Trust anchors in the quote; store PDF index + printed label; page order never assumed |
| D5 | Per-criterion refs; test-level sources derived by union, never stored separately |
| D6 | Recompute citations every run; `dedup_key` pinned now (handles stale-lingering chunk versions) |
| D7 | Bounded quotes (~240 chars) + vague umbrella `PRIVACY_MODE` (pointer-only exports in v1) |
| D8 | Capped `justification` field (~400 chars), token-overhead tracked, BACKLOG watch item |
| D9 | Unresolved = advisory, per-figure precision, never blocking; no STRICT_SOURCES until demanded |
| D10 | Surfaces: test-file comments → Living Test Plan cards → CLI debug; ⚠ everywhere |
| D11 | Tier 3 ceiling documented; future work owned by §16 ingestion improvements |
| D12 | `SourceRef` data model; `director.py` pass-through must carry the new fields |
