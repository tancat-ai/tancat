"""RAG (Retrieval-Augmented Generation) vector store for placeholder resolution.

Provides a retrieval layer that indexes verified locator patterns and Playwright
documentation chunks. At resolution time, the placeholder description is embedded
and used to retrieve similar patterns — feeding a scoring bonus to
``PlaceholderScorer`` and augmenting the LLM disambiguation prompt.

Architecture::

    RAGStore
      ├─ EmbeddingProvider (sentence-transformers)
      └─ VectorStoreBackend (Milvus Lite)

All retrieval is advisory: an empty or missing store behaves as if disabled.

Usage::

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
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GoldenPattern:
    """A verified placeholder → selector mapping from the eval dataset."""

    action: str  # CLICK, FILL, ASSERT, GOTO, SELECT
    description: str  # e.g. "Add to cart button"
    expected_locator: str  # e.g. "button.add-to-cart"
    tolerance_selectors: list[str] = field(default_factory=list)
    expected_page: str = ""

    @property
    def query_text(self) -> str:
        """Text used for embedding: action + description."""
        return f"{self.action}: {self.description}"


@dataclass(slots=True)
class DocChunk:
    """A chunk of Playwright documentation (or other domain text)."""

    text: str
    source: str = ""  # e.g. "playwright-locators.md"
    heading_path: str = ""  # e.g. "Locators > Best Practices"


@dataclass(slots=True)
class LearnedPattern:
    """A verified placeholder → selector mapping learned from execution.

    Written back by :func:`src.rag_learn.learn_from_evidence` when a
    generated test step passes against the live site (B-036 Phase 3).
    ``site_hash`` is a one-way sha256 of the site identity (``host[:port]``,
    B-047) — no URLs or PII are ever stored (AI-035 privacy design).
    """

    action_type: str  # CLICK, FILL, ASSERT, GOTO, SELECT
    description: str  # evidence step label / placeholder description
    locator: str  # verified locator from the passing step
    site_hash: str  # sha256(host[:port]), one-way
    confidence: float = 0.9  # verified by execution, below self-healing's 1.0
    source: str = "evidence"  # "evidence" (B-036) | "self_healing" (AI-035)

    @property
    def query_text(self) -> str:
        """Text used for embedding: action + description (matches GoldenPattern)."""
        return f"{self.action_type}: {self.description}"


@dataclass(slots=True)
class KnowledgeEntry:
    """Internal entry ready for vector store upsert."""

    vector: list[float]
    text: str
    metadata: dict[str, Any]  # Milvus dynamic fields: str/int/float values


@dataclass(slots=True)
class SearchHit:
    """A single search result from the vector store."""

    distance: float
    metadata: dict[str, Any]

    @property
    def confidence(self) -> float:
        """Confidence score (0.0–1.0, higher = more similar).

        For COSINE metric (used by both Milvus and InMemoryBackend),
        ``distance`` is the cosine similarity value.  We clamp it
        to [0, 1] so it can be used as a confidence threshold.
        """
        return max(0.0, min(1.0, self.distance))


@dataclass(slots=True)
class RetrievedPattern:
    """A retrieval result returned to the resolver."""

    description: str
    selector: str
    action_type: str
    confidence: float
    source: str = ""  # "golden", "doc", or "learned"
    page: str = ""  # URL fragment for golden patterns
    site_hash: str = ""  # one-way site identity hash (learned patterns)


# ---------------------------------------------------------------------------
# Embedding Provider Protocol
# ---------------------------------------------------------------------------


class EmbeddingProvider(Protocol):
    """Protocol for text → vector embedding."""

    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


# ---------------------------------------------------------------------------
# Sentence-Transformers embedder
# ---------------------------------------------------------------------------


class SentenceTransformerEmbedder:
    """Embedding provider backed by ``sentence-transformers``.

    Default model: ``all-MiniLM-L6-v2`` (384-dim, ~80 MB, CPU-only).
    The model is downloaded on first use and cached by Hugging Face.
    """

    _DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or self._DEFAULT_MODEL
        self._model: Any | None = None

    @property
    def dimension(self) -> int:
        return 384  # all-MiniLM-L6-v2

    @property
    def _loaded_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        return self._loaded_model.encode(text, normalize_embeddings=True).tolist()  # type: ignore[no-any-return]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = self._loaded_model.encode(texts, normalize_embeddings=True)
        return [vec.tolist() for vec in result]


# ---------------------------------------------------------------------------
# Vector Store Backend Protocol
# ---------------------------------------------------------------------------


class VectorStoreBackend(Protocol):
    """Protocol for vector store backends.

    A backend stores vector entries and supports similarity search.
    ``MilvusLiteBackend`` is the v1 implementation. The protocol makes
    swapping to ChromaDB / hosted Milvus a one-file change in Phase 6.
    """

    @property
    def dimension(self) -> int: ...

    def upsert(self, entries: list[KnowledgeEntry]) -> int: ...
    def search(self, query_vector: list[float], k: int) -> list[SearchHit]: ...
    def count(self) -> int: ...
    def clear(self) -> None: ...

    def counts_by_type(self) -> dict[str, int]:
        """Count stored entries grouped by ``entry_type`` (golden/doc/learned)."""
        ...

    def delete_learned(self) -> int:
        """Delete entries that are neither golden nor doc (learned patterns).

        Returns the number of entries removed.
        """
        ...

    def find_learned(
        self,
        action_type: str,
        description: str,
        site_hash: str,
    ) -> dict[str, Any] | None:
        """Find an existing learned-pattern row by dedup key.

        Returns the full row (incl. primary key, vector, and metadata) or
        ``None`` when no row matches ``(action_type, description, site_hash)``.
        """
        ...

    def increment_learned_hit(self, row: dict[str, Any]) -> int:
        """Increment ``hit_count`` on an existing learned row; returns the new count."""
        ...


# ---------------------------------------------------------------------------
# Milvus Lite backend
# ---------------------------------------------------------------------------

_COLLECTION_NAME = "rag_entries"


class MilvusLiteBackend:
    """Vector store backend backed by Milvus Lite (embedded).

    Stores the database at *db_path* (a ``.db`` file).
    Single-writer — safe for dev/CLI/single-process Streamlit.
    For multi-worker SaaS (Phase 6), swap to ``ChromaDBBackend``.
    """

    def __init__(self, db_path: str, dimension: int) -> None:
        self._db_path = str(db_path)
        self._dimension = dimension
        self._client: Any | None = None

    @property
    def dimension(self) -> int:
        return self._dimension

    # -- client lazy init ----------------------------------------------------

    @property
    def _c(self) -> Any:
        if self._client is None:
            from pymilvus import DataType, MilvusClient

            client = MilvusClient(self._db_path)

            # Create collection if it doesn't exist
            if not client.has_collection(_COLLECTION_NAME):
                schema = client.create_schema(
                    auto_id=True,
                    enable_dynamic_field=True,
                )
                schema.add_field("id", DataType.INT64, is_primary=True)
                schema.add_field(
                    "vector",
                    DataType.FLOAT_VECTOR,
                    dim=self._dimension,
                )
                client.create_collection(
                    _COLLECTION_NAME,
                    schema=schema,
                )

                # Create index for search
                index_params = client.prepare_index_params()
                index_params.add_index(
                    field_name="vector",
                    index_type="IVF_FLAT",
                    metric_type="COSINE",
                    params={"nlist": 128},
                )
                client.create_index(
                    _COLLECTION_NAME,
                    index_params,
                )

            client.load_collection(_COLLECTION_NAME)
            self._client = client
        return self._client

    # -- operations ----------------------------------------------------------

    def upsert(self, entries: list[KnowledgeEntry]) -> int:
        """Insert or update entries. Returns number inserted."""
        if not entries:
            return 0
        data = [
            {
                "vector": e.vector,
                "text": e.text,
                **e.metadata,
            }
            for e in entries
        ]
        result = self._c.insert(_COLLECTION_NAME, data)
        # Note: explicit flush() is omitted — it triggers a known
        # milvus-lite race condition on Windows (manifest.json.tmp
        # already exists).  Search triggers auto-flush.
        return result["insert_count"]

    def search(self, query_vector: list[float], k: int) -> list[SearchHit]:
        """Search for the k nearest neighbours."""
        results = self._c.search(
            _COLLECTION_NAME,
            [query_vector],
            limit=k,
            output_fields=["text", "action_type", "selector", "entry_type", "page"],
        )
        if not results or not results[0]:
            return []
        return [
            SearchHit(
                distance=hit["distance"],
                metadata=hit.get("entity", {}),
            )
            for hit in results[0]
        ]

    def count(self) -> int:
        """Total number of entries in the collection."""
        stats = self._c.get_collection_stats(_COLLECTION_NAME)
        return stats["row_count"]

    def counts_by_type(self) -> dict[str, int]:
        """Count stored entries grouped by ``entry_type`` metadata.

        B-036 Phase 2: used by ``rag_ingest --stats`` and the bundled-pack
        diagnostics. Entries without an ``entry_type`` are bucketed as
        ``unknown``.
        """
        from collections import Counter

        rows = self._c.query(
            _COLLECTION_NAME,
            filter="",
            output_fields=["entry_type"],
            limit=100_000,
        )
        counter: Counter[str] = Counter(str(row.get("entry_type", "unknown")) for row in rows)
        return dict(counter)

    def delete_learned(self) -> int:
        """Delete non-golden/doc entries (learned patterns).

        Keeps the bundled golden pack and doc chunks intact so a re-seed
        never duplicates them. Returns the number of entries removed.
        """
        rows = self._c.query(
            _COLLECTION_NAME,
            filter="",
            output_fields=["id", "entry_type"],
            limit=100_000,
        )
        ids = [row["id"] for row in rows if str(row.get("entry_type", "")) not in ("golden", "doc")]
        if not ids:
            return 0
        result = self._c.delete(_COLLECTION_NAME, ids=ids)
        if isinstance(result, dict):
            return int(result.get("delete_count", len(ids)))
        # Backward-compat: older Milvus returns the deleted primary keys.
        return len(result)

    def find_learned(
        self,
        action_type: str,
        description: str,
        site_hash: str,
    ) -> dict[str, Any] | None:
        """Find an existing learned-pattern row by dedup key (Milvus impl).

        Multi-field AND filter over dynamic fields (verified against
        Milvus-lite 2026-08-03). Returns the full row so the caller can
        upsert it back with an incremented ``hit_count``.
        """
        rows = self._c.query(
            _COLLECTION_NAME,
            filter=(
                "entry_type == 'learned' "
                f"and action_type == '{action_type}' "
                f"and description == '{description}' "
                f"and site_hash == '{site_hash}'"
            ),
            output_fields=["*"],
            limit=1,
        )
        return rows[0] if rows else None

    def increment_learned_hit(self, row: dict[str, Any]) -> int:
        """Increment ``hit_count`` on an existing learned row (Milvus impl).

        Milvus upsert replaces the whole entity, so the full row from
        ``find_learned`` (which includes the vector) is written back with
        ``hit_count + 1``. Returns the new count.
        """
        current = int(row.get("hit_count", 0))
        new_hit = current + 1
        data = {**row, "hit_count": new_hit}
        self._c.upsert(_COLLECTION_NAME, [data])
        return new_hit

    def clear(self) -> None:
        """Delete all entries (for testing / rebuild).

        Closes the underlying Milvus client and attempts to delete
        the database.  Milvus Lite stores the database as a directory
        (multiple files), so we use ``shutil.rmtree``.  On Windows,
        milvus-lite may not release its file locks immediately — the
        directory is left for the caller or OS to clean up.
        """
        if self._client is not None:
            self._client.close()
            self._client = None
        import shutil

        try:
            shutil.rmtree(self._db_path)
        except FileNotFoundError, PermissionError, OSError:
            pass  # milvus-lite may hold file locks


# ---------------------------------------------------------------------------
# RAGStore — high-level API
# ---------------------------------------------------------------------------


class RAGStore:
    """High-level retrieval store: embeds text and delegates to a vector backend.

    Two knowledge sources:
    - ``GoldenPattern`` — verified placeholder → selector mappings
    - ``DocChunk`` — domain documentation chunks
    """

    def __init__(
        self,
        backend: VectorStoreBackend,
        embedder: EmbeddingProvider,
    ) -> None:
        self._backend = backend
        self._embedder = embedder

    # -- ingestion -----------------------------------------------------------

    def add_patterns(self, patterns: list[GoldenPattern]) -> int:
        """Embed and store golden locator patterns. Returns count inserted."""
        if not patterns:
            return 0
        texts = [p.query_text for p in patterns]
        vectors = self._embedder.embed_batch(texts)
        entries = [
            KnowledgeEntry(
                vector=vec,
                text=p.query_text,
                metadata={
                    "action_type": p.action,
                    "selector": p.expected_locator,
                    "entry_type": "golden",
                    "page": p.expected_page,
                },
            )
            for vec, p in zip(vectors, patterns, strict=True)
        ]
        return self._backend.upsert(entries)

    def add_docs(self, chunks: list[DocChunk]) -> int:
        """Embed and store documentation chunks. Returns count inserted."""
        if not chunks:
            return 0
        texts = [c.text for c in chunks]
        vectors = self._embedder.embed_batch(texts)
        entries = [
            KnowledgeEntry(
                vector=vec,
                text=c.text,
                metadata={
                    "action_type": "",
                    "selector": "",
                    "entry_type": "doc",
                    "page": "",
                    "source": c.source,
                    "heading_path": c.heading_path,
                },
            )
            for vec, c in zip(vectors, chunks, strict=True)
        ]
        return self._backend.upsert(entries)

    # -- retrieval -----------------------------------------------------------

    def retrieve(
        self,
        query: str,
        *,
        action_type: str = "",
        k: int = 5,
        min_confidence: float = 0.6,
    ) -> list[RetrievedPattern]:
        """Retrieve the top-k patterns/docs for a query.

        Returns results with confidence ≥ *min_confidence*, sorted
        descending by confidence.
        """
        if self._backend.count() == 0:
            return []

        query_vector = self._embedder.embed(query)
        hits = self._backend.search(query_vector, k=k)

        results: list[RetrievedPattern] = []
        for hit in hits:
            if hit.confidence < min_confidence:
                continue
            md = hit.metadata
            results.append(
                RetrievedPattern(
                    description=md.get("text", query),
                    selector=md.get("selector", ""),
                    action_type=md.get("action_type", action_type),
                    confidence=hit.confidence,
                    source=md.get("entry_type", ""),
                    page=md.get("page", ""),
                    site_hash=md.get("site_hash", ""),
                )
            )

        # Stable sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    @property
    def is_empty(self) -> bool:
        return self._backend.count() == 0

    def counts_by_type(self) -> dict[str, int]:
        """Count stored entries grouped by ``entry_type`` (golden/doc/learned)."""
        return self._backend.counts_by_type()

    def delete_learned(self) -> int:
        """Delete non-golden/doc entries (learned patterns).

        Keeps golden patterns and doc chunks so re-seeding stays
        dedup-free. Returns the number of entries removed.
        """
        return self._backend.delete_learned()

    def upsert_pattern(self, pattern: LearnedPattern) -> tuple[str, int]:
        """Insert or dedup a learned pattern (AI-035 core, B-036 Phase 3).

        Dedup key: ``(action_type, description, site_hash)``. When a row
        with the same key already exists, its ``hit_count`` is incremented
        (no new row — the store stays bounded) and ``("exists", hit_count)``
        is returned. Otherwise the pattern is embedded and inserted with
        ``hit_count=1`` and ``("inserted", 1)`` is returned.
        """
        existing = self._backend.find_learned(
            pattern.action_type,
            pattern.description,
            pattern.site_hash,
        )
        if existing is not None:
            hit = self._backend.increment_learned_hit(existing)
            return ("exists", hit)

        vector = self._embedder.embed(pattern.query_text)
        self._backend.upsert(
            [
                KnowledgeEntry(
                    vector=vector,
                    text=pattern.query_text,
                    metadata={
                        "entry_type": "learned",
                        "action_type": pattern.action_type,
                        "description": pattern.description,
                        "selector": pattern.locator,
                        "site_hash": pattern.site_hash,
                        "confidence": float(pattern.confidence),
                        "source": pattern.source,
                        "hit_count": 1,
                        "created_at": time.time(),
                    },
                )
            ]
        )
        return ("inserted", 1)
