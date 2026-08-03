"""Unit tests for ``src/rag_bundled.py`` (B-036 Phase 2 bundled pack + auto-seed)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.rag_bundled import (
    BUNDLED_PACK_VERSION,
    build_bundled_docs,
    build_bundled_patterns,
    bundled_marker_path,
    ensure_bundled_seeded,
    prune_learned,
    store_stats,
)


class TestBuildBundledPack:
    """The shipped golden pack must load from the repo's own data."""

    def test_bundled_patterns_nonempty_and_wellformed(self) -> None:
        patterns = build_bundled_patterns()
        assert len(patterns) > 0
        for p in patterns:
            assert p.action
            assert p.description
            assert p.expected_locator

    def test_bundled_patterns_cover_all_sites(self) -> None:
        pages = {p.expected_page for p in build_bundled_patterns()}
        assert any("saucedemo" in pg for pg in pages)
        assert any("automationexercise" in pg for pg in pages)
        assert any("demoqa" in pg for pg in pages)
        assert any("the-internet" in pg for pg in pages)
        assert any("localhost:8781" in pg for pg in pages)  # mock sites

    def test_bundled_docs_nonempty_and_wellformed(self) -> None:
        chunks = build_bundled_docs()
        assert len(chunks) > 0
        for c in chunks:
            assert c.text
            assert c.source
            assert c.heading_path


class TestBundledMarkerPath:
    def test_marker_lives_in_evidence_dir(self, tmp_path: Path) -> None:
        class _FakeStorage:
            def evidence_dir(self) -> Path:
                return tmp_path / "evidence"

        marker = bundled_marker_path(_FakeStorage())  # type: ignore[arg-type]
        assert marker.name == ".rag_bundled_seeded.json"
        assert marker.parent == tmp_path / "evidence"


class TestEnsureBundledSeeded:
    def test_skips_when_marker_exists(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        marker.write_text(json.dumps({"version": 1}))
        store = MagicMock()
        result = ensure_bundled_seeded(store=store, marker_path=marker)
        assert result["status"] == "skipped"
        store.add_patterns.assert_not_called()
        store.add_docs.assert_not_called()

    def test_seeds_empty_store_and_writes_marker(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = True
        store.add_patterns.return_value = 67
        store.add_docs.return_value = 27
        result = ensure_bundled_seeded(store=store, marker_path=marker)
        assert result["status"] == "seeded"
        assert result["golden"] == 67
        assert result["docs"] == 27
        store.add_patterns.assert_called_once()
        store.add_docs.assert_called_once()
        assert marker.exists()

    def test_marks_nonempty_store_without_adding(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = False
        result = ensure_bundled_seeded(store=store, marker_path=marker)
        assert result["status"] == "marked"
        store.add_patterns.assert_not_called()
        store.add_docs.assert_not_called()
        assert marker.exists()

    def test_force_reseeds_despite_marker(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        marker.write_text(json.dumps({"version": 1}))
        store = MagicMock()
        store.is_empty = True
        result = ensure_bundled_seeded(store=store, marker_path=marker, force=True)
        assert result["status"] == "seeded"
        store.add_patterns.assert_called_once()

    def test_force_readds_to_populated_store(self, tmp_path: Path) -> None:
        """--force re-adds the pack even when the store already has entries."""
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = False
        store.add_patterns.return_value = 67
        store.add_docs.return_value = 27
        result = ensure_bundled_seeded(store=store, marker_path=marker, force=True)
        assert result["status"] == "seeded"
        store.add_patterns.assert_called_once()
        store.add_docs.assert_called_once()

    def test_marker_records_pack_version(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = True
        ensure_bundled_seeded(store=store, marker_path=marker)
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["version"] == BUNDLED_PACK_VERSION

    def test_failure_propagates_for_caller_to_handle(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = True
        store.add_patterns.side_effect = RuntimeError("embedder download failed")
        with pytest.raises(RuntimeError):
            ensure_bundled_seeded(store=store, marker_path=marker)
        assert not marker.exists()  # retry on the next run


class TestStoreStatsAndPrune:
    def test_store_stats_adds_total(self) -> None:
        store = MagicMock()
        store.counts_by_type.return_value = {"golden": 67, "doc": 27}
        assert store_stats(store) == {"golden": 67, "doc": 27, "total": 94}

    def test_prune_learned_delegates(self) -> None:
        store = MagicMock()
        store.delete_learned.return_value = 3
        assert prune_learned(store) == 3
        store.delete_learned.assert_called_once()
