"""Unit tests for ``src/rag_store.py``.

Uses a fake in-memory vector backend and deterministic embedding so no
model downloads are required in unit tests.  Integration tests that
verify the Milvus Lite backend and real embedding model are tagged
``integration``.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.rag_store import (
    DocChunk,
    GoldenPattern,
    KnowledgeEntry,
    MilvusLiteBackend,
    RAGStore,
    RetrievedPattern,
    SearchHit,
    SentenceTransformerEmbedder,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_unlink(path: str) -> None:
    """Best-effort file deletion — ignores PermissionError on Windows."""
    import os

    try:
        if os.path.exists(path):
            os.unlink(path)
    except PermissionError, OSError:
        pass  # milvus-lite holds file locks briefly


# ---------------------------------------------------------------------------
# Fake backend + embedder (no model downloads for unit tests)
# ---------------------------------------------------------------------------


class FakeEmbedder:
    """Deterministic embedder: uses character sums for fake vectors."""

    def __init__(self, dimension: int = 16) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        return self._fake_vector(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._fake_vector(t) for t in texts]

    def _fake_vector(self, text: str) -> list[float]:
        """Produce a deterministic unit vector from text via character sums.

        The first *dimension* values are derived from character ordinals;
        the remainder of the 384-dim array is zero.  This is NOT a real
        embedding — it just gives different texts different vectors for
        retrieval testing.
        """
        vec = [0.0] * self._dimension
        for i, ch in enumerate(text):
            vec[i % self._dimension] += ord(ch) / 1000.0
        # Normalize to unit length for cosine similarity
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class InMemoryBackend:
    """Stores vectors in a Python list with brute-force cosine similarity.

    Satisfies ``VectorStoreBackend`` for testing.
    """

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension
        self._entries: list[tuple[list[float], dict[str, str], str]] = []

    @property
    def dimension(self) -> int:
        return self._dimension

    def upsert(self, entries: list[KnowledgeEntry]) -> int:
        for e in entries:
            self._entries.append((e.vector, e.metadata, e.text))
        return len(entries)

    def search(self, query_vector: list[float], k: int) -> list[SearchHit]:
        if not self._entries:
            return []

        scored = [(self._cosine_sim(query_vector, vec), meta) for vec, meta, _text in self._entries]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [SearchHit(distance=score, metadata=meta) for score, meta in scored[:k]]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        return max(0.0, dot)  # cosine distance surrogate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder(dimension=16)


@pytest.fixture
def fake_backend(fake_embedder: FakeEmbedder) -> InMemoryBackend:
    return InMemoryBackend(dimension=fake_embedder.dimension)


@pytest.fixture
def rag_store(fake_backend: InMemoryBackend, fake_embedder: FakeEmbedder) -> RAGStore:
    return RAGStore(fake_backend, fake_embedder)


@pytest.fixture
def populated_store(rag_store: RAGStore) -> RAGStore:
    """Store with 5 golden patterns and 3 doc chunks."""
    patterns = [
        GoldenPattern(
            action="CLICK",
            description="Add to cart button",
            expected_locator="button.add-to-cart",
            tolerance_selectors=["[data-test='add']"],
            expected_page="/products",
        ),
        GoldenPattern(
            action="FILL",
            description="username input",
            expected_locator="#user-name",
            tolerance_selectors=["input[name='user-name']"],
            expected_page="/login",
        ),
        GoldenPattern(
            action="FILL",
            description="password input",
            expected_locator="#password",
            tolerance_selectors=["input[name='password']"],
            expected_page="/login",
        ),
        GoldenPattern(
            action="CLICK",
            description="login button",
            expected_locator="#login-button",
            tolerance_selectors=["[data-test='submit']"],
            expected_page="/login",
        ),
        GoldenPattern(
            action="ASSERT",
            description="confirmation message appears",
            expected_locator=".alert-success",
            tolerance_selectors=["[role='alert']"],
            expected_page="/cart",
        ),
    ]
    docs = [
        DocChunk(
            text="Prefer user-facing attributes like get_by_role over CSS selectors.",
            source="playwright-locators.md",
            heading_path="Locators > Best Practices",
        ),
        DocChunk(
            text="Use to_have_url() for page-level assertions instead of DOM elements.",
            source="playwright-assertions.md",
            heading_path="Assertions > Page",
        ),
        DocChunk(
            text="Actionability checks ensure elements are visible, enabled, and stable.",
            source="playwright-actionability.md",
            heading_path="Actionability > Overview",
        ),
    ]
    rag_store.add_patterns(patterns)
    rag_store.add_docs(docs)
    return rag_store


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestGoldenPattern:
    def test_query_text_combines_action_and_description(self) -> None:
        p = GoldenPattern(
            action="CLICK",
            description="Add to cart button",
            expected_locator="#btn",
        )
        assert p.query_text == "CLICK: Add to cart button"

    def test_defaults(self) -> None:
        p = GoldenPattern(action="CLICK", description="x", expected_locator="#x")
        assert p.tolerance_selectors == []
        assert p.expected_page == ""


class TestSearchHit:
    def test_confidence_from_distance(self) -> None:
        hit = SearchHit(distance=0.2, metadata={})
        assert hit.confidence == 0.2

    def test_confidence_floor_zero(self) -> None:
        hit = SearchHit(distance=-0.5, metadata={})
        assert hit.confidence == 0.0

    def test_confidence_ceil_one(self) -> None:
        hit = SearchHit(distance=1.5, metadata={})
        assert hit.confidence == 1.0


# ---------------------------------------------------------------------------
# FakeEmbedder tests
# ---------------------------------------------------------------------------


class TestFakeEmbedder:
    def test_different_texts_produce_different_vectors(self) -> None:
        e = FakeEmbedder()
        v1 = e.embed("Add to cart")
        v2 = e.embed("Login button")
        assert v1 != v2

    def test_same_text_produces_same_vector(self) -> None:
        e = FakeEmbedder()
        assert e.embed("hello") == e.embed("hello")

    def test_dimension(self) -> None:
        e = FakeEmbedder(dimension=32)
        assert e.dimension == 32
        assert len(e.embed("test")) == 32

    def test_batch(self) -> None:
        e = FakeEmbedder()
        texts = ["a", "b", "c"]
        results = e.embed_batch(texts)
        assert len(results) == 3
        assert results[0] == e.embed("a")


# ---------------------------------------------------------------------------
# InMemoryBackend tests
# ---------------------------------------------------------------------------


class TestInMemoryBackend:
    def test_empty_count(self, fake_backend: InMemoryBackend) -> None:
        assert fake_backend.count() == 0

    def test_upsert_and_count(self, fake_backend: InMemoryBackend) -> None:
        vec = [0.0] * fake_backend.dimension
        fake_backend.upsert([KnowledgeEntry(vector=vec, text="test", metadata={"k": "v"})])
        assert fake_backend.count() == 1

    def test_search_returns_ordered(self, fake_backend: InMemoryBackend) -> None:
        vec_a = [1.0] + [0.0] * (fake_backend.dimension - 1)
        vec_b = [0.0, 0.5] + [0.0] * (fake_backend.dimension - 2)
        fake_backend.upsert(
            [
                KnowledgeEntry(vector=vec_b, text="far", metadata={"id": "far"}),
                KnowledgeEntry(vector=vec_a, text="near", metadata={"id": "near"}),
            ]
        )
        results = fake_backend.search(vec_a, k=2)
        assert results[0].metadata["id"] == "near"
        assert results[0].distance > results[1].distance

    def test_clear(self, fake_backend: InMemoryBackend) -> None:
        vec = [0.0] * fake_backend.dimension
        fake_backend.upsert([KnowledgeEntry(vector=vec, text="test", metadata={})])
        assert fake_backend.count() == 1
        fake_backend.clear()
        assert fake_backend.count() == 0

    def test_empty_search(self, fake_backend: InMemoryBackend) -> None:
        results = fake_backend.search([0.0] * fake_backend.dimension, k=3)
        assert results == []


# ---------------------------------------------------------------------------
# RAGStore tests
# ---------------------------------------------------------------------------


class TestRAGStoreEmpty:
    def test_is_empty_true(self, rag_store: RAGStore) -> None:
        assert rag_store.is_empty is True

    def test_retrieve_empty_store_returns_empty(self, rag_store: RAGStore) -> None:
        results = rag_store.retrieve("anything")
        assert results == []


class TestRAGStorePopulated:
    def test_is_empty_false(self, populated_store: RAGStore) -> None:
        assert populated_store.is_empty is False

    def test_add_patterns_returns_count(self, rag_store: RAGStore) -> None:
        patterns = [GoldenPattern(action="CLICK", description="btn", expected_locator="#b")]
        count = rag_store.add_patterns(patterns)
        assert count == 1
        assert rag_store.is_empty is False

    def test_add_patterns_empty_list(self, rag_store: RAGStore) -> None:
        assert rag_store.add_patterns([]) == 0

    def test_add_docs_returns_count(self, rag_store: RAGStore) -> None:
        docs = [DocChunk(text="some documentation")]
        count = rag_store.add_docs(docs)
        assert count == 1

    def test_add_docs_empty_list(self, rag_store: RAGStore) -> None:
        assert rag_store.add_docs([]) == 0

    def test_retrieve_returns_results(self, populated_store: RAGStore) -> None:
        results = populated_store.retrieve("CLICK: Add to cart button")
        assert len(results) > 0
        # The top result should be the exact match
        top = results[0]
        assert "cart" in top.description.lower()
        assert top.confidence > 0.0

    def test_retrieve_with_action_type_filter(self, populated_store: RAGStore) -> None:
        results = populated_store.retrieve("FILL: username input", action_type="FILL")
        assert len(results) > 0

    def test_retrieve_min_confidence_threshold(self, populated_store: RAGStore) -> None:
        # Very high threshold should filter everything
        results = populated_store.retrieve("anything", min_confidence=0.999)
        assert results == []

    def test_retrieve_results_sorted_by_confidence(self, populated_store: RAGStore) -> None:
        results = populated_store.retrieve("CLICK: something", k=5)
        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i].confidence >= results[i + 1].confidence

    def test_retrieve_max_k(self, populated_store: RAGStore) -> None:
        results = populated_store.retrieve("anything", k=2)
        assert len(results) <= 2

    def test_golden_patterns_have_selector(self, populated_store: RAGStore) -> None:
        results = populated_store.retrieve("CLICK: login", k=5)
        golden = [r for r in results if r.source == "golden"]
        assert len(golden) > 0
        assert golden[0].selector != ""

    def test_doc_chunks_have_no_selector(self, populated_store: RAGStore) -> None:
        results = populated_store.retrieve("page assertion", k=5, min_confidence=0.0)
        docs = [r for r in results if r.source == "doc"]
        # Docs have empty selectors
        for d in docs:
            assert d.selector == ""
            assert d.action_type == ""


class TestRetrievedPattern:
    def test_default_source_and_page(self) -> None:
        r = RetrievedPattern(
            description="test",
            selector="#x",
            action_type="CLICK",
            confidence=0.9,
        )
        assert r.source == ""
        assert r.page == ""


# ---------------------------------------------------------------------------
# Integration tests (real backends — skipped when deps not available)
# ---------------------------------------------------------------------------


class TestMilvusLiteBackend:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        """Create a temporary database for each test."""
        import atexit
        import uuid

        self.db_path = str(tmp_path / f"test_rag_{uuid.uuid4().hex[:8]}.db")
        # Ensure cleanup even if test crashes
        atexit.register(lambda: _safe_unlink(self.db_path))

    def test_create_and_count(self) -> None:
        backend = MilvusLiteBackend(self.db_path, dimension=16)
        assert backend.count() == 0

    def test_upsert_and_search(self) -> None:
        backend = MilvusLiteBackend(self.db_path, dimension=16)
        vec_a = [1.0] + [0.0] * 15
        vec_b = [0.0, 1.0] + [0.0] * 14
        norm_a = math.sqrt(sum(v * v for v in vec_a))
        norm_b = math.sqrt(sum(v * v for v in vec_b))
        vec_a_norm = [v / norm_a for v in vec_a]
        vec_b_norm = [v / norm_b for v in vec_b]

        backend.upsert(
            [
                KnowledgeEntry(
                    vector=vec_a_norm,
                    text="first",
                    metadata={"action_type": "CLICK", "selector": "#a"},
                ),
                KnowledgeEntry(
                    vector=vec_b_norm,
                    text="second",
                    metadata={"action_type": "FILL", "selector": "#b"},
                ),
            ]
        )
        assert backend.count() == 2

        results = backend.search(vec_a_norm, k=2)
        assert len(results) == 2
        assert results[0].metadata.get("selector") == "#a"

    def test_clear(self) -> None:
        backend = MilvusLiteBackend(self.db_path, dimension=16)
        vec = [0.0] * 15 + [1.0]
        norm = math.sqrt(sum(v * v for v in vec))
        vec_norm = [v / norm for v in vec]
        backend.upsert([KnowledgeEntry(vector=vec_norm, text="x", metadata={})])
        assert backend.count() == 1
        backend.clear()
        # Client closed after clear (file may persist on Windows
        # due to milvus-lite lock — atexit cleanup handles it).
        assert backend._client is None

    def test_upsert_empty(self) -> None:
        backend = MilvusLiteBackend(self.db_path, dimension=16)
        assert backend.upsert([]) == 0
        assert backend.count() == 0


class TestMilvusLiteRAGStore:
    """End-to-end RAGStore tests backed by real Milvus Lite + FakeEmbedder."""

    @pytest.fixture
    def ml_store(self, tmp_path: Path, fake_embedder: FakeEmbedder) -> RAGStore:
        import atexit

        db_path = str(tmp_path / "test_ragstore_integration.db")
        atexit.register(lambda: _safe_unlink(db_path))
        backend = MilvusLiteBackend(db_path, dimension=fake_embedder.dimension)
        return RAGStore(backend, fake_embedder)

    def test_full_cycle(self, ml_store: RAGStore) -> None:
        assert ml_store.is_empty

        patterns = [
            GoldenPattern(
                action="CLICK",
                description="checkout button",
                expected_locator="#checkout",
            ),
            GoldenPattern(
                action="FILL",
                description="search box",
                expected_locator="input.search",
            ),
        ]
        ml_store.add_patterns(patterns)
        assert not ml_store.is_empty

        results = ml_store.retrieve("CLICK: checkout button", k=3)
        assert len(results) > 0
        top = results[0]
        assert top.action_type == "CLICK"
        assert top.selector == "#checkout"


# ---------------------------------------------------------------------------
# SentenceTransformerEmbedder smoke tests
# ---------------------------------------------------------------------------


class TestSentenceTransformerEmbedder:
    """These tests require internet (first run) to download the model.

    They are marked as slow and may be skipped in CI.
    """

    @pytest.fixture
    def real_embedder(self) -> SentenceTransformerEmbedder:
        return SentenceTransformerEmbedder()

    def test_dimension(self, real_embedder: SentenceTransformerEmbedder) -> None:
        assert real_embedder.dimension == 384

    @pytest.mark.slow
    def test_embed_returns_correct_dimension(
        self,
        real_embedder: SentenceTransformerEmbedder,
    ) -> None:
        vec = real_embedder.embed("Add to cart button")
        assert len(vec) == 384
        # Normalized embeddings should have unit length
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 0.001

    @pytest.mark.slow
    def test_embed_batch(self, real_embedder: SentenceTransformerEmbedder) -> None:
        texts = ["Add to cart", "Login button", "Checkout"]
        vectors = real_embedder.embed_batch(texts)
        assert len(vectors) == 3
        assert all(len(v) == 384 for v in vectors)

    @pytest.mark.slow
    def test_embed_batch_empty(
        self,
        real_embedder: SentenceTransformerEmbedder,
    ) -> None:
        assert real_embedder.embed_batch([]) == []
