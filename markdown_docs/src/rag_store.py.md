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
def add_docs(self, chunks: list[DocChunk]) -> int: ...
def retrieve(self, query: str, *, action_type: str = "", k: int = 5, min_confidence: float = 0.6) -> list[RetrievedPattern]: ...
```

**`retrieve()`:** Embeds the query, searches the backend, filters by `min_confidence`, and returns `RetrievedPattern` objects sorted by confidence descending. Returns empty list when the store is empty.

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
