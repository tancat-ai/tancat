# AI-045 #4 — PDF OCR Wiring + Doc-Chunk Dedup Key — Overnight Plan

**Created:** 2026-08-24 (planned for overnight autonomous run)
**Backlog ref:** `BACKLOG.md` → AI-045 §8.2 (PDF OCR wiring) + §8.2 (doc-chunk dedup gap)
**Status:** 📋 plan — not started
**Protected files:** none touched. `src/pdf_ingest.py`, `src/rag_store.py`, `scripts/rag_ingest.py`, `src/ocr_backends.py` are all non-protected.

---

## 1. Problem

Two related gaps in the document-ingestion path, both flagged **High** in the
2026-08-17 commercial-readiness audit (`docs/plans/RESEARCH_SAAS_AND_LAUNCH.md` §8.2):

### 1.1 PDF OCR not wired into the ingest path
- `src/ocr_backends.py` exists with two backends:
  - `PyMuPDFBackend` (default, CPU) — wraps `src.pdf_ingest.ingest_pdf()`
  - `UnlimitedOCRBackend` (opt-in, GPU) — Baidu 3B vision model, rasterises pages to 300 DPI PNG
- **Only the dormant LangGraph path** (`src/agents/pipeline_graph.py:141`) calls `get_ocr_backend()`.
- The production ingest path (`scripts/rag_ingest.py --pdfs` → `src.pdf_ingest.ingest_pdf_directory`) **hardcodes PyMuPDF** and never consults the OCR backend.
- Result: scanned insurance PDFs (the core domain) yield zero content in the production path, even when the user has configured `OCR_BACKEND=unlimited-ocr`.
- Image-only pages are **silently skipped** in `pdf_ingest.py::ingest_pdf` with an `info` log — no OCR fallback, no loud warning.

### 1.2 Doc chunks have no dedup key
- `RAGStore.add_docs(chunks)` (src/rag_store.py:659) does an **unconditional `upsert`** of every chunk.
- No dedup key. Re-ingesting the same PDF (e.g. `--pdfs` after `--reindex`, or `--bundled` + `--pdfs` in sequence) **duplicates every chunk** in the vector store.
- `delete_learned()` keeps `entry_type in ("golden", "doc")` — so doc duplicates persist across prune cycles.
- The learned-pattern path already has a dedup key (`action_type, description, site_hash` via `find_learned`) — docs lack the equivalent.

---

## 2. Scope

### In scope
1. **OCR wiring** — make `ingest_pdf_directory` / `ingest_pdf` consult `get_ocr_backend()` so the configured backend (PyMuPDF default, UnlimitedOCR opt-in) is honoured in the production path. Image-only pages should attempt OCR fallback when the backend is available; otherwise loud WARNING (not silent `info`).
2. **Dedup key** — give doc chunks a stable content-based dedup key so re-ingesting the same chunk is a no-op (or an in-place refresh), never a duplicate row.
3. **CLI surface** — `scripts/rag_ingest.py` gains a visible report of duplicates detected/skipped on each run.
4. **Tests** — unit tests for OCR wiring (mocked backends, no GPU) + dedup key (hermetic `InMemoryBackend` or temp-file Milvus).
5. **Documentation** — update `markdown_docs/src/pdf_ingest.py.md` + `markdown_docs/src/rag_store.py.md` via document-manager; add a session record.

### Out of scope
- **Table splitting** (§8.2 Medium) — large tables become one giant chunk; deferred.
- **Tokenizer-aware chunking** (§8.2 Medium) — char-based heuristic is adequate for advisory retrieval; deferred.
- **OCR model selection UX** — the `ocr_backend` setting already exists (B-036 Phase 4); no new UI.
- **GPU OCR in tests** — `UnlimitedOCRBackend` is mocked; no real model load in CI.
- **Multi-writer concurrency** (AI-045 #3) — separate decision item, not this task.

---

## 3. Design

### 3.1 OCR wiring

**Principle:** `pdf_ingest.py` is the extraction layer. It should be backend-agnostic. The OCR backend is the *text source*; `pdf_ingest` is the *chunker*.

**Current coupling problem:** `PyMuPDFBackend.parse_pdf()` calls `ingest_pdf()` which calls `_import_fitz()` directly. If we naively make `ingest_pdf` call `get_ocr_backend()`, we get a circular dependency (backend → pdf_ingest → backend).

**Resolution:** Introduce a **page-level text hook** in `pdf_ingest.py`:

```python
# src/pdf_ingest.py

def ingest_pdf(
    filepath: Path,
    *,
    ocr_fallback: Callable[[Path, int], str] | None = None,
) -> list[DocChunk]:
    """
    ocr_fallback: called for image-only pages (len(page.get_text()) < MIN_PAGE_CHARS).
                  Signature: (pdf_path, page_number_1indexed) -> extracted_text (may be "").
                  When None, image-only pages are skipped with a WARNING.
    """
```

The caller (`rag_ingest.py` or a new wrapper) decides whether to pass an OCR fallback based on the configured backend:

```python
# scripts/rag_ingest.py (or a helper in src/)

def _ocr_fallback_for(backend: OcrBackend) -> Callable[[Path, int], str] | None:
    if backend.name == "unlimited-ocr" and backend.available:
        # Render the specific page to PNG, run OCR on just that page
        return lambda path, pageno: _ocr_single_page(path, pageno, backend)
    return None  # PyMuPDF backend has no page-level OCR
```

**Key decision:** OCR fallback is **page-scoped**, not whole-document. When PyMuPDF finds 8 of 10 pages have text but 2 are scanned, we don't want to re-OCR the whole document (expensive, GPU). We OCR just the 2 image-only pages and merge the text in. This is the natural reading of "image-only pages are skipped" → "image-only pages should be OCR'd when the backend supports it."

**Loud failure:** when `ocr_fallback is None` and a page is image-only, log a **WARNING** (not `info`) with the page number + a hint (`Set OCR_BACKEND=unlimited-ocr to extract scanned pages`). This makes the gap visible without breaking the run.

**What we do NOT do:**
- Do not change `UnlimitedOCRBackend.parse_pdf` to be page-scoped (its current API is whole-document; a page-scoped variant is a new method `parse_page(path, page_number)` — add it if needed, but the fallback closure can also rasterise a single page itself via fitz and call the model on one image).
- Do not add a new backend. The existing two are sufficient.

### 3.2 Dedup key

**Principle:** A doc chunk's identity is its *content*, not its position. Two chunks are duplicates iff their normalised text + source match.

**Dedup key formula:**

```python
def doc_chunk_key(chunk: DocChunk) -> str:
    """Stable dedup key: sha256 of normalised text + source + heading_path."""
    normalised = _normalise_for_dedup(chunk.text)
    payload = f"{chunk.source}\x00{chunk.heading_path}\x00{normalised}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _normalise_for_dedup(text: str) -> str:
    """Collapse whitespace, strip, lowercase. Stable across re-extraction."""
    return re.sub(r"\s+", " ", text).strip().lower()
```

**Why normalise?** PyMuPDF text extraction can vary subtly across versions/platforms (trailing spaces, line-break placement). Lowercasing + whitespace collapse makes the key robust to cosmetic re-extraction differences while still catching genuine content changes.

**Where the key lives:**
- Add `dedup_key: str = ""` to `DocChunk` dataclass (computed by `ingest_pdf` before returning, or computed by `add_docs`).
- Add `"dedup_key"` to the `KnowledgeEntry.metadata` in `add_docs`.
- Milvus dynamic field — no schema change needed (the collection already has `enable_dynamic_field=True`).

**Dedup semantics in `add_docs`:**

Option A (in-memory pre-filter): `add_docs` queries the existing store for `dedup_key` values, filters out chunks whose key already exists, and inserts only new ones. Returns `(inserted, skipped)` tuple.

Option B (backend-level): Add a `find_by_dedup_key(key)` method to the backend protocol (like `find_learned` for learned patterns). `add_docs` checks each chunk's key against the store before inserting.

**Chosen: Option A** (simpler, no backend protocol change, works with any backend including in-memory). Implementation:

```python
def add_docs(self, chunks: list[DocChunk]) -> tuple[int, int]:
    """
    Returns (inserted_count, skipped_duplicate_count).
    Backwards compat: existing callers that expect int get inserted_count
    (they unpack or use [0]).
    """
    if not chunks:
        return (0, 0)
    self._ensure_embedder_match()
    
    # Query existing dedup keys (doc entries only)
    existing_keys = set(self._backend.query_dedup_keys("doc"))
    
    new_chunks = [c for c in chunks if c.dedup_key not in existing_keys]
    skipped = len(chunks) - len(new_chunks)
    
    if not new_chunks:
        return (0, skipped)
    
    texts = [c.text for c in new_chunks]
    vectors = self._embedder.embed_batch(texts)
    entries = [...]  # same as before, plus dedup_key in metadata
    inserted = self._backend.upsert(entries)
    return (inserted, skipped)
```

**New backend method:** `query_dedup_keys(entry_type: str) -> list[str]` — queries the collection for `dedup_key` field where `entry_type` matches. One batch query, not per-chunk.

**Return type change:** `add_docs` returns `tuple[int, int]` instead of `int`. This is a **breaking change** for callers. Mitigation:
- Audit all callers of `add_docs` (grep).
- Update each caller to unpack the tuple.
- The `rebuild_store` function in `rag_ingest.py` already returns a `dict[str, int]` — extend it to include `docs_skipped` / `pdfs_skipped` counts.

### 3.3 CLI surface

`scripts/rag_ingest.py --pdfs` (and `--reindex`) should print:
```
Ingested 42 pdf chunks (38 new, 4 duplicates skipped)
```
This makes dedup visible without being noisy.

`--stats` should also show a `duplicates` count (re-query existing keys vs stored count — or track in a sidecar; simplest: just show the insert/skip breakdown from the last run in the result dict).

### 3.4 What about existing duplicates in live stores?

The user's existing `rag_store.db` may already have duplicates from prior re-ingests. Two options:
- **Migrate:** a one-time `--prune-dupes` flag that scans doc entries, groups by `dedup_key`, keeps the first (lowest `id`), deletes the rest.
- **Reindex:** the existing `--reindex` flag already wipes + rebuilds — after this change, the rebuild is dedup-free by construction.

**Chosen:** Add `--prune-dupes` (cheap, non-destructive to the rest of the store, useful for the user's existing store). `--reindex` remains the nuclear option.

---

## 4. Implementation plan (sequential, each step gated)

### Step 1: OCR wiring in `pdf_ingest.py`
- [ ] Add `ocr_fallback` param to `ingest_pdf`
- [ ] Change image-only page log from `info` to `warning` with hint
- [ ] Add `parse_page(path, page_number)` method to `OcrBackend` ABC + `UnlimitedOCRBackend` (rasterise single page, run model on one image)
- [ ] Add `_ocr_single_page` helper in `rag_ingest.py` (or a new `src/pdf_ocr.py`) that implements the fallback closure
- [ ] Wire `ingest_pdf_directory` to accept + pass through `ocr_fallback`
- [ ] `rag_ingest.py --pdfs` consults `get_ocr_backend()` and passes the fallback
- **Gate:** `pytest tests/test_pdf_ingest.py tests/test_ocr_backends.py -q` green

### Step 2: Dedup key in `rag_store.py`
- [ ] Add `dedup_key: str = ""` to `DocChunk`
- [ ] Add `doc_chunk_key(chunk)` + `_normalise_for_dedup(text)` helpers in `pdf_ingest.py` (or `rag_store.py`)
- [ ] Compute `dedup_key` in `ingest_pdf` before returning chunks
- [ ] Add `query_dedup_keys(entry_type)` to `MilvusLiteBackend` + backend protocol
- [ ] Change `add_docs` to return `tuple[int, int]` with pre-filter
- [ ] Add `"dedup_key"` to `KnowledgeEntry.metadata` in `add_docs`
- **Gate:** `pytest tests/test_rag_store.py -q` green (update existing tests for new return type)

### Step 3: Update callers
- [ ] Grep all `add_docs` callers; update to unpack tuple
- [ ] `rag_ingest.py::rebuild_store` — extend result dict with `docs_skipped` / `pdfs_skipped`
- [ ] `rag_ingest.py` CLI — print insert/skip breakdown
- [ ] `--prune-dupes` flag (new) — scan + dedup existing doc entries
- **Gate:** `pytest tests/test_rag_ingest*.py -q` green (or wherever those tests live)

### Step 4: New tests
- [ ] OCR wiring: mocked `UnlimitedOCRBackend.parse_page` called for image-only page; not called for text page; WARNING logged when no fallback
- [ ] Dedup: re-ingesting same chunk → `(inserted=1, skipped=1)` on second call
- [ ] Dedup: different chunks → both inserted
- [ ] Dedup: whitespace-cosmetic difference → same key → skipped
- [ ] `--prune-dupes`: N dupes → N-1 removed
- **Gate:** full `pytest -q` green

### Step 5: De-sloppify + verify
- [ ] Review all changed files for over-defensive code, redundant checks, dead code
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy` clean
- [ ] `pytest -q --tb=short` full suite green
- [ ] `python scripts/smoke.py` green
- **Gate:** all green

### Step 6: Documentation + record
- [ ] Update `markdown_docs/src/pdf_ingest.py.md` (document-manager skill)
- [ ] Update `markdown_docs/src/rag_store.py.md` (document-manager skill)
- [ ] Create session record: `docs/sessions/2026-08-24_ai045_4_pdf_ocr_dedup.md`
- [ ] Update `BACKLOG.md` AI-045 #4 status (⚠️ NOT committed — status updates happen at ship-it with the user)
- [ ] Update `CHANGELOG.md` [Unreleased] section
- **Gate:** docs present, CHANGELOG updated

---

## 5. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| `add_docs` return type change breaks hidden callers | Grep all callers first (Step 3); the codebase is well-tested so any break surfaces in Step 5 |
| Milvus dynamic field `dedup_key` not returned by `query` | Verify in Step 2 with a temp-file store; add to `output_fields` in the query |
| OCR `parse_page` for UnlimitedOCR is untested against the real model | It's mocked in tests; the real path is opt-in + GPU-gated. The PyMuPDF path (default) is unchanged. Document that UnlimitedOCR page-level OCR is new and untested against the live model. |
| Dedup key normalisation too aggressive (collapses genuinely different chunks) | The key includes `source` + `heading_path` + normalised text. Two chunks with the same source + heading but different content will differ in the normalised text. Two chunks with the same content but different headings are *not* collapsed (correct — they're in different sections). |
| Existing store has no `dedup_key` field on old doc entries | `query_dedup_keys` returns `[]` for entries without the field (Milvus dynamic field absent = not in output). Old entries are treated as "no key" → new chunks with the same content get a different key (sha256 of normalised text) → they're inserted as new, not skipped. This is acceptable: the first `--reindex` or `--prune-dupes` cleans up. Document this. |

---

## 6. Definition of done

- [ ] OCR backend honoured in production ingest path (`--pdfs`)
- [ ] Image-only pages: WARNING (not silent) when no OCR fallback; OCR'd when backend available
- [ ] Doc chunks have a stable dedup key; re-ingest is idempotent
- [ ] `add_docs` returns `(inserted, skipped)`; all callers updated
- [ ] `--prune-dupes` CLI flag works on an existing store
- [ ] New unit tests cover OCR wiring + dedup (hermetic, no GPU)
- [ ] Full suite green, smoke green, ruff + mypy clean
- [ ] Docs updated (markdown_docs + session record + CHANGELOG)
- [ ] BACKLOG.md status updated (not committed — ship-it with user)
