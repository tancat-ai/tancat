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

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class EmbeddingMismatchError(RuntimeError):
    """The RAG store was created with a different embedding model than configured.

    Raised at store-open time when the stored embedder stamp (model + dim)
    does not match the configured embedder — refusing retrieval instead of
    silently returning garbage (Phase 6 6b — BACKLOG AI-045 #2). The message
    carries the fix: ``python scripts/rag_ingest.py --reindex``.
    """


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
    #: One-way sha256 of the dataset site's canonical ``host[:port]`` (B-047
    #: residual). Empty = legacy site-agnostic golden (still applies anywhere).
    site_hash: str = ""

    @property
    def query_text(self) -> str:
        """Text used for embedding: action + description."""
        return f"{self.action}: {self.description}"


@dataclass(slots=True)
class DocChunk:
    """A chunk of Playwright documentation (or other domain text).

    ``dedup_key`` is a stable content hash (see :func:`src.pdf_ingest.doc_chunk_key`)
    used by :meth:`RAGStore.add_docs` to make re-ingestion idempotent — a chunk
    whose key already exists in the store is skipped rather than duplicated.
    Empty ("" = not computed) means "always insert" for back-compat with
    callers that build chunks without the key.
    """

    text: str
    source: str = ""  # e.g. "playwright-locators.md"
    heading_path: str = ""  # e.g. "Locators > Best Practices"
    dedup_key: str = ""  # sha256(source \x00 heading_path \x00 normalised text)
    # ── 16b provenance (Phase 1 — stop discarding provenance) ─────
    #: Physical PDF page index (1-indexed). 0 = not a PDF / unknown.
    page: int = 0
    #: Printed page label (e.g. "5"). "" if the page has no label.
    page_label: str = ""
    #: Parse route: "text" (PyMuPDF extraction) | "ocr" (OCR fallback).
    route: str = "text"


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
    source: str = ""  # "golden", "doc", "learned", or "learned_negative"
    page: str = ""  # URL fragment for golden patterns
    site_hash: str = ""  # one-way site identity hash (learned patterns)
    hit_count: int = 0  # evidence count (learned / learned_negative)
    last_seen: float = 0.0  # wall-clock time of last record (recency tie-break)
    # ── 16b provenance (Phase 1 — carry doc identity through retrieval) ─
    #: Document source (filename) for doc chunks.
    doc_source: str = ""
    #: Physical PDF page index (1-indexed). 0 = not a PDF / unknown.
    doc_page: int = 0
    #: Printed page label.
    doc_page_label: str = ""
    #: Parse route: "text" | "ocr".
    doc_route: str = "text"


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
    def model_name(self) -> str:
        """The configured sentence-transformer model name."""
        return self._model_name

    @property
    def identity(self) -> str:
        """Stable embedder identity for store stamping: ``'<model>@<dim>'``.

        Changing either the model or the dimension changes the identity, so a
        store created with a different identity is refused (Phase 6 6b).
        """
        return f"{self._model_name}@{self.dimension}"

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


# The only embedder that could have built a pre-stamp (legacy) store — no
# model configuration existed before embedder-identity tracking (Phase 6 6b).
DEFAULT_EMBEDDER_IDENTITY: str = f"{SentenceTransformerEmbedder._DEFAULT_MODEL}@384"


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

    def query_dedup_keys(self, entry_type: str) -> list[str]:
        """Return the non-empty ``dedup_key`` values stored for *entry_type*.

        Used by :meth:`RAGStore.add_docs` to make re-ingestion idempotent.
        Backends without support return an empty list (dedup disabled).
        """
        return []  # pragma: no cover - protocol default

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

    def find_negative(
        self,
        action_type: str,
        description: str,
        site_hash: str,
    ) -> dict[str, Any] | None:
        """Find an existing ``learned_negative`` row by dedup key (AI-058).

        Mirrors ``find_learned`` for the contrastive negative store.
        """
        ...


# ---------------------------------------------------------------------------
# Milvus Lite backend
# ---------------------------------------------------------------------------

_COLLECTION_NAME = "rag_entries"


#: Suffix of the embedder-stamp sidecar written next to the Milvus db dir.
_EMBEDDER_STAMP_SUFFIX = ".embedder.json"


def embedder_stamp_path(db_path: str) -> str:
    """Path of the embedder-stamp sidecar for a Milvus db path.

    Milvus Lite stores its db as a *directory*; the stamp lives as a sibling
    file so ``shutil.rmtree`` of the db dir never silently carries a stale
    stamp into a rebuilt store.
    """
    return str(db_path) + _EMBEDDER_STAMP_SUFFIX


class MilvusLiteBackend:
    """Vector store backend backed by Milvus Lite (embedded).

    Stores the database at *db_path* (a ``.db`` file).
    Single-writer — safe for dev/CLI/single-process Streamlit.
    For multi-worker SaaS (Phase 6), swap to ``ChromaDBBackend``.

    Embedder stamping (Phase 6 6b): on first creation the backend writes a
    sidecar stamp (``<db_path>.embedder.json``) recording the embedder
    identity + dimension. Opening an existing store verifies the stamp
    against the configured identity and raises :class:`EmbeddingMismatchError`
    on mismatch — never silently returning vectors from a different embedding
    space.
    """

    def __init__(
        self,
        db_path: str,
        dimension: int,
        *,
        embedder_identity: str | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._dimension = dimension
        self._embedder_identity = embedder_identity
        self._client: Any | None = None

    @property
    def dimension(self) -> int:
        return self._dimension

    # -- embedder stamp (Phase 6 6b) -----------------------------------------

    def _stamp_path(self) -> str:
        return embedder_stamp_path(self._db_path)

    def _read_stamp(self) -> dict[str, Any] | None:
        try:
            with open(self._stamp_path(), encoding="utf-8") as fh:
                data = json.load(fh)
        except OSError, ValueError:
            return None
        return data if isinstance(data, dict) else None

    def _write_stamp(self, embedder_identity: str | None) -> None:
        payload = {
            "embedder": embedder_identity,
            "dim": self._dimension,
            "created_at": time.time(),
        }
        with open(self._stamp_path(), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def _verify_stamp(self, embedder_identity: str | None) -> None:
        """Compare the stored stamp against *embedder_identity*; refuse on mismatch.

        Refusal policy:
        * dimension mismatch → always refuse (inserts would fail confusingly);
        * embedder identity mismatch → refuse (cosine similarity is meaningless
          across embedding spaces — the silent-corruption case);
        * legacy store (no sidecar) → accept only the default embedder (the only
          model that could have built it) and migrate the stamp forward;
          any other identity is refused because the store cannot be verified.
        """
        stored = self._read_stamp()
        if stored is None:
            if embedder_identity in (None, DEFAULT_EMBEDDER_IDENTITY):
                self._write_stamp(embedder_identity)
                return
            raise EmbeddingMismatchError(
                f"RAG store at {self._db_path} has no embedder stamp (created before "
                "embedder-identity tracking) and cannot be verified against embedder "
                f"'{embedder_identity}'. Re-embed with: "
                "`python scripts/rag_ingest.py --reindex`"
            )
        stored_dim = stored.get("dim")
        if stored_dim is not None and int(stored_dim) != self._dimension:
            raise EmbeddingMismatchError(
                f"RAG store at {self._db_path} was created with dimension "
                f"{stored_dim} but the configured embedder produces "
                f"{self._dimension}-dim vectors. Re-embed with: "
                "`python scripts/rag_ingest.py --reindex`"
            )
        stored_embedder = stored.get("embedder")
        if stored_embedder is not None and embedder_identity is not None and stored_embedder != embedder_identity:
            raise EmbeddingMismatchError(
                f"RAG store at {self._db_path} was created with embedder "
                f"'{stored_embedder}' but the configured embedder is "
                f"'{embedder_identity}'. Refusing retrieval to prevent silent "
                "corruption. Re-embed with: `python scripts/rag_ingest.py --reindex`"
            )

    def verify_embedder(self, embedder_identity: str | None) -> None:
        """Cross-check the stored stamp against *embedder_identity*.

        Called by :class:`RAGStore` before every operation with the actual
        embedder's identity, so a store opened with a different declared
        identity cannot smuggle mismatched vectors past the constructor-time
        check. The lazy client is opened first so a brand-new store gets
        created + stamped before the cross-check (otherwise a first-run
        store would look like an unverifiable legacy one). In-memory/fake
        backends may omit this method (callers use ``getattr``).
        """
        _ = self._c  # ensure the collection exists (created + stamped)
        self._verify_stamp(embedder_identity)

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
                # Embedder stamp: recorded at creation so a later model change
                # is detected instead of silently corrupting retrieval.
                self._write_stamp(self._embedder_identity)
            else:
                # Existing store: verify the embedder stamp before any use.
                self._verify_stamp(self._embedder_identity)

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
            # ``site_hash`` must be returned for the site-scoping gates
            # (B-047 residual): golden/learned patterns read it at scoring
            # time — without it every pattern looks site-agnostic.
            output_fields=["text", "action_type", "selector", "entry_type", "page", "site_hash"],
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

    def query_dedup_keys(self, entry_type: str) -> list[str]:
        """Return non-empty ``dedup_key`` values stored for *entry_type*.

        One batched query (not per-chunk).  Entries written before dedup-key
        tracking have no ``dedup_key`` field and are simply absent from the
        result — they are treated as "no key" by the caller, so a re-ingest of
        their content inserts a fresh keyed row (cleaned up by --reindex or
        --prune-dupes).
        """
        rows = self._c.query(
            _COLLECTION_NAME,
            filter=f"entry_type == '{entry_type}'",
            output_fields=["dedup_key"],
            limit=100_000,
        )
        return [str(row["dedup_key"]) for row in rows if row.get("dedup_key")]

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

    def find_negative(
        self,
        action_type: str,
        description: str,
        site_hash: str,
    ) -> dict[str, Any] | None:
        """Find an existing ``learned_negative`` row by dedup key (Milvus impl).

        AI-058: mirrors ``find_learned`` but filters ``entry_type ==
        'learned_negative'``. Returns the full row so the caller can upsert
        it back with an incremented ``hit_count`` / fresh ``last_seen``.
        """
        rows = self._c.query(
            _COLLECTION_NAME,
            filter=(
                "entry_type == 'learned_negative' "
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
        ``hit_count + 1`` and a fresh ``last_seen`` (AI-058 recency). Returns
        the new count.
        """
        current = int(row.get("hit_count", 0))
        new_hit = current + 1
        data = {**row, "hit_count": new_hit, "last_seen": time.time()}
        self._c.upsert(_COLLECTION_NAME, [data])
        return new_hit

    def clear(self) -> None:
        """Delete all entries (for testing / rebuild).

        Closes the underlying Milvus client and attempts to delete
        the database.  Milvus Lite stores the database as a directory
        (multiple files), so we use ``shutil.rmtree``.  On Windows,
        milvus-lite may not release its file locks immediately — the
        directory is left for the caller or OS to clean up.  The
        embedder-stamp sidecar is removed too so a rebuilt store never
        inherits a stale stamp.
        """
        if self._client is not None:
            self._client.close()
            self._client = None
        import os
        import shutil

        for target in (self._db_path, self._stamp_path()):
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                else:
                    os.remove(target)
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
        self._identity: str | None = getattr(embedder, "identity", None)

    def _ensure_embedder_match(self) -> None:
        """Refuse operations when the store's stamp doesn't match this embedder.

        Phase 6 6b: the backend verifies its constructor-declared identity at
        open; this cross-check uses the *actual* embedder's identity so a store
        opened with a different declared identity cannot smuggle mismatched
        vectors through. Backends without ``verify_embedder`` (in-memory
        fakes) skip the check.
        """
        verify = getattr(self._backend, "verify_embedder", None)
        if verify is not None:
            verify(self._identity)

    # -- ingestion -----------------------------------------------------------

    def add_patterns(self, patterns: list[GoldenPattern]) -> int:
        """Embed and store golden locator patterns. Returns count inserted."""
        if not patterns:
            return 0
        self._ensure_embedder_match()
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
                    # B-047 residual: site-scoped goldens only earn a bonus
                    # on their own site (empty = legacy agnostic).
                    "site_hash": p.site_hash,
                },
            )
            for vec, p in zip(vectors, patterns, strict=True)
        ]
        return self._backend.upsert(entries)

    def add_docs(self, chunks: list[DocChunk]) -> tuple[int, int]:
        """Embed and store documentation chunks, deduping by ``dedup_key``.

        Returns ``(inserted, skipped)`` where *skipped* counts chunks whose
        non-empty ``dedup_key`` already exists in the store (re-ingestion is
        idempotent).  Chunks with an empty ``dedup_key`` are always inserted
        (back-compat for callers that don't compute the key).
        """
        if not chunks:
            return (0, 0)
        self._ensure_embedder_match()

        existing_keys = set(self._backend.query_dedup_keys("doc"))
        new_chunks = [c for c in chunks if not c.dedup_key or c.dedup_key not in existing_keys]
        skipped = len(chunks) - len(new_chunks)
        if not new_chunks:
            return (0, skipped)

        texts = [c.text for c in new_chunks]
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
                    "dedup_key": c.dedup_key,
                    # 16b Phase 1 — carry provenance through the store
                    "doc_page": c.page,
                    "doc_page_label": c.page_label,
                    "doc_route": c.route,
                },
            )
            for vec, c in zip(vectors, new_chunks, strict=True)
        ]
        inserted = self._backend.upsert(entries)
        return (inserted, skipped)

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
        self._ensure_embedder_match()
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
                    hit_count=int(md.get("hit_count", 0) or 0),
                    last_seen=float(md.get("last_seen", 0.0) or 0.0),
                    # 16b Phase 1 — carry doc provenance through retrieval
                    doc_source=md.get("source", ""),
                    doc_page=int(md.get("doc_page", 0) or 0),
                    doc_page_label=md.get("doc_page_label", ""),
                    doc_route=md.get("doc_route", "text"),
                )
            )

        # Stable sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    @property
    def is_empty(self) -> bool:
        self._ensure_embedder_match()
        return self._backend.count() == 0

    def counts_by_type(self) -> dict[str, int]:
        """Count stored entries grouped by ``entry_type`` (golden/doc/learned)."""
        self._ensure_embedder_match()
        return self._backend.counts_by_type()

    def delete_learned(self) -> int:
        """Delete non-golden/doc entries (learned patterns).

        Keeps golden patterns and doc chunks so re-seeding stays
        dedup-free. Returns the number of entries removed.
        """
        self._ensure_embedder_match()
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

        self._ensure_embedder_match()
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

    def upsert_negative_pattern(self, pattern: LearnedPattern) -> tuple[str, int]:
        """Insert or dedup a learned-NEGATIVE pattern (AI-058 contrastive store).

        Mirrors :meth:`upsert_pattern` with ``entry_type="learned_negative"` —
        dedup on ``(action_type, description, site_hash)``; a repeat bumps
        ``hit_count`` and refreshes ``last_seen`` (recency tie-break). The
        single-row-per-key invariant mirrors the positive store, so a
        ``(description, selector, site)`` pair resolves to one net signal.
        """
        existing = self._backend.find_negative(
            pattern.action_type,
            pattern.description,
            pattern.site_hash,
        )
        if existing is not None:
            hit = self._backend.increment_learned_hit(existing)
            return ("exists", hit)

        self._ensure_embedder_match()
        vector = self._embedder.embed(pattern.query_text)
        now = time.time()
        self._backend.upsert(
            [
                KnowledgeEntry(
                    vector=vector,
                    text=pattern.query_text,
                    metadata={
                        "entry_type": "learned_negative",
                        "action_type": pattern.action_type,
                        "description": pattern.description,
                        "selector": pattern.locator,
                        "site_hash": pattern.site_hash,
                        "confidence": float(pattern.confidence),
                        "source": pattern.source,
                        "hit_count": 1,
                        "created_at": now,
                        "last_seen": now,
                    },
                )
            ]
        )
        return ("inserted", 1)
