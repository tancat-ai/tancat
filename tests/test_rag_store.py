"""Unit tests for ``src/rag_store.py``.

Uses a fake in-memory vector backend and deterministic embedding so no
model downloads are required in unit tests.  Integration tests that
verify the Milvus Lite backend and real embedding model are tagged
``integration``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from src.rag_store import (
    DocChunk,
    EmbeddingMismatchError,
    GoldenPattern,
    KnowledgeEntry,
    LearnedPattern,
    MilvusLiteBackend,
    RAGStore,
    RetrievedPattern,
    SearchHit,
    SentenceTransformerEmbedder,
    embedder_stamp_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_unlink(path: str) -> None:
    """Best-effort deletion — Milvus Lite creates directories, not files."""
    import os
    import shutil

    try:
        if os.path.exists(path):
            shutil.rmtree(path)
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

    @property
    def identity(self) -> str:
        """Phase 6 6b: embedder identity for stamping/cross-checks."""
        return f"fake@{self._dimension}"

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
        self._entries: list[tuple[list[float], dict[str, Any], str]] = []

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

    def counts_by_type(self) -> dict[str, int]:
        from collections import Counter

        counter: Counter[str] = Counter(str(meta.get("entry_type", "unknown")) for _vec, meta, _text in self._entries)
        return dict(counter)

    def query_dedup_keys(self, entry_type: str) -> list[str]:
        return [
            str(meta["dedup_key"])
            for _vec, meta, _text in self._entries
            if meta.get("entry_type") == entry_type and meta.get("dedup_key")
        ]

    def delete_learned(self) -> int:
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry[1].get("entry_type") in ("golden", "doc")]
        return before - len(self._entries)

    def find_learned(
        self,
        action_type: str,
        description: str,
        site_hash: str,
    ) -> dict[str, Any] | None:
        for _vec, meta, _text in self._entries:
            if (
                meta.get("entry_type") == "learned"
                and meta.get("action_type") == action_type
                and meta.get("description") == description
                and meta.get("site_hash") == site_hash
            ):
                return dict(meta)
        return None

    def increment_learned_hit(self, row: dict[str, Any]) -> int:
        for _vec, meta, _text in self._entries:
            if (
                meta.get("entry_type") == "learned"
                and meta.get("action_type") == row.get("action_type")
                and meta.get("description") == row.get("description")
                and meta.get("site_hash") == row.get("site_hash")
            ):
                new_hit = int(meta.get("hit_count", 0)) + 1
                meta["hit_count"] = new_hit
                return new_hit
        return 1

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


class TestCountsByTypeAndDeleteLearned:
    """B-036 Phase 2: per-type counts and learned-pattern pruning."""

    def _seed(self, fake_backend: InMemoryBackend) -> None:
        vec = [0.0] * fake_backend.dimension
        fake_backend.upsert(
            [
                KnowledgeEntry(vector=vec, text="g1", metadata={"entry_type": "golden"}),
                KnowledgeEntry(vector=vec, text="g2", metadata={"entry_type": "golden"}),
                KnowledgeEntry(vector=vec, text="d1", metadata={"entry_type": "doc"}),
                KnowledgeEntry(vector=vec, text="l1", metadata={"entry_type": "learned"}),
                KnowledgeEntry(vector=vec, text="x", metadata={}),
            ]
        )

    def test_counts_by_type(self, fake_backend: InMemoryBackend, rag_store: RAGStore) -> None:
        self._seed(fake_backend)
        counts = rag_store.counts_by_type()
        assert counts["golden"] == 2
        assert counts["doc"] == 1
        assert counts["learned"] == 1
        assert counts["unknown"] == 1

    def test_delete_learned_keeps_golden_and_docs(
        self,
        fake_backend: InMemoryBackend,
        rag_store: RAGStore,
    ) -> None:
        self._seed(fake_backend)
        deleted = rag_store.delete_learned()
        assert deleted == 2  # learned + unknown
        remaining = rag_store.counts_by_type()
        assert remaining["golden"] == 2
        assert remaining["doc"] == 1

    def test_delete_learned_with_nothing_to_prune(self, rag_store: RAGStore) -> None:
        assert rag_store.delete_learned() == 0


class TestUpsertPattern:
    """AI-035/B-036 Phase 3: learned-pattern write-back with dedup."""

    def _pattern(self, **overrides: str) -> LearnedPattern:
        base = {
            "action_type": "FILL",
            "description": "username",
            "locator": "#user-name",
            "site_hash": "abc123",
        }
        base.update(overrides)
        return LearnedPattern(**base)  # type: ignore[arg-type]

    def test_inserts_new_pattern(self, rag_store: RAGStore) -> None:
        status, hit = rag_store.upsert_pattern(self._pattern())
        assert status == "inserted"
        assert hit == 1
        counts = rag_store.counts_by_type()
        assert counts["learned"] == 1

    def test_repeat_bumps_hit_count_not_rows(self, rag_store: RAGStore) -> None:
        rag_store.upsert_pattern(self._pattern())
        status, hit = rag_store.upsert_pattern(self._pattern())
        assert status == "exists"
        assert hit == 2
        # Store stays bounded — one row, hit bumped
        assert rag_store.counts_by_type()["learned"] == 1

    def test_dedup_key_includes_action_and_site(self, rag_store: RAGStore) -> None:
        rag_store.upsert_pattern(self._pattern())
        # Same description, different action → distinct row
        rag_store.upsert_pattern(self._pattern(action_type="ASSERT"))
        # Same action+description, different site → distinct row
        rag_store.upsert_pattern(self._pattern(site_hash="def456"))
        assert rag_store.counts_by_type()["learned"] == 3

    def test_different_locator_same_key_is_deduped(self, rag_store: RAGStore) -> None:
        """A repeat with a changed locator still dedups (first locator wins)."""
        rag_store.upsert_pattern(self._pattern())
        status, _hit = rag_store.upsert_pattern(self._pattern(locator="input[name=user]"))
        assert status == "exists"
        assert rag_store.counts_by_type()["learned"] == 1


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
        inserted, skipped = rag_store.add_docs(docs)
        assert inserted == 1
        assert skipped == 0

    def test_add_docs_empty_list(self, rag_store: RAGStore) -> None:
        assert rag_store.add_docs([]) == (0, 0)

    def test_add_docs_dedup_skips_existing_key(self, rag_store: RAGStore) -> None:
        from src.pdf_ingest import doc_chunk_key

        chunk = DocChunk(text="same content", source="a.md", heading_path="A")
        chunk.dedup_key = doc_chunk_key(chunk)

        assert rag_store.add_docs([chunk]) == (1, 0)
        # Re-ingesting the identical chunk is a no-op.
        assert rag_store.add_docs([chunk]) == (0, 1)
        # Store holds exactly one row.
        assert rag_store.counts_by_type().get("doc") == 1

    def test_add_docs_mixed_new_and_dup(self, rag_store: RAGStore) -> None:
        from src.pdf_ingest import doc_chunk_key

        a = DocChunk(text="alpha content", source="a.md", heading_path="A")
        a.dedup_key = doc_chunk_key(a)
        b = DocChunk(text="beta content", source="b.md", heading_path="B")
        b.dedup_key = doc_chunk_key(b)

        assert rag_store.add_docs([a, b]) == (2, 0)
        # One new (a-dup) + one genuinely new (c).
        c = DocChunk(text="gamma content", source="c.md", heading_path="C")
        c.dedup_key = doc_chunk_key(c)
        assert rag_store.add_docs([a, c]) == (1, 1)

    def test_add_docs_empty_key_always_inserts(self, rag_store: RAGStore) -> None:
        """Chunks without a dedup_key (back-compat) are inserted every time."""
        chunk = DocChunk(text="no key", source="a.md", heading_path="A")  # dedup_key == ""
        assert rag_store.add_docs([chunk]) == (1, 0)
        assert rag_store.add_docs([chunk]) == (1, 0)
        assert rag_store.counts_by_type().get("doc") == 2

    def test_doc_chunk_key_normalisation(self) -> None:
        from src.pdf_ingest import doc_chunk_key

        base = DocChunk(text="Hello   World\nfoo", source="s.md", heading_path="H")
        whitespace_variant = DocChunk(text="Hello World foo", source="s.md", heading_path="H")
        case_variant = DocChunk(text="hello world foo", source="s.md", heading_path="H")
        assert doc_chunk_key(base) == doc_chunk_key(whitespace_variant)
        assert doc_chunk_key(base) == doc_chunk_key(case_variant)

        different_text = DocChunk(text="Completely different", source="s.md", heading_path="H")
        different_heading = DocChunk(text="Hello World foo", source="s.md", heading_path="Other")
        different_source = DocChunk(text="Hello World foo", source="t.md", heading_path="H")
        assert doc_chunk_key(base) != doc_chunk_key(different_text)
        assert doc_chunk_key(base) != doc_chunk_key(different_heading)
        assert doc_chunk_key(base) != doc_chunk_key(different_source)

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

    def test_counts_by_type(self) -> None:
        """B-036 Phase 2: per-entry_type counts against real Milvus."""
        backend = MilvusLiteBackend(self.db_path, dimension=16)
        vec = [0.0] * 15 + [1.0]
        backend.upsert(
            [
                KnowledgeEntry(vector=vec, text="g1", metadata={"entry_type": "golden"}),
                KnowledgeEntry(vector=vec, text="g2", metadata={"entry_type": "golden"}),
                KnowledgeEntry(vector=vec, text="d1", metadata={"entry_type": "doc"}),
                KnowledgeEntry(vector=vec, text="l1", metadata={"entry_type": "learned"}),
            ]
        )
        counts = backend.counts_by_type()
        assert counts["golden"] == 2
        assert counts["doc"] == 1
        assert counts["learned"] == 1

    def test_delete_learned_keeps_golden_and_docs(self) -> None:
        """B-036 Phase 2: prune learned entries against real Milvus."""
        backend = MilvusLiteBackend(self.db_path, dimension=16)
        vec = [0.0] * 15 + [1.0]
        backend.upsert(
            [
                KnowledgeEntry(vector=vec, text="g1", metadata={"entry_type": "golden"}),
                KnowledgeEntry(vector=vec, text="d1", metadata={"entry_type": "doc"}),
                KnowledgeEntry(vector=vec, text="l1", metadata={"entry_type": "learned"}),
            ]
        )
        assert backend.delete_learned() == 1
        assert backend.count() == 2
        counts = backend.counts_by_type()
        assert counts.get("learned", 0) == 0
        assert counts["golden"] == 1
        assert counts["doc"] == 1


class TestEmbedderStamp:
    """Phase 6 6b — embedder stamp written at creation, verified on open."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        import atexit
        import uuid

        self.db_path = str(tmp_path / f"stamp_{uuid.uuid4().hex[:8]}.db")
        atexit.register(lambda: _safe_unlink(self.db_path))
        atexit.register(lambda: _safe_unlink(embedder_stamp_path(self.db_path)))

    def test_stamp_written_on_creation(self) -> None:
        import json

        backend = MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="model-a@16")
        backend.count()  # opens the client -> creates + stamps
        stamp = json.loads(Path(embedder_stamp_path(self.db_path)).read_text(encoding="utf-8"))
        assert stamp["embedder"] == "model-a@16"
        assert stamp["dim"] == 16

    def test_reopen_same_identity_is_ok(self) -> None:
        MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="model-a@16").count()
        reopened = MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="model-a@16")
        assert reopened.count() == 0  # no refusal

    def test_dimension_mismatch_refused(self) -> None:
        MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="model-a@16").count()
        with pytest.raises(EmbeddingMismatchError) as excinfo:
            MilvusLiteBackend(self.db_path, dimension=384, embedder_identity="model-a@384").count()
        assert "dimension" in str(excinfo.value)
        assert "--reindex" in str(excinfo.value)

    def test_embedder_mismatch_refused(self) -> None:
        MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="model-a@16").count()
        with pytest.raises(EmbeddingMismatchError) as excinfo:
            MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="model-b@16").count()
        assert "model-a@16" in str(excinfo.value)
        assert "model-b@16" in str(excinfo.value)
        assert "--reindex" in str(excinfo.value)

    def test_verify_embedder_cross_check(self) -> None:
        """RAGStore-level cross-check re-verifies with the ACTUAL embedder."""
        backend = MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="model-a@16")
        backend.count()
        backend.verify_embedder("model-a@16")  # matches
        with pytest.raises(EmbeddingMismatchError):
            backend.verify_embedder("model-b@16")

    def test_legacy_store_migrated_with_default_embedder(self) -> None:
        """A pre-stamp store (no sidecar) is accepted only for the default model."""
        from src.rag_store import DEFAULT_EMBEDDER_IDENTITY

        MilvusLiteBackend(self.db_path, dimension=384, embedder_identity="legacy@384").count()
        Path(embedder_stamp_path(self.db_path)).unlink()  # simulate pre-stamp store

        reopened = MilvusLiteBackend(self.db_path, dimension=384, embedder_identity=DEFAULT_EMBEDDER_IDENTITY)
        assert reopened.count() == 0
        # Migration: the stamp is now written.
        import json

        stamp = json.loads(Path(embedder_stamp_path(self.db_path)).read_text(encoding="utf-8"))
        assert stamp["embedder"] == DEFAULT_EMBEDDER_IDENTITY

    def test_legacy_store_refused_with_custom_embedder(self) -> None:
        MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="legacy@16").count()
        Path(embedder_stamp_path(self.db_path)).unlink()  # simulate pre-stamp store
        with pytest.raises(EmbeddingMismatchError) as excinfo:
            MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="custom@16").count()
        assert "no embedder stamp" in str(excinfo.value)

    def test_clear_removes_stamp(self) -> None:
        backend = MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="model-a@16")
        backend.count()
        assert Path(embedder_stamp_path(self.db_path)).exists()
        backend.clear()
        assert not Path(embedder_stamp_path(self.db_path)).exists()

    def test_ragstore_refuses_embedder_mismatch(self) -> None:
        """RAGStore refuses ops when its embedder differs from the store's stamp.

        The store is stamped 'other@16' by its creating backend; RAGStore is
        given an embedder with identity 'fake@16' — the cross-check must fire
        before any Milvus access (pure sidecar read, no second client needed).
        """
        MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="other@16").count()
        store = RAGStore(
            MilvusLiteBackend(self.db_path, dimension=16, embedder_identity="other@16"),
            FakeEmbedder(dimension=16),  # identity: fake@16
        )
        with pytest.raises(EmbeddingMismatchError):
            store.retrieve("CLICK: x")

    def test_delete_learned_empty(self) -> None:
        backend = MilvusLiteBackend(self.db_path, dimension=16)
        assert backend.delete_learned() == 0


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

    def test_golden_site_hash_roundtrips(self, ml_store: RAGStore) -> None:
        """B-047 residual: a golden's site_hash must survive the store round-trip.

        Regression: ``MilvusLiteBackend.search`` omitted ``site_hash`` from
        ``output_fields``, so every retrieved pattern looked site-agnostic and
        the site-scoping gates could not fire.
        """
        ml_store.add_patterns(
            [
                GoldenPattern(
                    action="FILL",
                    description="username",
                    expected_locator="#user-name",
                    site_hash="abc123",
                )
            ]
        )
        results = ml_store.retrieve("FILL: username", k=3)
        assert any(r.selector == "#user-name" and r.site_hash == "abc123" for r in results)

    def test_learned_site_hash_roundtrips(self, ml_store: RAGStore) -> None:
        """AI-035 Phase 2: a learned pattern's site_hash must round-trip too."""
        ml_store.upsert_pattern(
            LearnedPattern(
                action_type="FILL",
                description="password",
                locator="#password",
                site_hash="abc123",
            )
        )
        results = ml_store.retrieve("FILL: password", k=3)
        assert any(r.selector == "#password" and r.site_hash == "abc123" for r in results)

    def test_upsert_pattern_insert_dedup_hit(self, ml_store: RAGStore) -> None:
        """AI-035: learned patterns insert once, dedup bumps hit_count."""
        pattern = LearnedPattern(
            action_type="FILL",
            description="username",
            locator="#user-name",
            site_hash="abc123",
        )
        status, hit = ml_store.upsert_pattern(pattern)
        assert status == "inserted"
        assert hit == 1

        status, hit = ml_store.upsert_pattern(pattern)
        assert status == "exists"
        assert hit == 2

        # One row total, still searchable
        assert ml_store.counts_by_type()["learned"] == 1
        results = ml_store.retrieve("FILL: username", k=5)
        assert any(r.selector == "#user-name" for r in results)

    def test_upsert_pattern_different_sites_distinct(self, ml_store: RAGStore) -> None:
        a = LearnedPattern(action_type="FILL", description="username", locator="#u-a", site_hash="aaa")
        b = LearnedPattern(action_type="FILL", description="username", locator="#u-b", site_hash="bbb")
        assert ml_store.upsert_pattern(a)[0] == "inserted"
        assert ml_store.upsert_pattern(b)[0] == "inserted"
        assert ml_store.counts_by_type()["learned"] == 2

    def test_delete_learned_removes_only_learned(self, ml_store: RAGStore) -> None:
        ml_store.upsert_pattern(
            LearnedPattern(action_type="FILL", description="username", locator="#user-name", site_hash="abc123")
        )
        ml_store.add_patterns([GoldenPattern(action="FILL", description="password", expected_locator="#password")])
        assert ml_store.delete_learned() == 1
        assert ml_store.counts_by_type().get("learned", 0) == 0
        assert ml_store.counts_by_type()["golden"] == 1


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
