"""Per-part RAG switches (j-0247): each part can be off, and proves it.

RAG has four parts and each one now has its own switch beside the global
``RAG_ENABLED`` gate:

======================  =====================  ======================
part                    switch                 entry type
======================  =====================  ======================
bundled golden pack     ``RAG_GOLDEN``         ``golden``
Playwright doc chunks   ``RAG_DOC_CHUNKS``     ``doc``
learned positives       ``RAG_LEARNED``        ``learned``
contrastive negatives   ``RAG_NEGATIVES``      ``learned_negative``
======================  =====================  ======================

What these tests pin:

* **Default = on = nothing changes.** With every switch unset the same inputs
  give exactly the same writes, retrievals and scores as before the switches
  existed (the documented constants: golden +20, learned +5, negative -5).
* **Off = inert at both ends.** A part switched to ``0`` is not written, not
  returned by retrieval, and not scored - so it cannot tilt a measurement.
* **A typo is refused.** Any value that is not ``1``, ``0`` or unset raises
  ``RAGSwitchError``; it is never read as "on".

Each switch-off test fails before the gates were wired in (the write, the hit
or the bonus still happened), and the default tests fail before the module
existed.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from src.placeholder_scorers import PlaceholderScorer
from src.rag_learn import learn_from_evidence, learn_negatives_from_evidence
from src.rag_retriever import RAGRetriever
from src.rag_store import (
    DocChunk,
    GoldenPattern,
    KnowledgeEntry,
    LearnedPattern,
    RAGStore,
    RetrievedPattern,
    SearchHit,
)
from src.rag_switches import (
    PART_ENTRY_TYPES,
    PART_GOLDEN,
    PART_LEARNED,
    PART_SWITCH_ENV,
    RAGSwitchError,
    disabled_entry_types,
    part_enabled,
    validate_rag_switches,
)

SITE = "abc123"


# ---------------------------------------------------------------------------
# Minimal fake backend + embedder (same shape as tests/test_rag_retriever.py)
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
        return [v / norm for v in vec] if norm else vec


class _InMemoryBackend:
    def __init__(self, dimension: int) -> None:
        self._dimension = dimension
        self._entries: list[tuple[list[float], dict[str, Any], str]] = []

    @property
    def dimension(self) -> int:
        return self._dimension

    def upsert(self, entries: list[KnowledgeEntry]) -> int:
        for entry in entries:
            self._entries.append((entry.vector, entry.metadata, entry.text))
        return len(entries)

    def search(self, query_vector: list[float], k: int) -> list[SearchHit]:
        scored = [
            (sum(x * y for x, y in zip(query_vector, vec, strict=True)), meta) for vec, meta, _text in self._entries
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [SearchHit(distance=score, metadata=meta) for score, meta in scored[:k]]

    def count(self) -> int:
        return len(self._entries)

    def counts_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _vec, meta, _text in self._entries:
            key = str(meta.get("entry_type", "unknown"))
            counts[key] = counts.get(key, 0) + 1
        return counts

    def delete_learned(self) -> int:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e[1].get("entry_type") in ("golden", "doc")]
        return before - len(self._entries)

    def query_dedup_keys(self, entry_type: str) -> list[str]:
        return [str(m.get("dedup_key", "")) for _v, m, _t in self._entries if m.get("entry_type") == entry_type]

    def clear(self) -> None:
        self._entries.clear()

    def find_learned(self, action_type: str, description: str, site_hash: str) -> dict[str, object] | None:
        return self._find("learned", action_type, description, site_hash)

    def find_negative(self, action_type: str, description: str, site_hash: str) -> dict[str, object] | None:
        return self._find("learned_negative", action_type, description, site_hash)

    def _find(self, entry_type: str, action_type: str, description: str, site_hash: str) -> dict[str, object] | None:
        for _vec, meta, _text in self._entries:
            if (
                meta.get("entry_type") == entry_type
                and meta.get("action_type") == action_type
                and meta.get("description") == description
                and meta.get("site_hash") == site_hash
            ):
                return dict(meta)
        return None

    def increment_learned_hit(self, row: dict[str, object]) -> int:
        for _vec, meta, _text in self._entries:
            if (
                meta.get("action_type") == row.get("action_type")
                and meta.get("description") == row.get("description")
                and meta.get("site_hash") == row.get("site_hash")
            ):
                new_hit = int(meta.get("hit_count", 0)) + 1
                meta["hit_count"] = new_hit
                return new_hit
        return 0


def _store() -> RAGStore:
    return RAGStore(_InMemoryBackend(16), _FakeEmbedder())


def _golden(description: str = "Add to cart button") -> GoldenPattern:
    return GoldenPattern(
        action="CLICK",
        description=description,
        expected_locator="button.add-to-cart",
        expected_page="",
        site_hash=SITE,
    )


def _learned(description: str = "Add to cart button", source: str = "evidence") -> LearnedPattern:
    return LearnedPattern(
        action_type="CLICK",
        description=description,
        locator="button.add-to-cart",
        site_hash=SITE,
        confidence=1.0,
        source=source,
    )


def _retrieved(source: str, selector: str = "button.add-to-cart") -> RetrievedPattern:
    return RetrievedPattern(
        description="CLICK: Add to cart button",
        selector=selector,
        action_type="CLICK",
        confidence=1.0,
        source=source,
        site_hash=SITE,
        hit_count=1,
    )


_ELEMENT = {"selector": "button.add-to-cart", "text": "Add to cart", "tag": "button"}

#: Every switch, so a test can clear all four first.
_ALL_SWITCHES = tuple(PART_SWITCH_ENV.values())


@pytest.fixture(autouse=True)
def _default_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from the defaults: every part switch unset (= on)."""
    for env_var in _ALL_SWITCHES:
        monkeypatch.delenv(env_var, raising=False)


# ---------------------------------------------------------------------------
# The switch itself: defaults, values, refusal
# ---------------------------------------------------------------------------


class TestSwitchValues:
    def test_unset_is_on(self) -> None:
        assert validate_rag_switches() == dict.fromkeys(PART_ENTRY_TYPES, True)

    @pytest.mark.parametrize("raw", ["", "1"])
    def test_blank_and_one_are_on(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("RAG_GOLDEN", raw)
        assert part_enabled(PART_GOLDEN) is True

    def test_zero_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_GOLDEN", "0")
        assert part_enabled(PART_GOLDEN) is False

    @pytest.mark.parametrize("raw", ["yes", "true", "off", "no", "maybe", "2", "-1"])
    def test_unknown_value_is_refused(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("RAG_LEARNED", raw)
        with pytest.raises(RAGSwitchError) as excinfo:
            part_enabled(PART_LEARNED)
        assert "RAG_LEARNED" in str(excinfo.value)
        assert "1 (on" in str(excinfo.value)

    def test_validate_refuses_any_bad_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_NEGATIVES", "on")
        with pytest.raises(RAGSwitchError):
            validate_rag_switches()

    def test_unknown_part_is_a_key_error(self) -> None:
        with pytest.raises(KeyError):
            part_enabled("embeddings")

    def test_disabled_entry_types_reports_the_off_parts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert disabled_entry_types() == frozenset()
        monkeypatch.setenv("RAG_DOC_CHUNKS", "0")
        monkeypatch.setenv("RAG_NEGATIVES", "0")
        assert disabled_entry_types() == frozenset({"doc", "learned_negative"})

    def test_a_bad_value_is_refused_at_the_write_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        monkeypatch.setenv("RAG_GOLDEN", "yes")
        with pytest.raises(RAGSwitchError):
            store.add_patterns([_golden()])
        assert store.counts_by_type() == {}

    def test_a_bad_value_is_refused_at_the_score_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_GOLDEN", "yes")
        with pytest.raises(RAGSwitchError):
            PlaceholderScorer._golden_pattern_bonus(_ELEMENT, [_retrieved("golden")], SITE)


# ---------------------------------------------------------------------------
# Golden pack: RAG_GOLDEN
# ---------------------------------------------------------------------------


class TestGoldenPart:
    def test_default_writes_reads_and_scores(self) -> None:
        store = _store()
        assert store.add_patterns([_golden()]) == 1
        assert store.counts_by_type() == {"golden": 1}
        patterns = store.retrieve("CLICK: Add to cart button", action_type="CLICK")
        assert [p.source for p in patterns] == ["golden"]
        assert PlaceholderScorer._golden_pattern_bonus(_ELEMENT, patterns, SITE) == int(
            PlaceholderScorer.GOLDEN_PATTERN_BONUS * patterns[0].confidence
        )

    def test_off_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        monkeypatch.setenv("RAG_GOLDEN", "0")
        assert store.add_patterns([_golden()]) == 0
        assert store.counts_by_type() == {}
        assert store.retrieve("CLICK: Add to cart button", action_type="CLICK") == []

    def test_off_is_not_read_from_an_existing_store(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        store.add_patterns([_golden()])
        monkeypatch.setenv("RAG_GOLDEN", "0")
        assert store.retrieve("CLICK: Add to cart button", action_type="CLICK") == []

    def test_off_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        patterns = [_retrieved("golden")]
        assert PlaceholderScorer._golden_pattern_bonus(_ELEMENT, patterns, SITE) > 0
        monkeypatch.setenv("RAG_GOLDEN", "0")
        assert PlaceholderScorer._golden_pattern_bonus(_ELEMENT, patterns, SITE) == 0

    def test_off_is_not_reported_by_pattern_usage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        retriever = RAGRetriever(_store())
        patterns = [_retrieved("golden")]
        assert retriever.scoring_bonus_for(_ELEMENT, patterns, SITE) > 0
        monkeypatch.setenv("RAG_GOLDEN", "0")
        assert retriever.scoring_bonus_for(_ELEMENT, patterns, SITE) == 0
        assert retriever.pattern_usage(patterns, SITE, _ELEMENT["selector"]) == []


# ---------------------------------------------------------------------------
# Doc chunks: RAG_DOC_CHUNKS
# ---------------------------------------------------------------------------


class TestDocChunkPart:
    def test_default_writes_and_reads(self) -> None:
        store = _store()
        assert store.add_docs([DocChunk(text="Playwright locators", dedup_key="k1")]) == (1, 0)
        assert store.counts_by_type() == {"doc": 1}
        assert [p.source for p in store.retrieve("Playwright locators")] == ["doc"]

    def test_off_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        monkeypatch.setenv("RAG_DOC_CHUNKS", "0")
        assert store.add_docs([DocChunk(text="Playwright locators", dedup_key="k1")]) == (0, 0)
        assert store.counts_by_type() == {}

    def test_off_is_not_read_from_an_existing_store(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        store.add_docs([DocChunk(text="Playwright locators", dedup_key="k1")])
        monkeypatch.setenv("RAG_DOC_CHUNKS", "0")
        assert store.retrieve("Playwright locators") == []

    def test_docs_earn_no_bonus_either_way(self) -> None:
        # The docs are still discarded at scoring (a separate decision): the
        # switch changes retrieval, not the scoring rule.
        assert PlaceholderScorer._golden_pattern_bonus(_ELEMENT, [_retrieved("doc")], SITE) == 0
        assert PlaceholderScorer._learned_pattern_bonus(_ELEMENT, [_retrieved("doc")], SITE) == 0


# ---------------------------------------------------------------------------
# Learned positives: RAG_LEARNED
# ---------------------------------------------------------------------------


class TestLearnedPart:
    def test_default_writes_reads_and_scores(self) -> None:
        store = _store()
        assert store.upsert_pattern(_learned()) == ("inserted", 1)
        assert store.counts_by_type() == {"learned": 1}
        patterns = store.retrieve("CLICK: Add to cart button", action_type="CLICK")
        assert [p.source for p in patterns] == ["learned"]
        assert PlaceholderScorer._learned_pattern_bonus(_ELEMENT, patterns, SITE) == int(
            PlaceholderScorer.SAME_SITE_LEARNED_BONUS * patterns[0].confidence
        )

    def test_off_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        monkeypatch.setenv("RAG_LEARNED", "0")
        assert store.upsert_pattern(_learned()) == ("disabled", 0)
        assert store.counts_by_type() == {}

    def test_off_is_not_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        store.upsert_pattern(_learned())
        monkeypatch.setenv("RAG_LEARNED", "0")
        assert store.retrieve("CLICK: Add to cart button", action_type="CLICK") == []

    def test_off_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        patterns = [_retrieved("learned")]
        assert PlaceholderScorer._learned_pattern_bonus(_ELEMENT, patterns, SITE) > 0
        monkeypatch.setenv("RAG_LEARNED", "0")
        assert PlaceholderScorer._learned_pattern_bonus(_ELEMENT, patterns, SITE) == 0
        assert (
            PlaceholderScorer._learned_net_evidence(
                _ELEMENT, patterns, SITE, action="CLICK", description="Add to cart button"
            )
            == 0
        )

    def test_off_learn_from_evidence_does_no_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        steps = [
            {
                "type": "click",
                "label": "Add to cart button",
                "locator": "button.add-to-cart",
                "url": "https://shop.test/cart",
                "result": {"status": "passed"},
            }
        ]
        monkeypatch.setenv("RAG_LEARNED", "0")
        assert learn_from_evidence(steps, store=store) == {"inserted": 0, "exists": 0}
        assert store.counts_by_type() == {}
        # Sanity: the same input does learn with the default.
        monkeypatch.delenv("RAG_LEARNED")
        assert learn_from_evidence(steps, store=store)["inserted"] == 1


# ---------------------------------------------------------------------------
# Contrastive negatives: RAG_NEGATIVES
# ---------------------------------------------------------------------------


class TestNegativePart:
    def test_default_writes_and_penalises(self) -> None:
        store = _store()
        assert store.upsert_negative_pattern(_learned(source="learned_negative")) == ("inserted", 1)
        assert store.counts_by_type() == {"learned_negative": 1}
        patterns = store.retrieve("CLICK: Add to cart button", action_type="CLICK")
        assert [p.source for p in patterns] == ["learned_negative"]
        penalty = PlaceholderScorer._learned_negative_penalty(
            _ELEMENT, patterns, SITE, action="CLICK", description="Add to cart button"
        )
        assert penalty == int(PlaceholderScorer.LEARNED_NEGATIVE_BONUS * patterns[0].confidence)

    def test_off_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        monkeypatch.setenv("RAG_NEGATIVES", "0")
        assert store.upsert_negative_pattern(_learned(source="learned_negative")) == ("disabled", 0)
        assert store.counts_by_type() == {}

    def test_off_is_not_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        store.upsert_negative_pattern(_learned(source="learned_negative"))
        monkeypatch.setenv("RAG_NEGATIVES", "0")
        assert store.retrieve("CLICK: Add to cart button", action_type="CLICK") == []

    def test_off_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        patterns = [_retrieved("learned_negative")]
        assert (
            PlaceholderScorer._learned_negative_penalty(
                _ELEMENT, patterns, SITE, action="CLICK", description="Add to cart button"
            )
            > 0
        )
        monkeypatch.setenv("RAG_NEGATIVES", "0")
        assert (
            PlaceholderScorer._learned_negative_penalty(
                _ELEMENT, patterns, SITE, action="CLICK", description="Add to cart button"
            )
            == 0
        )
        assert (
            PlaceholderScorer._learned_net_evidence(
                _ELEMENT, patterns, SITE, action="CLICK", description="Add to cart button"
            )
            == 0
        )

    def test_off_learn_negatives_does_no_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        steps = [
            {
                "type": "click",
                "label": "Add to cart button",
                "locator": "button.add-to-cart",
                "url": "https://shop.test/cart",
                "result": {"status": "failed", "error": "element not found"},
            }
        ]
        monkeypatch.setenv("RAG_NEGATIVES", "0")
        assert learn_negatives_from_evidence(steps, store=store) == {"inserted": 0, "exists": 0}
        assert store.counts_by_type() == {}


# ---------------------------------------------------------------------------
# Defaults change nothing, and the parts are independent
# ---------------------------------------------------------------------------


class TestDefaultsChangeNothing:
    def test_every_default_score_matches_the_documented_constant(self) -> None:
        """Golden +20, learned +5, negative -5 at full confidence - unchanged."""
        golden = [_retrieved("golden")]
        learned = [_retrieved("learned")]
        negative = [_retrieved("learned_negative")]
        for pattern in (golden[0], learned[0], negative[0]):
            pattern.confidence = 1.0
        assert PlaceholderScorer._golden_pattern_bonus(_ELEMENT, golden, SITE) == PlaceholderScorer.GOLDEN_PATTERN_BONUS
        assert (
            PlaceholderScorer._learned_pattern_bonus(_ELEMENT, learned, SITE)
            == PlaceholderScorer.SAME_SITE_LEARNED_BONUS
        )
        assert (
            PlaceholderScorer._learned_negative_penalty(
                _ELEMENT, negative, SITE, action="CLICK", description="Add to cart button"
            )
            == PlaceholderScorer.LEARNED_NEGATIVE_BONUS
        )

    def test_unset_and_explicit_one_are_identical(self, monkeypatch: pytest.MonkeyPatch) -> None:
        patterns = [_retrieved("golden"), _retrieved("learned")]
        unset = PlaceholderScorer._golden_pattern_bonus(_ELEMENT, patterns, SITE)
        for env_var in _ALL_SWITCHES:
            monkeypatch.setenv(env_var, "1")
        assert PlaceholderScorer._golden_pattern_bonus(_ELEMENT, patterns, SITE) == unset

    def test_one_part_off_leaves_the_others_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _store()
        store.add_patterns([_golden()])
        store.upsert_pattern(_learned())
        monkeypatch.setenv("RAG_LEARNED", "0")
        sources = [p.source for p in store.retrieve("CLICK: Add to cart button", action_type="CLICK")]
        assert sources == ["golden"]

    def test_part_switches_do_not_replace_the_global_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RAG_ENABLED=0 is unchanged: the store still accepts writes today.

        The global gate decides whether a retriever is built; the four part
        switches sit inside it and must not change that existing path.
        """
        store = _store()
        monkeypatch.setenv("RAG_ENABLED", "0")
        assert store.add_patterns([_golden()]) == 1
        assert store.counts_by_type() == {"golden": 1}
