# Test-to-Document Traceability - Session/Spec Notes

**Created:** 2026-08-25
**Status:** Session notes - **to go over in a dedicated spec session** (not yet a full spec)
**Priority:** High (core of the trust story)
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` -> Tier 5 -> item **16b** (Test-to-Document Traceability)
**Depends on:** AI-055 (source/heading_path on chunks - built 2026-08-25), Phase 3 RAG (shipped), the Ingestion Agent (existing, **protected file**)

> This document captures what was discussed on 2026-08-25 so it can be reviewed in a
> dedicated spec session. It is **not** a full spec - it is the *raw material*: the
> user's framing, what exists today, the feasibility spectrum, the honest ceiling, and
> the open questions to grill. The roadmap item 16b is the canonical tracker; this doc
> is the working notes.

---

## 1. The user's framing (verbatim)

> "The user sees a boundary test and it's for a figure they've never seen before.
> Can they look at the data and say **'where did you get that figure from?'** and then
> have the generator show them **the point or points in the docs that lead them to
> creating that test**?"

That is the *entire* trust question. A user who *can't* trace a generated test back to
the source doc **can't trust the generator** - even if it's 99% correct - because the
1% they can't explain is the 1% that makes them nervous. This is the **trust
differentiator** in action ("your generator learns *your* domain, on *your* hardware,
no egress") - and traceability is how the customer *verifies* that claim.

---

## 2. What exists today (the pieces, and the broken link)

| Piece | Status | What it gives us |
|-------|--------|------------------|
| `DocChunk` has `source` (filename) + `heading_path` + `text` | built | Every chunk in the RAG store already knows *which doc and which section* it came from. |
| `dedup_key` = `sha256(source \x00 heading_path \x00 normalised text)` | built (AI-055) | The source-in-hash guarantee (two different docs never dedup against each other). |
| Ingestion quality summary (per-page text/ocr/skip + cause) | built (AI-055) | Per-doc ingestion outcome, cause-differentiated skip warning. |
| Generation pipeline: doc -> raw_document_text -> Ingestion Agent -> Criterion -> test | built | The flow from doc to test. |

**The broken link (the thing to build):** `Criterion` -> *which part of the doc* produced
it. The Ingestion Agent produces a criterion from the text, but it does **not** record
*where* in the text (which chunk, which page, which heading, which figure) the criterion
came from. **That is exactly the point the user is asking about.**

---

## 3. The proposed mechanism

Add a `source_refs` field to `Criterion`:

    Criterion(
        ref="TC01.03",
        description="Verify the claim amount displays as $4,250.00",
        source_refs=[
            {"doc": "40383-2025-Cover-and-limits-v4-1.pdf",
             "page": 5,
             "heading": "Limits of Liability > Section B",
             "text": "Claim Amount: $4,250.00",
             "kind": "text"}        # "text" (traceable) or "unresolved" (no source found)
        ]
    )

**How the user sees it (three surfaces):**
1. **UI:** hover/expand a criterion -> its source ref(s) (doc name, page, heading, exact
   text). A `kind: "unresolved"` criterion shows a WARNING badge.
2. **CLI / exported test:** a comment above the test:
   `# Source: 40383-...pdf p5 "Limits > Section B": "Claim Amount: $4,250.00"`
3. **On demand:** "where did this figure come from?" -> the source_ref *is* the answer.

**The "no source found" case is itself valuable (the trust payoff):** if the Ingestion
Agent produces a criterion it *can't* back in the docs (e.g. the figure was a
table/graph-as-image we never extracted), it marks `kind: "unresolved"` -> the user sees:
**"WARNING TC01.05 - no source found in the ingested docs. This figure may be unverified."**
That is *more* trustworthy than the user *assuming* it's right. Traceability *doubles*
as a **confidence signal**: "here's the source" vs "WARNING no source found."

---

## 4. Feasibility (honest spectrum - the ceiling is set by what we *extract*)

| Tier | What it shows | Feasibility | Notes |
|------|---------------|-------------|-------|
| **1 - which doc + section** | `source` (filename) + `heading_path` | **High (EASY)** | `DocChunk` already has both. The Ingestion Agent just records which chunk(s) each criterion was derived from. The *minimum* that answers the user's question. |
| **2 - which page + which text span** | `page` + exact text | **Medium** | Add a `page` field to chunks (chunks are split by heading, can span pages) + record the exact text. Doable, more work. |
| **3 - which figure/table** | the actual figure/image | **Low (HARD - the ceiling)** | A figure that's an **image** (graph, table-as-image) is **not text**. Our pipeline extracts *text* (PyMuPDF) and *OCR'd text* (RapidOCR) but **not figure/table structure**. So a criterion whose figure came from an image-graph is **not traceable to that figure** - only to "WARNING no source found." |

**The critical, honest point:** **Traceability can only point to what we *extracted*.**
For *text-based* figures (numbers, limits, line items), it's fully traceable (Tier 1/2).
For *image-based* figures (graphs, tables-as-images), it can only say "WARNING no source
found" - which is valuable but **not** the same as "here's the figure."

**Why this matters for the user's exact question:** if the boundary test's figure came
from a **table or graph rendered as an image** (like the 524x218 graphic in the
`40383-2025-Cover-and-limits-v4-1.pdf` doc), we may not even have the data - and
therefore *can't* trace it. If a specific *image-based figure* traceability is needed,
that's a **separate, much harder** capability (figure/table structure extraction) we
don't have and **shouldn't pretend to**.

---

## 5. Relationship to the OCR/ingestion work (AI-055)

- Traceability is the **next** trust feature after the OCR + tracking work.
- It **builds on** the `source`/`heading_path` data AI-055 already produces on every chunk.
- It has the **same ceiling** (image-graphs not extractable) - the two share that limitation.
- The OCR/ingestion work (AI-055) is the *prerequisite*: without reliable extraction
  (OCR'd text in the chunks), traceability has nothing to point at.

---

## 6. Open questions to grill in the spec session

1. **Attribution:** How does the Ingestion Agent *attribute* a criterion to a chunk(s)?
   - LLM outputs a chunk index?
   - Embedding similarity between criterion text and chunk text?
   - A post-hoc match (criterion text -> fuzzy-match against chunks)?
   - *This is the core design decision.* It determines whether source_refs is *reliable*
     (LLM says "this came from chunk 7") or *probabilistic* (similarity match above a threshold).
2. **Granularity:** Is source_refs per-criterion or per-test (a test has many criteria)?
   (Likely per-criterion, but confirm.)
3. **Page:** Where does page come from? Chunks are split by heading (can span pages).
   Do we add a page (or pages) field to DocChunk? (Tier 2.)
4. **"Unresolved" detection:** How is the "no source found" case *detected* (no chunk
   match above a threshold?) and *shown* (WARNING badge in UI, a comment in the export)?
5. **UI surface:** hover/expand? a dedicated "sources" panel? click-through to the doc
   page? (Tie to the existing evidence-search UI (AI-028) if feasible.)
6. **Regeneration:** Does traceability need to survive *regeneration* (a regenerated test
   keeps its source refs, or are they recomputed)? If a doc is re-ingested (chunks
   change), do the source refs still point at the right content?
7. **Privacy:** Does a source ref expose any PII (a doc section quoted in full)? The
   site_hash design (B-047) stores *no* URLs/PII - does source-ref need a similar
   constraint (e.g. quote only the relevant span, not the whole chunk)? Insurance docs
   may contain policy numbers / names - a source ref that quotes a chunk verbatim
   could leak PII.
8. **Tier 3 (figure/table-as-image):** confirm it's a *documented limitation* for v1,
   not a to-do. Is there a *future* capability (figure/table structure extraction) worth
   noting, or is it out of scope?
9. **Confidence threshold:** what similarity/attribution threshold makes a criterion
   "resolved" vs "unresolved"? Too strict -> many false "unresolved" (erodes trust);
   too loose -> false "resolved" (wrong pointer). This is a tuning decision with a
   trust impact.

---

## 7. The honest verdict (from the discussion)

- **Tier 1 (doc + section) is the realistic, high-value scope** - it directly answers
  "where did this figure come from?" for *text-based* figures.
- **The "no source found" case is a feature, not a bug** - it's the confidence signal.
- **Tier 3 (image-graph) is a known ceiling, not a to-do** - document it, don't pretend.
- **It touches protected files** (`src/agents/ingestion.py`, `pipeline_graph.py`) - per
  house rules, it needs **a full spec session + sign-off** before editing.
- **Priority: High** - it's the core of the trust story, and the trust story is the
  reason the product exists.

---

## 8. What was built on 2026-08-25 (context - the prerequisite)

The AI-055 ingestion work that traceability builds on (all built + tested this session):
- **Tier-1 CPU OCR backend** (`RapidOCRBackend`) + `AutoOcrBackend` (the `auto` default)
  in `src/ocr_backends.py`; `get_ocr_backend()` extended (auto/cpu/high-accuracy/power).
- **[ocr] optional extra** in `pyproject.toml` (fixed a `oocr`->`ocr` typo).
- **Ingestion quality summary** in `src/rag_bundled.py` + `scripts/rag_ingest.py`.
- **Cause-differentiated skip warning** (`no_engine` / `ocr_no_text` / `ocr_failed`)
  with the install fix (`uv sync --extra ocr`) + docs link.
- **CI regression test** (`test_lv_docs_no_pages_skipped_regression`) - the durable form
  of the ingestion tracking.
- **Dedup-key source-in-hash guarantee** tests (two different docs with identical text
  never dedup against each other).
- Full gate green: 2960 tests pass, ruff clean, mypy clean, eval static 79%+.

**The end-to-end verification (LV docs):** the 3 LV car-insurance PDFs (38,712 + 8,688
+ 21,702 text chars, **zero full-page scans**, 100 images in cover-and-limits of which
99 are small logos/icons + 1 big 524x218 graphic) all ingest as "fully ingested" -> 66
chunks. **The OCR tier had nothing new to add on these docs** (they're all text) - the
improvement only manifests on *scanned/image-only* docs, which the LV set doesn't
contain. To *see* the OCR improvement, a scanned doc is needed (e.g. a photographed
policy page with no text layer).

---

*Next step: a dedicated spec session to grill Section 6 (especially Q1 attribution and
Q9 confidence threshold), produce a full `FEATURE_SPEC_test_to_doc_traceability.md`, get
sign-off to edit the protected Ingestion Agent files, then implement Tier 1.*
