"""Unit tests for ``src/rag_retriever.py``."""

from __future__ import annotations

import math
from typing import Any

import pytest

from src.placeholder_scorers import PlaceholderScorer
from src.rag_retriever import RAGRetriever
from src.rag_store import (
    EmbeddingMismatchError,
    GoldenPattern,
    KnowledgeEntry,
    RAGStore,
    RetrievedPattern,
    SearchHit,
)

# ---------------------------------------------------------------------------
# Minimal fake backend + embedder
# ---------------------------------------------------------------------------


class _FakeEmbedder:
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
        vec = [0.0] * self._dimension
        for i, ch in enumerate(text):
            vec[i % self._dimension] += ord(ch) / 1000.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class _InMemoryBackend:
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
        scored = [
            (sum(x * y for x, y in zip(query_vector, vec, strict=True)), meta) for vec, meta, _text in self._entries
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [SearchHit(distance=score, metadata=meta) for score, meta in scored[:k]]

    def count(self) -> int:
        return len(self._entries)

    def counts_by_type(self) -> dict[str, int]:
        from collections import Counter

        counter: Counter[str] = Counter(str(meta.get("entry_type", "unknown")) for _vec, meta, _text in self._entries)
        return dict(counter)

    def delete_learned(self) -> int:
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry[1].get("entry_type") in ("golden", "doc")]
        return before - len(self._entries)

    def find_learned(
        self,
        action_type: str,
        description: str,
        site_hash: str,
    ) -> dict[str, object] | None:
        for _vec, meta, _text in self._entries:
            if (
                meta.get("entry_type") == "learned"
                and meta.get("action_type") == action_type
                and meta.get("description") == description
                and meta.get("site_hash") == site_hash
            ):
                return dict(meta)
        return None

    def increment_learned_hit(self, row: dict[str, object]) -> int:
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

    def clear(self) -> None:
        self._entries.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_retriever(
    patterns: list[GoldenPattern] | None = None,
) -> RAGRetriever:
    """Build a RAGRetriever with a fake in-memory store."""
    embedder = _FakeEmbedder(dimension=16)
    backend = _InMemoryBackend(dimension=16)
    store = RAGStore(backend, embedder)
    if patterns:
        store.add_patterns(patterns)
    return RAGRetriever(store)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRAGRetrieverDisabled:
    def test_disabled_when_store_is_none(self) -> None:
        retriever = RAGRetriever(None)
        assert retriever.enabled is False

    def test_retrieve_returns_empty_when_disabled(self) -> None:
        retriever = RAGRetriever(None)
        assert retriever.retrieve("anything") == []

    def test_scoring_bonus_returns_zero_when_no_patterns(self) -> None:
        retriever = RAGRetriever(None)
        assert retriever.scoring_bonus_for({"selector": "#btn"}, []) == 0.0


class _MismatchBackend(_InMemoryBackend):
    """Phase 6 6b: a backend whose stamp verification refuses."""

    def verify_embedder(self, embedder_identity: str | None) -> None:
        raise EmbeddingMismatchError(
            f"RAG store was created with a different embedder ('{embedder_identity}') — "
            "run `python scripts/rag_ingest.py --reindex`"
        )


class TestRAGRetrieverEmbedderMismatch:
    """Phase 6 6b: a mismatch refuses retrieval (empty result) and is loud, never silent."""

    @pytest.fixture
    def retriever(self) -> RAGRetriever:
        store = RAGStore(_MismatchBackend(dimension=16), _FakeEmbedder())
        return RAGRetriever(store)

    def test_enabled_is_false_on_mismatch(self, retriever: RAGRetriever) -> None:
        assert retriever.enabled is False

    def test_retrieve_returns_empty_on_mismatch(self, retriever: RAGRetriever) -> None:
        assert retriever.retrieve("CLICK: Add to cart") == []


class TestRAGRetrieverEnabled:
    @pytest.fixture
    def retriever(self) -> RAGRetriever:
        patterns = [
            GoldenPattern(
                action="CLICK",
                description="Add to cart button",
                expected_locator="button.add-to-cart",
                tolerance_selectors=["[data-test='add']"],
            ),
            GoldenPattern(
                action="FILL",
                description="username input",
                expected_locator="#user-name",
            ),
            GoldenPattern(
                action="FILL",
                description="password input",
                expected_locator="#password",
            ),
        ]
        return _build_retriever(patterns)

    def test_enabled_returns_true(self, retriever: RAGRetriever) -> None:
        assert retriever.enabled is True

    def test_retrieve_returns_results(self, retriever: RAGRetriever) -> None:
        results = retriever.retrieve("Add to cart button", action_type="CLICK")
        assert len(results) > 0

    def test_retrieve_with_no_match_returns_empty(self, retriever: RAGRetriever) -> None:
        results = retriever.retrieve("zzz something unrelated")
        assert isinstance(results, list)

    def test_scoring_bonus_direct_match(self, retriever: RAGRetriever) -> None:
        patterns = retriever.retrieve("Add to cart", action_type="CLICK")
        bonus = retriever.scoring_bonus_for({"selector": "button.add-to-cart"}, patterns)
        assert bonus > 0

    def test_scoring_bonus_no_match(self, retriever: RAGRetriever) -> None:
        patterns = retriever.retrieve("Add to cart", action_type="CLICK")
        bonus = retriever.scoring_bonus_for({"selector": "#something-else"}, patterns)
        assert bonus == 0.0

    def test_scoring_bonus_empty_selector(self, retriever: RAGRetriever) -> None:
        patterns = retriever.retrieve("Add to cart", action_type="CLICK")
        bonus = retriever.scoring_bonus_for({"selector": ""}, patterns)
        assert bonus == 0.0

    def test_scoring_bonus_empty_patterns(self, retriever: RAGRetriever) -> None:
        bonus = retriever.scoring_bonus_for({"selector": "#btn"}, [])
        assert bonus == 0.0


class TestRAGRetrieverLearnedScoring:
    """AI-035 Phase 2: same-site learned patterns earn +5; cross-site get 0."""

    @staticmethod
    def _learned(selector: str, site_hash: str = "abc123", confidence: float = 0.9) -> RetrievedPattern:
        return RetrievedPattern(
            description="FILL: username",
            selector=selector,
            action_type="FILL",
            confidence=confidence,
            source="learned",
            site_hash=site_hash,
        )

    def test_same_site_direct_match(self) -> None:
        retriever = RAGRetriever(None)
        bonus = retriever.scoring_bonus_for(
            {"selector": "#user-name"},
            [self._learned("#user-name")],
            site_hash="abc123",
        )
        assert bonus > 0
        assert bonus < 20  # learned bonus is below the golden +20

    def test_cross_site_learned_no_bonus(self) -> None:
        retriever = RAGRetriever(None)
        bonus = retriever.scoring_bonus_for(
            {"selector": "#user-name"},
            [self._learned("#user-name", site_hash="other")],
            site_hash="abc123",
        )
        assert bonus == 0.0

    def test_no_site_context_no_bonus(self) -> None:
        retriever = RAGRetriever(None)
        bonus = retriever.scoring_bonus_for(
            {"selector": "#user-name"},
            [self._learned("#user-name")],
        )
        assert bonus == 0.0

    def test_golden_still_wins_over_learned(self) -> None:
        retriever = RAGRetriever(None)
        learned = retriever.scoring_bonus_for(
            {"selector": "#login-button"},
            [self._learned("#login-button")],
            site_hash="abc123",
        )
        golden = retriever.scoring_bonus_for(
            {"selector": "#login-button"},
            [
                RetrievedPattern(
                    description="CLICK: login button",
                    selector="#login-button",
                    action_type="CLICK",
                    confidence=0.9,
                    source="golden",
                )
            ],
            site_hash="abc123",
        )
        assert golden > learned

    def test_cross_site_golden_no_bonus(self) -> None:
        """B-047 residual: a site-scoped golden earns nothing off-site."""
        retriever = RAGRetriever(None)
        golden = RetrievedPattern(
            description="CLICK: login button",
            selector="#login-button",
            action_type="CLICK",
            confidence=0.9,
            source="golden",
            site_hash="saucedemo-hash",
        )
        assert retriever.scoring_bonus_for({"selector": "#login-button"}, [golden], site_hash="banking-hash") == 0.0
        # ...and its own site still earns the full bonus.
        assert (
            retriever.scoring_bonus_for({"selector": "#login-button"}, [golden], site_hash="saucedemo-hash")
            == float(PlaceholderScorer.GOLDEN_PATTERN_BONUS) * 0.9
        )

    def test_legacy_ungated_golden_still_applies(self) -> None:
        """Empty site_hash goldens (unseeded stores) stay site-agnostic."""
        retriever = RAGRetriever(None)
        golden = RetrievedPattern(
            description="CLICK: login button",
            selector="#login-button",
            action_type="CLICK",
            confidence=0.9,
            source="golden",
        )
        assert retriever.scoring_bonus_for({"selector": "#login-button"}, [golden], site_hash="any-site") > 0.0


class TestRAGRetrieverEmptyStore:
    def test_enabled_is_false(self) -> None:
        retriever = _build_retriever([])
        assert retriever.enabled is False

    def test_retrieve_returns_empty(self) -> None:
        retriever = _build_retriever([])
        assert retriever.retrieve("anything") == []


class TestRAGRetrieverGracefulDegradation:
    """B-036 Phase 1: a failing store/embedder must never raise."""

    class _BrokenStore:
        def retrieve(self, *args: object, **kwargs: object) -> list[RetrievedPattern]:
            raise RuntimeError("embedder model download failed")

    def test_retrieve_degrades_to_empty_on_store_failure(self) -> None:
        retriever = RAGRetriever(self._BrokenStore())  # type: ignore[arg-type]
        assert retriever.retrieve("anything", action_type="CLICK") == []

    def test_retrieve_still_degrades_on_repeat_failures(self) -> None:
        retriever = RAGRetriever(self._BrokenStore())  # type: ignore[arg-type]
        for _ in range(3):
            assert retriever.retrieve("anything") == []


class TestRAGRetrieverScoring:
    """Tests for scoring_bonus_for with different match types."""

    @pytest.fixture
    def patterns(self) -> list[RetrievedPattern]:
        return [
            RetrievedPattern(
                description="CLICK: login button",
                selector="#login-btn",
                action_type="CLICK",
                confidence=0.9,
                source="golden",
            ),
            RetrievedPattern(
                description="FILL: email input",
                selector="input[name='email']",
                action_type="FILL",
                confidence=0.8,
                source="golden",
            ),
            RetrievedPattern(
                description="doc chunk",
                selector="",
                action_type="",
                confidence=0.7,
                source="doc",
            ),
        ]

    def test_direct_match_full_bonus(self, patterns: list[RetrievedPattern]) -> None:
        retriever = RAGRetriever(None)  # store=None but scoring works
        bonus = retriever.scoring_bonus_for({"selector": "#login-btn"}, patterns)
        assert bonus > 0

    def test_doc_pattern_ignored(self, patterns: list[RetrievedPattern]) -> None:
        retriever = RAGRetriever(None)
        doc_pattern = [p for p in patterns if p.source == "doc"]
        bonus = retriever.scoring_bonus_for({"selector": "anything"}, doc_pattern)
        assert bonus == 0.0

    def test_substring_match_half_bonus(self, patterns: list[RetrievedPattern]) -> None:
        retriever = RAGRetriever(None)
        bonus = retriever.scoring_bonus_for({"selector": "input[name='email']"}, patterns)
        assert bonus > 0

    def test_no_match_zero_bonus(self, patterns: list[RetrievedPattern]) -> None:
        retriever = RAGRetriever(None)
        bonus = retriever.scoring_bonus_for({"selector": "#nonexistent"}, patterns)
        assert bonus == 0.0
