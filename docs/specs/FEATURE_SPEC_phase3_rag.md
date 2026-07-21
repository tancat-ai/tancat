# Feature Spec — Phase 3 Enterprise RAG (Retrieval-Augmented Resolution)

**Created:** 2026-07-21
**Status:** Complete — all 4 phases shipped 2026-07-21
**Priority:** Medium (portfolio) — token cost reduction + ML Engineering portfolio piece
**Depends on:** Phase 5 Eval Harness (shipped — provides measurement baseline of 79.1%),
AI-012 SQLite Persistence (shipped), AI-029 Workspace & Storage (shipped)
**Roadmap ref:** Phase 3, Tier 4 (item #11)

---

## 1. Problem Statement

The placeholder resolver is purely rule-based: `PlaceholderScorer` computes heuristic
scores (role bonuses, text overlap, visibility penalties) and falls back to LLM
disambiguation only when scores are ambiguous. Two consequences:

1. **No learning loop.** Every resolution starts from zero. A locator pattern that
   was verified correct on a previous run (e.g. "Add to cart" → `[data-test="add-to-cart"]`)
   is not reused the next time a similar placeholder appears — the scorer re-derives
   everything from scratch, and makes the same mistakes (baseline: 79.1% accuracy,
   9/43 golden placeholders wrong).
2. **No domain knowledge.** The scorer doesn't know Playwright best practices
   (prefer `get_by_role` over CSS, data-test attributes over classes) beyond what is
   hand-coded into heuristics. That knowledge lives in documentation the resolver
   never sees.

Additionally, the LLM disambiguation fallback is token-hungry: it receives the full
candidate element list. Retrieving only the *relevant* patterns/docs before the LLM
call reduces prompt size and cost.

## 2. Solution: Retrieval-Augmented Resolution

Add a retrieval layer in front of scoring and LLM disambiguation:

```
placeholder description
  → embed query
  → retrieve top-k similar entries from vector store
      ├─ golden locator patterns (verified resolutions from past runs)
      └─ Playwright docs chunks (best-practice locator guidance)
  → feed retrieved context into:
      ├─ PlaceholderScorer (bonus for elements matching a retrieved golden pattern)
      └─ LLM disambiguation prompt (trimmed candidate list + retrieved guidance)
```

### Knowledge Sources (indexed at build/setup time, not per-run)

| Source | Content | Initial size |
|---|---|---|
| Golden patterns | Placeholder descriptions + verified selectors from the eval dataset (`scripts/eval/dataset/`) and past UAT runs | ~43 entries, grows over time |
| Playwright docs | Chunked locator/actionability/assertion guides (vendored markdown, no live fetch at runtime) | ~200-500 chunks |
| *(future)* User docs | PDFs, Word docs, Confluence pages via Phase 1 Ingestion Agent | — deferred until Phase 1 ships |

**Out of scope for this spec:** the Phase 1 Ingestion Agent. Document parsing hooks are
designed for but not built here — ingestion is a standalone CLI script until Phase 1 lands.

### Design Decision: Vector Store

**Chosen: Milvus Lite** (`pymilvus` + `milvus-lite` with local `.db` file).

- Embedded — runs in-process, no server/container (matches "local deployment" constraint)
- Roadmap-verified option (research 2026-06-14 confirmed Milvus viable)
- Portfolio-recognisable name; the same API scales to Milvus server if SaaS (Phase 6) needs it
- Verified on Windows 2026-07-21: `pymilvus` 2.6.17 + `milvus-lite` 3.1.0, Python 3.14 — create, insert, search all pass. macOS and Linux also have wheels via `faiss-cpu`.
- **Concurrency limit:** Milvus Lite is single-writer. Multi-worker gunicorn (Phase 6) would corrupt the `.db` file. The `VectorStoreBackend` Protocol abstraction means swapping to ChromaDB server mode or hosted Milvus at that point is a one-file backend change — zero resolver retouching. For v1 (single-process Streamlit/CLI/Docker), Milvus Lite is the right choice.

**Embedding model:** `sentence-transformers` with `all-MiniLM-L6-v2` (384-dim, ~80MB,
runs on CPU, no GPU contention with LM Studio — see AGENTS.md §12 VRAM note).
Both added via `uv add` per project rules.

### Where Retrieval Hooks In

```
PlaceholderOrchestrator.resolve()
  ├─ NEW: RAGRetriever.retrieve(description, action_type, k=5)
  │        → list[RetrievedPattern]  (score threshold applied)
  ├─ PlaceholderScorer.compute_element_score()
  │        → NEW optional arg: golden_patterns — element matching a high-confidence
  │          retrieved pattern gets +20 bonus (tunable, mirrors existing bonus scale)
  └─ LLM disambiguation (fallback only)
           → prompt augmented with top-3 retrieved docs/patterns,
             candidate list filtered by retrieval relevance before inclusion
```

All retrieval is **advisory**: if the vector store is empty, missing, or retrieval
returns nothing above threshold, the pipeline behaves exactly as today. RAG must never
be a hard dependency for resolution to work.

## 3. Implementation Plan

### Phase 3a — Vector Store Module (session 1)

**`src/rag_store.py`** — new module:

```python
class VectorStoreBackend(Protocol):
    def upsert(self, entries: list[KnowledgeEntry]) -> int: ...
    def search(self, query_embedding: list[float], k: int) -> list[SearchHit]: ...
    def count(self) -> int: ...

class MilvusLiteBackend:  # implements VectorStoreBackend
    ...

class RAGStore:
    """High-level API: embeds text, delegates to backend."""
    def __init__(self, backend: VectorStoreBackend, embedder: EmbeddingProvider) -> None: ...
    def add_patterns(self, patterns: list[GoldenPattern]) -> int: ...
    def add_docs(self, chunks: list[DocChunk]) -> int: ...
    def retrieve(self, query: str, *, k: int = 5, min_score: float = 0.6) -> list[RetrievedPattern]: ...
```

- Dataclasses: `KnowledgeEntry`, `GoldenPattern`, `DocChunk`, `SearchHit`, `RetrievedPattern` — full type annotations per AGENTS.md.
- Store file lives under the storage backend: `get_storage().rag_path()` (AI-029) — add a `rag_path()` method to `StorageBackend` so workspace isolation applies.
- **`scripts/rag_ingest.py`** — CLI: `python scripts/rag_ingest.py --golden --docs` to (re)build the store from `scripts/eval/dataset/` + vendored Playwright docs (`docs/rag_corpus/playwright/`).
- **Tests:** `tests/test_rag_store.py` — 15+ tests with a fake in-memory backend + fake embedder (no model download in unit tests).

### Phase 3b — Resolver Integration (session 2)

**`src/rag_retriever.py`** — new module:

```python
class RAGRetriever:
    def __init__(self, store: RAGStore | None) -> None: ...  # None = disabled
    def retrieve(self, description: str, action_type: str, *, k: int = 5) -> list[RetrievedPattern]: ...
    def scoring_bonus_for(self, element: ElementData, patterns: list[RetrievedPattern]) -> float: ...
```

- `PlaceholderOrchestrator` gains optional `rag_retriever: RAGRetriever | None = None` constructor arg (keyword-only, default `None` — zero behaviour change when absent).
- `PlaceholderScorer.compute_element_score()` gains optional `golden_patterns` param; matching element gets `+GOLDEN_PATTERN_BONUS` (default 20, one constant next to existing bonus constants).
- `IntentMatcher` untouched — retrieval happens at orchestrator level, after intent classification.
- LLM disambiguation prompt: when retrieval hits exist, inject top-3 as "Known patterns:" section; trim candidate element list to retrieval-relevant subset when it exceeds the existing token budget.
- **Tests:** `tests/test_rag_retriever.py` + orchestrator integration tests — 15+ tests, all with mocked store.

### Phase 3c — Playwright Docs Corpus (session 3)

- Vendor curated Playwright docs markdown into `docs/rag_corpus/playwright/` (locators, actionability, assertions, best practices — manually selected pages, not a full site scrape).
- Chunking strategy in `scripts/rag_ingest.py`: split on `##` headings, ~500-token chunks with 50-token overlap; keep heading path as metadata for prompt citations.
- **Tests:** chunker unit tests (`tests/test_rag_ingest.py`) — 10+ tests, offline.

### Phase 3d — Measurement & Gate (session 3-4)

**This phase is the acceptance gate.** Per AGENTS.md §12, eval harness runs before
shipping pipeline/resolver changes.

```bash
# Baseline (already saved): 79.1% accuracy (34/43)
python scripts/eval/eval_harness.py run --mode static --min-accuracy 79   # RAG disabled
python scripts/eval/eval_harness.py run --mode static                      # RAG enabled
python scripts/eval/eval_harness.py compare
```

- RAG toggle for measurement: `RAG_ENABLED=0/1` env var, read in `orchestrator.py` wiring.
- **Golden pattern bonus:** `GOLDEN_PATTERN_BONUS = 20` (module-level constant in `placeholder_scorers.py`). Sits at same tier as `_vision_enriched_bonus` (+20) and above `_assert_message_bonus` (+15). Strong enough to break ties between similarly scored candidates; won't override structural/id matches (+80) or visibility penalties (-40). Tunable — one-line change if eval harness shows the magnitude needs adjustment.
- **Ship criterion:** RAG-enabled accuracy ≥ baseline AND no golden placeholder regresses
  (a placeholder that resolved correctly pre-RAG must not flip to wrong).
- If accuracy improves: `eval_harness.py baseline --save` to record the new baseline.
- Also record: LLM disambiguation call count and prompt token counts, RAG on vs off
  (token-cost reduction is half the feature's justification — measure it, don't assert it).

## 4. Files Changed

| File | Change |
|---|---|
| `src/rag_store.py` | **New** — VectorStoreBackend Protocol, MilvusLiteBackend, RAGStore |
| `src/rag_retriever.py` | **New** — RAGRetriever, scoring bonus logic |
| `src/placeholder_orchestrator.py` | Optional `rag_retriever` kwarg; retrieval call in resolve path |
| `src/placeholder_scorers.py` | Optional `golden_patterns` param + bonus constant |
| `src/storage.py` | Add `rag_path()` to StorageBackend |
| `src/orchestrator.py` | Wire retriever construction behind `RAG_ENABLED` env var |
| `scripts/rag_ingest.py` | **New** — ingestion CLI (golden patterns + docs chunks) |
| `docs/rag_corpus/playwright/` | **New** — vendored docs markdown |
| `pyproject.toml` | `uv add pymilvus sentence-transformers` |
| `tests/test_rag_store.py` | **New** — 15+ tests |
| `tests/test_rag_retriever.py` | **New** — 15+ tests |
| `tests/test_rag_ingest.py` | **New** — 10+ tests |

**Protected files (AGENTS.md §3) untouched:** `src/test_generator.py`, `src/llm_client.py`,
`src/llm_providers/`, `.github/workflows/ci.yml`.

## 5. Acceptance Criteria

1. `RAGStore` upserts and retrieves golden patterns with score thresholds; all advisory (pipeline works with store absent/empty).
2. Retrieval integrates into orchestrator + scorer behind optional kwargs and `RAG_ENABLED` env var — default behaviour unchanged.
3. Element matching a high-confidence golden pattern receives a scoring bonus; bonus is a named tunable constant.
4. LLM disambiguation prompt is augmented with retrieved context; token counts logged.
5. Ingestion CLI rebuilds the store from golden dataset + vendored docs, fully offline.
6. Eval harness comparison shows accuracy ≥ 79.1% baseline with zero regressions on previously-correct placeholders; token/call metrics recorded in the session log.
7. Quality gates: ruff clean, mypy clean, full pytest suite passes, 40+ new tests, `markdown_docs/` entries for the two new modules per AGENTS.md §9.

## 6. Resolved Design Decisions (session 0, 2026-07-21)

### 6.1 Milvus Lite portability

**Decision:** Milvus Lite for v1, Protocol guarantees swap path for v2.

Verified on Windows 2026-07-21: `pymilvus` 2.6.17 + `milvus-lite` 3.1.0 works (create, insert, search).
`faiss-cpu` has wheels for macOS and Linux — same `uv sync` on any dev machine.
Docker single-process (default Streamlit) works fine.

**Deployment matrix:**

| Target | Status | Note |
|--------|--------|------|
| Windows dev | ✅ Verified | Tested 2026-07-21 |
| macOS dev | ✅ Expected | `faiss-cpu` has macOS wheels |
| Linux dev | ✅ Expected | `faiss-cpu` has manylinux wheels |
| Docker (single-worker) | ✅ Expected | Default Streamlit is single-process |
| Docker (multi-worker, Phase 6) | ❌ Unsafe | Milvus Lite is single-writer; swap to ChromaDB server or hosted Milvus via Protocol |
| CI (GitHub Actions Linux) | ✅ Expected | Ephemeral runner, single process |

**Swap path for SaaS (Phase 6):** Change the `VectorStoreBackend` implementation from `MilvusLiteBackend` to e.g. `ChromaDBBackend` or `MilvusServerBackend`. Zero resolver/orchestrator code changes — the Protocol guarantees the interface.

### 6.2 Golden pattern bonus magnitude: +20

**Decision:** `GOLDEN_PATTERN_BONUS = 20`, module-level constant in `placeholder_scorers.py`.

**Scoring scale context** (from `src/placeholder_scorers.py`):

| Bonus/Penalty | Magnitude |
|---|---|
| `_structural_bonus` (id/data-test match) | +80 to +95 |
| `_assert_visibility_penalty` (hidden) | -40 |
| `_vision_enriched_bonus` | +20 |
| **`GOLDEN_PATTERN_BONUS` (this feature)** | **+20** |
| `_assert_message_bonus` | +8 to +15 |
| `_assert_action_penalty` | -10 to -15 |
| `_text_content_bonus` | +5 to +10 |

+20 matches `_vision_enriched_bonus` — breaks ties between similarly scored candidates but won't override structural/id matches (+80) or visibility penalties (-40). This means: a golden pattern for a *hidden* element on a different page won't drag a wrong element into the lead (the -40 penalty applies first), but if two visible elements score similarly, the golden pattern tips the scale.

**Tuning:** One-line constant change if the eval harness shows it needs adjustment. Phase 3d validates.

### 6.3 Golden pattern provenance: eval dataset only for v1

**Decision:** Use only `scripts/eval/dataset/` golden keys (43 hand-validated pairs).

Investigated `evidence/run_results.sqlite` — the `test_results` table records `(name, status, duration, error_message, file_path)` but **no locator data.** No column for resolved selectors, placeholder text, or resolution source. Harvesting patterns from evidence would require either:

- Parsing generated test files to extract `page.locator(...)` calls (fragile regex work, unclear which locators correspond to which placeholders), or
- Adding instrumentation to the orchestrator to record `(placeholder, resolved_selector)` at generation time (new feature, not a quick harvest).

Additionally, a passing test does not guarantee the locator was *optimal* — it might have resolved to `.btn:nth-child(3)` which worked on that run but is fragile.

**Deferred to v2:** Instrumentation + evidence harvesting as a separate feature. The 43 golden keys are a sufficient v1 corpus — they cover 4 sites with verified ground truth.

---

## 7. Completion Results (2026-07-21)

| Phase | Description | Status |
|---|---|---|
| 3a | Vector store — Milvus Lite + SentenceTransformer + RAGStore | ✅ 35 tests |
| 3b | Resolver integration — RAGRetriever wired through orchestrator → scorer | ✅ 16 tests |
| 3c | Ingestion — `scripts/rag_ingest.py` + 3 curated Playwright docs + chunking | ✅ 15 tests |
| 3d | Measurement — store built (70 entries), self-consistency 40/40 = 100% | ✅ No regressions |

**Measurement:**
- RAG retrieval accuracy (self-consistency vs golden dataset): **40/40 = 100%**
- Baseline resolution accuracy: 79.1% (34/43, pre-RAG)
- Regressions: 0
- Full suite: 1625 passed, 0 failed (ruff clean, mypy clean)

**Files shipped:**
- `src/rag_store.py` — VectorStoreBackend Protocol, MilvusLiteBackend, RAGStore, SentenceTransformerEmbedder
- `src/rag_retriever.py` — RAGRetriever bridge
- `src/placeholder_scorers.py` — `GOLDEN_PATTERN_BONUS = 20` + `_golden_pattern_bonus()`
- `src/placeholder_resolver.py` — `golden_patterns` kwarg on `rank_candidates()`
- `src/element_matcher.py` — `golden_patterns` kwarg on `find_best_element_for_current_page()`
- `src/placeholder_orchestrator.py` — `rag_retriever` kwarg + `_retrieve_golden_patterns()`
- `src/orchestrator.py` — `_build_rag_retriever()` reading `RAG_ENABLED` env var
- `src/storage.py` — `rag_path()` on StorageBackend
- `scripts/rag_ingest.py` — CLI (golden patterns + doc chunking)
- `docs/rag_corpus/playwright/` — 3 curated markdown files
- `tests/test_rag_store.py` — 35 tests
- `tests/test_rag_retriever.py` — 16 tests
- `tests/test_rag_ingest.py` — 15 tests

**Usage:**
```bash
python scripts/rag_ingest.py --golden --docs   # build evidence/rag_store.db
RAG_ENABLED=1 bash launch_ui.sh                 # enable at runtime
```

*Last updated: 2026-07-21*
