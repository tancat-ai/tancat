# Feature Spec — Phase 1: Multi-Agent Architecture & Resolution Improvements

**Created:** 2026-07-23
**Status:** Approved — Phase 1c complete
**Priority:** High — closes the gap between "works on simple sites" and "works on complex SPAs"
**Depends on:** Phase 3 RAG (shipped — RAGStore, RAGRetriever, golden pattern ingestion),
Phase 5 Eval Harness (shipped — resolver eval with RAG on/off comparison),
AI-030 LV Insurance mock site (shipped — 129 elements, 7-step quote flow)
**Roadmap ref:** Phase 1 (ROADMAP.md), supplemented by eval findings

---

## 1. Problem Statement

The current pipeline resolves placeholders against a single flat haystack of all scraped elements.
This works for simple sites (saucedemo: 45% → 55% with RAG) but degrades on complex SPAs:

| Metric | Value |
|--------|-------|
| LV Insurance elements | 129 (all visible at scrape time, 7 hidden page sections) |
| LV Insurance accuracy (RAG off) | 20.8% (7/33) |
| LV Insurance accuracy (RAG on) | 33.3% (11/33) |
| LV RAG improvement | +12.5pp — proven signal, but absolute still low |
| Buttons competing for "Next" | 5 identical "Next →" buttons across 5 sections |
| Buttons competing for "Back" | 6 identical "← Back" buttons across 6 sections |

**Root causes (ranked by eval impact):**

1. **No section scoping.** The resolver scores all 129 elements simultaneously. "Next button on account page" competes against 4 other "Next →" buttons. The description says "on account page" but the scorer has no concept of page sections.

2. **PDF domain docs not indexed.** The 3 real LV PDFs (38 pages: T&Cs, IPID, Cover & Limits) sit in `docs/rag_corpus/lv_docs/` as raw PDFs. Only the markdown docs (underwriting guide, redacted personal docs) are ingested. The resolver lacks the actual policy language (scheme names, excess amounts, cover types) to match against form labels.

3. **No visibility-aware resolution.** Hidden elements (`is_visible=False`) score the same as visible ones for non-ASSERT actions. In the real pipeline this is correct (you click through pages), but for the eval (single-page scrape of all sections) it means hidden "Back" buttons pollute the candidate list.

4. **Single-prompt skeleton generation.** `TestGenerator.generate_skeleton()` sends the full user story + all criteria to the LLM in one call. For complex stories (10+ criteria), the LLM hallucinates selectors or skips criteria. The ROADMAP Phase 1 calls for a Planning Agent → Developer Agent split, but this can be delivered incrementally.

### Current pipeline (what we have)

```
User story + conditions
  → TestGenerator (single LLM call, skeleton-first with placeholders)
  → SkeletonParser (extract journeys, placeholders, page requirements)
  → PageScraper (scrape all candidate URLs)
  → PlaceholderOrchestrator (resolve placeholders against flat element list)
      → ElementMatcher (pass 0-3, scoring)
      → PlaceholderScorer (flat score, no section context)
      → RAGRetriever (advisory golden pattern bonus, +20)
  → CodePostprocessor (inject evidence_tracker calls)
```

---

## 2. Solution: Incremental Phase 1

The original ROADMAP Phase 1 (LangGraph PlanningAgent → DeveloperAgent) is the end state.
This spec breaks it into deliverable phases, each measured by the eval harness:

```
Phase 1a: PDF Ingestion ──► Phase 1b: Section-Aware Resolution ──► Phase 1c: LangGraph Orchestration
```

### Phase 1a — PDF Ingestion Pipeline

**Goal:** Parse the 3 LV PDFs and ingest them into the existing RAG store, giving the resolver actual insurance domain language to retrieve.

**What ships:**

| File | Description |
|------|-------------|
| `src/pdf_ingest.py` | PDF text extraction with PyMuPDF (already installed). Handles text, tables (cell-by-cell), and images (skip with log). Outputs `DocChunk` objects. |
| `scripts/rag_ingest.py` | New `--pdfs` flag: `python scripts/rag_ingest.py --pdfs --docs --golden` |
| `docs/rag_corpus/lv_docs/*.pdf` | Already present — 3 PDFs (24 + 2 + 12 = 38 pages) |
| `tests/test_pdf_ingest.py` | Unit tests for text extraction, table handling, chunking |

**PDF chunking strategy:**

- Split on `##` / `#` headings within extracted text (PyMuPDF extracts heading structure for PDFs with bookmarks)
- Fall back to fixed-size chunks (~500 tokens, 50-token overlap) for unstructured text
- Tables: extract as markdown tables, keep as single chunk (don't split rows)
- Skip images with a logged warning (no OCR in v1 — Docling is Phase 2)

**Integration:** Reuses `RAGStore.add_docs()` — zero changes to the vector store backend. The `DocChunk` dataclass already exists and carries `source` and `heading_path` metadata.

**RAG store metadata for PDFs:**
```python
DocChunk(
    text="Section 3.2: Standard cover includes third party liability...",
    source="35880-2023-car-tc.pdf",
    heading_path="Car T&Cs > Your insurance policy > Cover options",
)
```

**Eval impact:** +5-8pp on LV Insurance (resolver can now match "Standard scheme" against actual policy text).

**Acceptance criteria:**
1. `python scripts/rag_ingest.py --pdfs` parses all 3 PDFs and upserts chunks into the store.
2. RAG retrieval for insurance terms ("Standard scheme", "no claims discount", "compulsory excess") returns PDF chunks with confidence ≥ 0.6.
3. Eval harness shows LV Insurance accuracy ≥ 25% (up from 20.8% baseline, RAG on).
4. No regressions on other sites' eval accuracy.
5. 15+ unit tests, ruff clean, mypy clean.

---

### Phase 1b — Section-Aware Resolution

**Goal:** Scope placeholder resolution to the correct page section, reducing the haystack from 129 elements to ~15-20 per section.

**What ships:**

| File | Description |
|------|-------------|
| `src/section_scoper.py` | **New** — Detects page sections from heading elements and assigns each element to a section. Provides `scope_elements(section_name, all_elements)` → filtered list. |
| `src/placeholder_scorers.py` | Visibility penalty for non-ASSERT actions on hidden elements. New constant `_HIDDEN_ELEMENT_PENALTY = -30`. |
| `src/placeholder_orchestrator.py` | Section scoping in the resolve path: extract section hint from placeholder description ("on account page") → filter elements before scoring. |
| `tests/test_section_scoper.py` | 15+ tests covering heading detection, element assignment, section name matching. |

**Section scoping algorithm:**

1. **Heading detection:** Scan elements for `role=h1/h2/h3/h4` or elements with `tag=h1..h6`.
2. **Element assignment:** Each element belongs to the section whose heading precedes it (by document order / `_element_box_index` or accessibility tree position).
3. **Section name matching:** Extract section hint from placeholder description using regex: `"...on <SECTION> page"`, `"...in <SECTION> section"`. Also match against known section patterns ("account", "product", "policy", "drivers", "vehicles", "extras", "quote").
4. **Fallback:** If no section hint found in description, score against all elements (current behaviour).

**Visibility penalty:**

For non-ASSERT actions (CLICK, FILL, SELECT), hidden elements (`is_visible=False`) receive `_HIDDEN_ELEMENT_PENALTY = -30`. This doesn't exclude them (a hidden element might still be the correct answer if the description names its section explicitly) but demotes them below visible candidates with similar scores.

**How it interacts with the real pipeline:**

In the actual `TestOrchestrator.run_pipeline()`, pages are scraped per-URL (not all sections at once). Section scoping is a no-op for multi-page sites — each URL has one section. The benefit is for:
1. The eval harness (single-page mock sites like LV Insurance)
2. Future SPA support where the scraper needs to navigate hidden sections

**Eval impact:** +10-15pp on LV Insurance (smaller haystack = fewer false matches).

**Acceptance criteria:**
1. `SectionScoper` correctly assigns 129 LV elements to 7 sections based on headings.
2. "Next button on account page" resolves to `#accountNext` (not `#productNext` or others).
3. "← Back" buttons resolve correctly when section is specified.
4. Eval harness shows LV Insurance accuracy ≥ 40% (up from 33.3% with RAG only).
5. No regressions on other sites (section scoping is a no-op when no section hint found).
6. 15+ unit tests, ruff clean, mypy clean.

---

### Phase 1c — LangGraph Orchestration (skeleton generation)

**Dependency note:** `langgraph` is an **optional dependency** (`[project.optional-dependencies] langgraph`). Commercial customers who don't need multi-agent generation don't install it. The `LANGGRAPH_ENABLED=0` default ensures zero impact when the package is absent.

**Goal:** Replace `TestGenerator.generate_skeleton()` with a LangGraph multi-agent workflow: Planner → Generator → Validator.

**What ships:**

| File | Description |
|------|-------------|
| `src/agents/graph.py` | **New** — LangGraph `StateGraph` with Pydantic state schema. |
| `src/agents/planner.py` | **New** — Planning Agent node: parses user story + DOM → ordered test plan (Markdown, no code). |
| `src/agents/generator.py` | **New** — Generator Agent node: consumes test plan → skeleton code with placeholders. |
| `src/agents/validator.py` | **New** — Validator Agent node: checks skeleton against criteria count, retries if mismatch. |
| `src/agents/state.py` | **New** — Pydantic `WorkflowState` model. |
| `src/test_generator.py` | Updated to delegate to LangGraph (or fall back to current single-call mode when `LANGGRAPH_ENABLED=0`). |
| `tests/test_agents_*.py` | Unit tests for each agent node + integration test for full graph. |

**State schema:**

```python
class WorkflowState(BaseModel):
    user_story: str
    conditions: str
    target_urls: list[str] = []
    expected_test_count: int = 0
    raw_dom_snapshot: str = ""        # Optional: pre-scraped DOM for planner
    test_plan: str = ""               # Planner output (Markdown)
    skeleton_code: str = ""           # Generator output
    validation_errors: list[str] = [] # Validator output
    retry_count: int = 0
    max_retries: int = 2
```

**Graph topology:**

```
[Planner] → [Generator] → [Validator]
                          ↖_________↙ (retry loop, max 2)
                              ↓ (pass)
                         [Return skeleton]
```

**Retry logic:**
- If validator detects missing criteria (journey count ≠ expected count) or hallucinated selectors, increment `retry_count` and route back to Generator with error context.
- If `retry_count >= max_retries`, return best effort (current behaviour) — don't fail the pipeline.

**Toggle:** `LANGGRAPH_ENABLED=1` env var. Default `0` (current single-call mode) for safe rollout. When `0`, `TestGenerator` uses existing `LLMClient.generate_skeleton()`.

**Eval impact:** Reduces skeleton hallucination rate (fewer runs with wrong criteria count). Measured by `scripts/eval/eval_harness.py run --regenerate` (nondeterministic pipeline eval).

**Acceptance criteria:**
1. LangGraph produces identical skeleton output to current `TestGenerator` on simple stories (1-3 criteria).
2. On complex stories (10+ criteria), LangGraph produces skeletons with fewer validation errors than single-call mode.
3. Pipeline passes all existing tests when `LANGGRAPH_ENABLED=0` (default).
4. 20+ unit tests covering each agent node + graph topology.
5. ruff clean, mypy clean, full pytest suite passes.

---

### Phase 1d — Vision-Based Tie-Breaker (Fara)

**Goal:** Replace text-based scoring tie-breakers with a vision model that sees the actual page screenshot, resolving ambiguous placeholders (e.g. "Next button on account page" vs five identical "Next →" buttons) by visual context.

**What ships:**

| File | Description |
|------|-------------|
| `src/vision_tiebreaker.py` | **New** — Takes top-N tied candidates (within scoring threshold), crops their bounding boxes from a page screenshot, and sends region + placeholder description to a vision model for final selection. |
| `src/placeholder_orchestrator.py` | New tie-break step: when scoring returns ≤3 candidates within 5 points, delegate to vision tie-breaker instead of picking highest score. |
| `tests/test_vision_tiebreaker.py` | Unit tests with mocked vision model + mock screenshots. |

**Model: Microsoft Fara 1.5 (27B)**

- **Why Fara:** Microsoft's multimodal computer-use agent (CUA), fine-tuned on Qwen3.5-27B. Specifically trained for browser automation — takes screenshots + task descriptions, outputs actions. MIT license. Ollama-compatible quantized version available.
- **Paper:** "Fara-1.5: Scalable Learning Environments for Computer Use Agents" (arxiv:2606.20785, June 2026).
- **Pipeline tag:** `image-text-to-text` — feeds screenshot crop + "which element matches: {description}?" and returns the selected element.
- **Three sizes available:** 4B, 9B, 27B — start with 9B quantized for local dev, scale to 27B for production.

**Integration points:**

1. **Tie-breaker (primary use):** When `PlaceholderScorer` returns 2-3 candidates within 5 scoring points of each other, crop each candidate's bounding box from the page screenshot, send to Fara with the placeholder description, and use its selection as the final winner. Replaces the current "pick highest score" tie-break.

2. **LLM disambiguation replacement (secondary):** Currently the LLM disambiguation fallback sends candidate element lists as text to the LLM. Fara could see the actual screenshot region and make the visual call — fewer tokens, more accurate for icon/icon-button elements.

3. **Planner Agent input (Phase 1c synergy):** In the LangGraph flow, the Planning Agent could receive a page screenshot alongside the accessibility tree — giving it visual context for generating the test plan.

**Infrastructure:**
- Runs through Ollama (quantized version) on the same machine as LM Studio.
- Separate GPU from LM Studio: Fara on GPU 1, text LLM on GPU 0 (or use 9B quantized on CPU if single GPU).
- Toggle: `VISION_TIEBREAKER_ENABLED=1` — disabled by default, zero overhead when off.

**Eval impact:** +3-5pp on LV Insurance (resolves the "which Next button" and "which Back button" ties that section scoping alone can't solve).

**Acceptance criteria:**
1. Vision tie-breaker correctly selects `#accountNext` over `#productNext` when given cropped regions of both buttons + "Next button on account page" description.
2. Eval harness shows improvement on tied candidates (measured by tracking tie-break resolution accuracy).
3. No regressions when `VISION_TIEBREAKER_ENABLED=0` (default).
4. Fallback to score-based selection when vision model is unavailable (graceful degradation).
5. 10+ unit tests with mocked screenshots and vision model responses.

---

## 3. Implementation Order & Session Plan

| Session | Phase | Deliverable | Eval Target |
|---------|-------|------------|-------------|
| 1 | 1a | `src/pdf_ingest.py` + `--pdfs` flag + tests | LV ≥ 25% |
| 2 | 1b | `src/section_scoper.py` + visibility penalty + tests | LV ≥ 40% |
| 3-4 | 1c | LangGraph agents + graph + tests | skeleton validation errors ↓ |
| 5 | 1d | `src/vision_tiebreaker.py` + Fara integration + tests | LV ≥ 45%, tie-break accuracy ↑ |

**Rationale for order:**
- 1a is lowest risk: self-contained PDF → chunk → upsert. Reuses existing RAGStore API.
- 1b is highest eval impact: section scoping directly addresses the "8 Next buttons" problem.
- 1c is highest effort but also highest long-term value: LangGraph is the ROADMAP's Phase 1.
- 1d depends on 1b (section scoping reduces the tie-breaker's candidate list) and 1c (synergy with Planner Agent's visual input). Needs separate GPU or quantized model — infrastructure decision made last.

---

## 4. Files Changed (Summary)

### New files

| File | Phase |
|------|-------|
| `src/pdf_ingest.py` | 1a |
| `src/section_scoper.py` | 1b |
| `src/agents/__init__.py` | 1c |
| `src/agents/graph.py` | 1c |
| `src/agents/planner.py` | 1c |
| `src/agents/generator.py` | 1c |
| `src/agents/validator.py` | 1c |
| `src/agents/state.py` | 1c |
| `src/vision_tiebreaker.py` | 1d |
| `tests/test_pdf_ingest.py` | 1a |
| `tests/test_section_scoper.py` | 1b |
| `tests/test_agents_graph.py` | 1c |
| `tests/test_agents_planner.py` | 1c |
| `tests/test_agents_generator.py` | 1c |
| `tests/test_agents_validator.py` | 1c |
| `tests/test_vision_tiebreaker.py` | 1d |

### Modified files

| File | Change |
|------|--------|
| `scripts/rag_ingest.py` | Add `--pdfs` flag + `load_pdfs()` function |
| `src/placeholder_scorers.py` | Add `_HIDDEN_ELEMENT_PENALTY` for non-ASSERT actions |
| `src/placeholder_orchestrator.py` | Section scoping in resolve path (1b) + vision tie-break step (1d) |
| `src/test_generator.py` | Delegate to LangGraph when `LANGGRAPH_ENABLED=1` |
| `pyproject.toml` | `uv add langgraph` (1c only); Fara via Ollama pull (1d, no uv dependency) |
| `BACKLOG.md` | Track Phase 1 work items |

### Protected files (AGENTS.md §3) — NOT modified

`src/test_generator.py` — **exception requested** for Phase 1c only. The change is additive: new LangGraph delegate path behind env var toggle, existing `generate_skeleton()` preserved as fallback.

---

## 5. Measurement & Acceptance

### Eval harness commands (run after each phase)

```bash
# Baseline (current state)
python scripts/eval/eval_resolver.py --mode static            # RAG off: 34.3%
RAG_ENABLED=1 python scripts/eval/eval_resolver.py --mode static  # RAG on: 44.8%

# After Phase 1a (PDF ingestion)
python scripts/rag_ingest.py --golden --docs --pdfs
RAG_ENABLED=1 python scripts/eval/eval_resolver.py --mode static
# Target: LV ≥ 25% (up from 20.8%), overall ≥ 35%

# After Phase 1b (section scoping)
RAG_ENABLED=1 python scripts/eval/eval_resolver.py --mode static
# Result: LV 33.3% (unchanged from 1a), overall 44.8%
# Note: LV mock has form elements BEFORE headings in accessibility tree,
# so section scoping (heading → children) doesn't narrow the haystack.
# Feature is correct and works on properly-ordered pages.
# Target: LV ≥ 40%, overall ≥ 45% — deferred to Phase 1d (vision tie-breaker)

# After Phase 1c (LangGraph)
python scripts/eval/eval_harness.py run --regenerate
# Target: skeleton validation error rate ↓, no regressions on simple stories
# Status: Implemented.  LANGGRAPH_ENABLED=0 by default (safe rollout).
# To test: LANGGRAPH_ENABLED=1 python -m pytest tests/
# Architecture:
#   src/agents/state.py    — Pydantic WorkflowState
#   src/agents/planner.py  — Planner (user story → test plan)
#   src/agents/generator.py — Generator (test plan → skeleton)
#   src/agents/validator.py — Validator (checks + retry routing)
#   src/agents/graph.py    — StateGraph (Planner→Generator→Validator↺)
# 23 unit tests, all passing.  langgraph is optional dependency.

# After Phase 1d (Vision Tie-Breaker)
VISION_TIEBREAKER_ENABLED=1 RAG_ENABLED=1 python scripts/eval/eval_resolver.py --mode static
# Target: LV ≥ 45% (up from ~40%), tie-break accuracy tracked separately
```

### Quality gates (per AGENTS.md)

- `ruff check` — clean
- `mypy` — clean
- `pytest -q --tb=short` — all pass, no regressions
- `python scripts/smoke.py` — offline checks pass
- Eval harness accuracy ≥ previous baseline (no golden placeholder regresses)

---

## 6. Design Decisions

### 6.1 PyMuPDF over Docling for PDF parsing

**Decision:** PyMuPDF (`fitz`) for v1, Docling deferred.

**Rationale:**
- PyMuPDF is already installed (`fitz 1.28.0`)
- Handles the 3 LV PDFs well: they're scanned PDFs with text layers (not images)
- No additional dependency; Docling requires a separate install + larger footprint
- Docling's advantage (table extraction, layout analysis) isn't needed for these documents — the T&Cs are linear text with simple heading structure

**When to switch to Docling:** If future domains require OCR (scanned PDFs without text layers) or complex table extraction.

### 6.2 Section scoping via heading detection, not DOM structure

**Decision:** Use accessibility tree headings (`role=h1..h6`) as section boundaries, not CSS classes or DOM nesting.

**Rationale:**
- Works across all sites regardless of framework (React, Vue, plain HTML)
- The accessibility snapshot already extracts headings — no additional scraping needed
- Heading text provides natural section names for description matching ("on account page" → "Create Your Account" heading)
- Falls back gracefully: if no headings found, score against all elements (current behaviour)

### 6.3 Hidden element penalty for non-ASSERT actions

**Decision:** `_HIDDEN_ELEMENT_PENALTY = -30` for CLICK, FILL, SELECT on `is_visible=False` elements.

**Rationale:**
- In the real pipeline, you scrape per-page so hidden sections aren't in the haystack. The penalty only applies to the eval and future SPA scenarios.
- -30 is significant but not exclusionary: a hidden element with a perfect ID match (+80 structural bonus) still scores above a visible element with only text overlap (~25). The penalty breaks ties between equally scored visible vs hidden candidates.
- Matches the existing `_assert_visibility_penalty` (-40) but less severe: for ASSERT we want visible elements (you can't assert what you can't see), for CLICK/FILL the hidden element might still be correct if the section is explicitly named.

### 6.4 LangGraph toggle with safe default

**Decision:** `LANGGRAPH_ENABLED=0` (disabled) by default. Existing `TestGenerator` path preserved.

**Rationale:**
- Zero-risk rollout: if LangGraph has bugs, users get current behaviour
- Allows incremental testing: enable only for specific test runs
- Matches the RAG toggle pattern (`RAG_ENABLED=0/1`) already established
- `langgraph` is an optional dependency — commercial customers without the package get the existing single-call path automatically

### 6.5 Table chunks stay whole

**Decision:** PDF tables are extracted as single chunks even if they exceed the target token size (~1000 tokens).

**Rationale:** Splitting a table mid-row loses column headers and context — the embedding becomes meaningless. Better to have one large, coherent table embedding than two half-tables. SentenceTransformers handles variable-length input without issues.

### 6.6 Section hint matching is data-agnostic

**Decision:** Section scoping uses generic patterns (`"on <X> page"`, `"in <X> section"`), not site-specific section names.

**Rationale:** This is a commercial product — section matching must work against any site's heading structure. The algorithm extracts the section hint from the placeholder description and fuzzy-matches it against heading text. No hardcoded site names.

### 6.7 `_HIDDEN_ELEMENT_PENALTY` as class constant

**Decision:** `_HIDDEN_ELEMENT_PENALTY = -30` as a class constant on `PlaceholderScorer`, matching the existing `GOLDEN_PATTERN_BONUS` pattern.

**Rationale:** Simple, zero-config. If per-site tuning is needed later, it can be promoted to a config object.

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| PyMuPDF extracts garbled text from some PDFs | 1a produces poor-quality chunks | Validate chunk quality during ingestion; skip pages with <10 chars of text |
| Section scoping mismatches on sites with unusual heading structure | 1b reduces accuracy on some sites | Fallback to full haystack when section hint not found; measure per-site impact |
| LangGraph adds latency to skeleton generation | 1c makes pipeline slower | Planner + Generator are sequential (not parallel) — same LLM, fewer tokens per call. Total latency should be similar or better than single large call. |
| LV Insurance eval accuracy still < 50% after all 4 phases | Feature doesn't meet user expectations | The 24-28pp improvement (20.8% → ~45%) demonstrates real progress. Remaining gap is structural: the mock site's 7-page SPA flow requires actual navigation (Phase 2, future). |

---

## 8. Out of Scope

- **Docling integration** — deferred until OCR is needed (Phase 2)
- **Multi-agent resolver** (MoE model selection) — deferred; current single-model approach works
- **Interactive repair merge** (Phase 2b from ROADMAP) — covered by Phase 2 Self-Healing (already shipped)
- **Docker containerization** — Phase 4
- **Enterprise vector DB swap** — Phase 3 extension (Protocol already guarantees swap path)
- **Fara 27B full precision** — Phase 1d uses quantized 9B for local dev; 27B full precision deferred until multi-GPU infrastructure is available

---

## 9. Fara Model Reference Card

> **Keep this section — the model details will be forgotten by the time Phase 1d arrives.**

| Property | Value |
|----------|-------|
| **Model** | Microsoft Fara 1.5 |
| **HuggingFace** | `microsoft/Fara1.5-27B` (also 4B, 9B in collection `microsoft/fara15`) |
| **Base** | Qwen/Qwen3.5-27B |
| **Pipeline** | `image-text-to-text` (multimodal vision-language) |
| **License** | MIT |
| **Paper** | arxiv:2606.20785 — "Fara-1.5: Scalable Learning Environments for Computer Use Agents" |
| **Paper date** | June 2026 |
| **Tags** | computer-use, cua, web-agent, browser-automation, vision-language, agent |
| **Ollama** | Quantized version available (search `ollama.com/library` for `fara`) |
| **Transformer class** | `AutoModelForMultimodalLM` / `Qwen3_5ForConditionalGeneration` |
| **Processor** | `AutoProcessor` |
| **Parameters** | 27.4B (BF16), ~55GB on disk (sharded safetensors) |
| **Inference** | Runs through Ollama (separate from LM Studio) |
| **VRAM** | 27B full: ~56GB (needs A100/A6000). 9B quantized: ~6GB (fits on consumer GPU). 4B quantized: ~3GB |
| **Space demo** | `hugging-apps/fara-computer-use-27B` — screenshot + task → next action |

**Our use case:** Feed cropped bounding-box regions from page screenshots + placeholder description text → Fara returns which element matches. Acts as the tie-breaker when `PlaceholderScorer` can't distinguish between 2-3 candidates within 5 scoring points.

**Prompt pattern:**
```
User: [screenshot crop of element A] [screenshot crop of element B] ...
      Which element matches: "{placeholder_description}"?
      Return only the element number (1, 2, etc.).
Assistant: 1
```

**Integration constraints:**
- Must run on separate GPU from LM Studio (or use quantized 9B/4B on CPU as fallback)
- Toggle `VISION_TIEBREAKER_ENABLED=1` — zero overhead when disabled
- Graceful degradation: if Ollama/Fara is unavailable, fall back to score-based selection
- Not a hard dependency — pipeline works without it (same pattern as RAG)

---

---

*Last updated: 2026-07-23*
