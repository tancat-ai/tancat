# `src/rag_store.py`

## High-Level Purpose

RAG (Retrieval-Augmented Generation) vector store for placeholder resolution. Indexes verified locator patterns (golden patterns from the eval dataset) and Playwright documentation chunks. At resolution time, the placeholder description is embedded and used to retrieve similar patterns — feeding a scoring bonus to `PlaceholderScorer` and augmenting the LLM disambiguation prompt.

All retrieval is **advisory**: an empty or missing store behaves as if disabled — the pipeline works identically to pre-RAG.

## Module Metadata

- **Lines:** ~340
- **Imports:** `dataclasses`, `typing.Protocol`, `sentence_transformers`, `pymilvus`
- **Spec:** `docs/specs/FEATURE_SPEC_phase3_rag.md`
- **Shipped:** 2026-07-21

## Architecture

```
RAGStore
  ├─ EmbeddingProvider (SentenceTransformerEmbedder)
  └─ VectorStoreBackend (MilvusLiteBackend)
```

## Dataclasses

### `GoldenPattern`
A verified placeholder → selector mapping from the eval dataset.

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | CLICK, FILL, ASSERT, GOTO, SELECT |
| `description` | `str` | e.g. "Add to cart button" |
| `expected_locator` | `str` | e.g. "button.add-to-cart" |
| `tolerance_selectors` | `list[str]` | Acceptable alternative selectors |
| `expected_page` | `str` | URL fragment the pattern was verified on |
| `query_text` | `property → str` | `"{action}: {description}"` — used for embedding |

### `DocChunk`
A chunk of Playwright documentation (or other domain text).

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | Chunk content |
| `source` | `str` | Source filename, e.g. "playwright-locators.md" |
| `heading_path` | `str` | Heading hierarchy, e.g. "Locators > Best Practices" |
| `dedup_key` | `str` | Stable sha256 content hash (see `src.pdf_ingest.doc_chunk_key`); `""` = not computed → always inserted |

### `KnowledgeEntry`
Internal entry ready for vector store upsert. Contains `vector`, `text`, `metadata`.

### `SearchHit`
A single search result from the vector store.

| Field/Property | Type | Description |
|----------------|------|-------------|
| `distance` | `float` | Cosine similarity value |
| `metadata` | `dict[str, str]` | Stored entity metadata |
| `confidence` | `property → float` | `distance` clamped to [0.0, 1.0] |

### `RetrievedPattern`
A retrieval result returned to the resolver/retriever.

| Field | Type | Description |
|-------|------|-------------|
| `description` | `str` | Original query or matched text |
| `selector` | `str` | Matched locator (golden patterns) or empty (docs) |
| `action_type` | `str` | Action type from metadata |
| `confidence` | `float` | Similarity score (0.0–1.0) |
| `source` | `str` | `"golden"` or `"doc"` |
| `page` | `str` | URL fragment for golden patterns |

## Protocols

### `EmbeddingProvider`
Protocol for text → vector embedding.
- `dimension: int` — vector dimension (384 for all-MiniLM-L6-v2)
- `embed(text: str) -> list[float]` — single text embedding
- `embed_batch(texts: list[str]) -> list[list[float]]` — batch embedding

### `VectorStoreBackend`
Protocol for vector store backends. MilvusLiteBackend is the v1 implementation. The protocol makes swapping to ChromaDB / hosted Milvus a one-file change in Phase 6 (SaaS).

- `dimension: int` — vector dimension
- `upsert(entries: list[KnowledgeEntry]) -> int` — insert entries, returns count
- `search(query_vector: list[float], k: int) -> list[SearchHit]` — top-k similarity search
- `count() -> int` — total entries
- `clear() -> None` — delete all entries (test/rebuild)

## Classes

### `SentenceTransformerEmbedder`
Embedding provider backed by `sentence-transformers` with `all-MiniLM-L6-v2` (384-dim, ~80 MB, CPU-only). Model is downloaded on first use and cached by Hugging Face.

```python
def __init__(self, model_name: str | None = None) -> None: ...
def embed(self, text: str) -> list[float]: ...
def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

### `MilvusLiteBackend`
Vector store backend backed by Milvus Lite (embedded, in-process). Stores data at `db_path` (a `.db` file). Single-writer — safe for dev/CLI/single-process Streamlit. For multi-worker SaaS (Phase 6), swap to ChromaDB server or hosted Milvus.

```python
def __init__(self, db_path: str, dimension: int) -> None: ...
def upsert(self, entries: list[KnowledgeEntry]) -> int: ...
def search(self, query_vector: list[float], k: int) -> list[SearchHit]: ...
def count(self) -> int: ...
def clear(self) -> None: ...
```

**Lazy init:** Client and collection are created on first access. Collection uses `IVF_FLAT` index with `COSINE` metric and `nlist=128`. Auto-ID primary key on `INT64`. Dynamic fields enabled for flexible metadata.

**Note:** Explicit `flush()` after insert is deliberately omitted — it triggers a known milvus-lite race condition on Windows (`manifest.json.tmp` already exists). Search triggers auto-flush instead.

### `RAGStore`
High-level retrieval store: embeds text and delegates to a vector backend.

```python
def __init__(self, backend: VectorStoreBackend, embedder: EmbeddingProvider) -> None: ...
def add_patterns(self, patterns: list[GoldenPattern]) -> int: ...
def add_docs(self, chunks: list[DocChunk]) -> tuple[int, int]: ...
def retrieve(
    self, query: str, *, action_type: str = "", k: int = 5, min_confidence: float = 0.6
) -> list[RetrievedPattern]: ...
```

**`retrieve()`:** Embeds the query, searches the backend, filters by `min_confidence`, and returns `RetrievedPattern` objects sorted by confidence descending. Returns empty list when the store is empty.

**`add_docs()`:** Returns `(inserted, skipped)`. Before embedding, it queries the backend for existing `dedup_key` values (`query_dedup_keys("doc")`) and skips any chunk whose non-empty key already exists — re-ingestion is idempotent. Chunks with an empty `dedup_key` are always inserted (back-compat). The key is stored as a dynamic `dedup_key` field on each row.

## Key Design Decisions

- **Milvus Lite for v1:** Embedded, in-process, no server needed. Protocol abstraction guarantees swap path to ChromaDB/hosted Milvus for Phase 6 SaaS.
- **sentence-transformers for embeddings:** `all-MiniLM-L6-v2` (384-dim, ~80MB, CPU-only) — no GPU contention with LM Studio (see AGENTS.md §12 VRAM note).
- **COSINE metric:** Used by both Milvus and in-memory test backend for consistency.
- **Advisory retrieval:** Store absence/emptiness is not an error — pipeline degrades gracefully to pre-RAG behaviour.
- **Two knowledge sources:** Golden patterns (verified locators) and doc chunks (domain guidance) — stored with `entry_type` metadata for downstream filtering.

## Dependencies

- `pymilvus` — Milvus Lite client
- `sentence_transformers` — embedding model
- `src.storage.get_storage()` — workspace-aware `rag_path()`

## Depended On By

- `src/rag_retriever.py` — bridge to resolution pipeline
- `scripts/rag_ingest.py` — ingestion CLI (build/rebuild store)
- `tests/test_rag_store.py` — 35 unit tests

## Usage

```python
from src.rag_store import RAGStore, MilvusLiteBackend, SentenceTransformerEmbedder
from src.storage import get_storage

embedder = SentenceTransformerEmbedder()
backend = MilvusLiteBackend(get_storage().rag_path(), embedder.dimension)
store = RAGStore(backend, embedder)

# Ingestion
store.add_patterns([GoldenPattern(...), ...])
store.add_docs([DocChunk(...), ...])

# Retrieval
results = store.retrieve("Add to cart button", action_type="CLICK", k=5)
```

---

## AI-035 / B-036 Update (2026-08-03)

### New dataclass: `LearnedPattern`
A verified placeholder → selector mapping learned from execution
(`source="evidence"`, `confidence=0.9`).

| Field | Type | Description |
|-------|------|-------------|
| `action_type` | `str` | CLICK, FILL, ASSERT, GOTO, SELECT |
| `description` | `str` | evidence step label / placeholder description |
| `locator` | `str` | verified locator from the passing step |
| `site_hash` | `str` | one-way sha256(domain) — no URLs/PII stored |
| `confidence` | `float` | `0.9` (evidence-verified) |
| `source` | `str` | `"evidence"` \| `"self_healing"` (future) |
| `query_text` | `property → str` | `"{action_type}: {description}"` — matches golden embedding |

### New method: `RAGStore.upsert_pattern(pattern: LearnedPattern) -> tuple[str, int]`
Dedup on `(action_type, description, site_hash)`. Existing row → increments
`hit_count` (no new row), returns `("exists", hit_count)`. New row → embeds +
inserts with `hit_count=1`, returns `("inserted", 1)`. The store stays bounded
(one row per fact). Backend support: `find_learned()` (multi-field AND filter
over Milvus dynamic fields — spike-verified) + `increment_learned_hit()`
(full-row upsert by pk to preserve the vector).

### New backend methods (Protocol + Milvus + test backends)
- `counts_by_type() -> dict[str, int]` — per-`entry_type` counts (`--stats`)
- `delete_learned() -> int` — delete non-golden/doc rows, keep the pack
  (`--prune-learned`); handles both pymilvus delete return shapes
- `find_learned(...)` / `increment_learned_hit(...)` — learned-pattern dedup machinery
- `query_dedup_keys(entry_type: str) -> list[str]` — doc-chunk dedup keys (AI-045 #4); protocol default returns `[]`, Milvus impl queries the `dedup_key` field

### `RetrievedPattern.site_hash`
New field (`str = ""`) — learned patterns carry their site hash through to the
scorer so same-site bonuses are scoped correctly. Golden patterns keep `""`.

### Type correction
`KnowledgeEntry.metadata` / `SearchHit.metadata` changed from `dict[str, str]`
to `dict[str, Any]` — Milvus dynamic fields carry ints/floats (confidence,
hit_count, created_at).

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `EmbeddingMismatchError` (class): The RAG store was created with a different embedding model than configured. Raised at store-open time when the stored embedder stamp (model + dim) does not match the configured embedder - refusing retrieval instead of...
- `SentenceTransformerEmbedder.identity` (method of `SentenceTransformerEmbedder`): `SentenceTransformerEmbedder.identity() -> str` - Stable embedder identity for store stamping: '<model>@<dim>'. Changing either the model or the dimension changes the identity, so a store created with a different identity is refused (Phase 6 6b).
- `VectorStoreBackend.find_negative` (method of `VectorStoreBackend`): `VectorStoreBackend.find_negative(action_type: str, description: str, site_hash: str) -> dict[str, Any] | None` - Find an existing learned_negative row by dedup key (AI-058). Mirrors find_learned for the contrastive negative store.
- `embedder_stamp_path` (function): `embedder_stamp_path(db_path: str) -> str` - Path of the embedder-stamp sidecar for a Milvus db path. Milvus Lite stores its db as a *directory*; the stamp lives as a sibling file so shutil.rmtree of the db dir never silently carries a stale stamp into a reb...
- `MilvusLiteBackend.verify_embedder` (method of `MilvusLiteBackend`): `MilvusLiteBackend.verify_embedder(embedder_identity: str | None) -> None` - Cross-check the stored stamp against *embedder_identity*. Called by :class:'RAGStore' before every operation with the actual embedder's identity, so a store opened with a different declared identity cannot smuggle mis...
- `MilvusLiteBackend.find_negative` (method of `MilvusLiteBackend`): `MilvusLiteBackend.find_negative(action_type: str, description: str, site_hash: str) -> dict[str, Any] | None` - Find an existing learned_negative row by dedup key (Milvus impl). AI-058: mirrors find_learned but filters entry_type == 'learned_negative'. Returns the full row so the caller can upsert it back with an in...
- `RAGStore.is_empty` (method of `RAGStore`): `RAGStore.is_empty() -> bool`
- `RAGStore.upsert_pattern` (method of `RAGStore`): `RAGStore.upsert_pattern(pattern: LearnedPattern) -> tuple[str, int]` - Insert or dedup a learned pattern (AI-035 core, B-036 Phase 3). Dedup key: (action_type, description, site_hash). When a row with the same key already exists, its hit_count is incremented (no new row - the sto...
- `RAGStore.upsert_negative_pattern` (method of `RAGStore`): `RAGStore.upsert_negative_pattern(pattern: LearnedPattern) -> tuple[str, int]` - Insert or dedup a learned-NEGATIVE pattern (AI-058 contrastive store). Mirrors :meth:'upsert_pattern' with entry_type="learned_negative"' - dedup on (action_type, description, site_hash); a repeat bumps hit_co...
- `DEFAULT_EMBEDDER_IDENTITY` (constant): `DEFAULT_EMBEDDER_IDENTITY = f'{SentenceTransformerEmbedder._DEFAULT_MODEL}@384'`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (6 items). Grouped under the public function that calls them.

### `MilvusLiteBackend.verify_embedder(embedder_identity: str | None) -> None` - method of `MilvusLiteBackend`

- `_verify_stamp(embedder_identity: str | None) -> None` (method of `MilvusLiteBackend`): Compare the stored stamp against *embedder_identity*; refuse on mismatch. Refusal policy: * dimension mismatch -> always refuse (inserts would fail confusingly); * embedder identity mismatch -> refuse (cosine similarity...

### `RAGStore.add_patterns(patterns: list[GoldenPattern]) -> int` - method of `RAGStore`

- `_ensure_embedder_match() -> None` (method of `RAGStore`): Refuse operations when the store's stamp doesn't match this embedder. Phase 6 6b: the backend verifies its constructor-declared identity at open; this cross-check uses the *actual* embedder's identity so a store opene...

### Internal utilities

- `_loaded_model() -> Any` (method of `SentenceTransformerEmbedder`): Loaded model; calls `SentenceTransformer`; returns Any.
- `_read_stamp() -> dict[str, Any] | None` (method of `MilvusLiteBackend`): Read stamp; calls `_stamp_path`, `load`; returns dict[str, Any] | None.
- `_write_stamp(embedder_identity: str | None) -> None` (method of `MilvusLiteBackend`): Write stamp; calls `_stamp_path`, `dump`, `time`; returns None.
- `_c() -> Any` (method of `MilvusLiteBackend`): C; calls `MilvusClient`, `_verify_stamp`, `_write_stamp`, `add_field`, `add_index`, `create_collection`; returns Any.
