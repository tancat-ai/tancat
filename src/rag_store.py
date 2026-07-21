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
class KnowledgeEntry:
    """Internal entry ready for vector store upsert."""

    vector: list[float]
    text: str
    metadata: dict[str, str]


@dataclass(slots=True)
class SearchHit:
    """A single search result from the vector store."""

    distance: float
    metadata: dict[str, str]

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
    source: str = ""  # "golden" or "doc"
    page: str = ""  # URL fragment for golden patterns


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

    def clear(self) -> None:
        """Delete all entries (for testing / rebuild).

        Closes the underlying Milvus client and attempts to delete
        the database file.  On Windows, milvus-lite may not release
        the file lock immediately — the file is left for the caller
        or OS to clean up.
        """
        if self._client is not None:
            self._client.close()
            self._client = None
        import os

        try:
            os.remove(self._db_path)
        except FileNotFoundError, PermissionError:
            pass  # Windows: milvus-lite may not release the lock


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
                )
            )

        # Stable sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    @property
    def is_empty(self) -> bool:
        return self._backend.count() == 0
