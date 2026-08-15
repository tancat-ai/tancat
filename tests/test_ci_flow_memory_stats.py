"""Tests for action/flow_memory_stats.py (spec §3 goal 13, learn: true).

The entrypoint consumes this helper after a green generate-and-run with
learn: true — it must never fail a green run on learning bookkeeping, so a
missing or corrupt store reads as zeros with exit 0.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from action.flow_memory_stats import flow_memory_stats as stats_of
from src.flow_memory import FlowTransition


def _seeded_store(tmp_path: Path) -> Path:
    """Write a store with 3 patterns across 2 sites and return its path."""
    from src.flow_memory import FlowMemoryStore
    from src.rag_learn import site_hash

    store = FlowMemoryStore(tmp_path / "flow_memory.json")
    store.upsert_flow(
        FlowTransition("home", "CLICK", "products link", "products"),
        site_hash("staging.example.com"),
    )
    store.upsert_flow(
        FlowTransition("home", "CLICK", "products link", "products"),
        site_hash("staging2.example.com"),
    )  # same key on a 2nd site -> cross-site pattern
    store.upsert_flow(
        FlowTransition("cart", "CLICK", "proceed to checkout", "checkout"),
        site_hash("staging.example.com"),
    )
    store.upsert_flow(
        FlowTransition("products", "GOTO", "cart", "cart"),
        site_hash("staging2.example.com"),
        source="suite_chain",
    )
    store.save()
    return tmp_path / "flow_memory.json"


# ---------------------------------------------------------------------------
# Helper unit tests (importable API)
# ---------------------------------------------------------------------------


class TestFlowMemoryStats:
    def test_missing_store_reads_zeros(self, tmp_path: Path) -> None:
        stats = stats_of(tmp_path / "nope" / "flow_memory.json")
        assert stats["patterns"] == 0
        assert stats["sites"] == 0
        assert stats["corrupt"] is False

    def test_populated_store_reports_counts(self, tmp_path: Path) -> None:
        stats = stats_of(_seeded_store(tmp_path))
        assert stats["patterns"] == 3
        assert stats["sites"] == 2
        assert stats["cross_site"] == 1
        assert stats["suite_chains"] == 1
        assert stats["within_test"] == 2
        assert stats["corrupt"] is False
        assert "last_learned_at" in stats

    def test_corrupt_store_reads_zeros_with_flag(self, tmp_path: Path) -> None:
        path = tmp_path / "flow_memory.json"
        path.write_text("{ not json", encoding="utf-8")
        stats = stats_of(path)
        assert stats["patterns"] == 0
        assert stats["corrupt"] is True

    def test_path_reported_as_given(self, tmp_path: Path) -> None:
        path = tmp_path / "flow_memory.json"
        assert stats_of(path)["path"] == str(path)


# ---------------------------------------------------------------------------
# CLI contract (the entrypoint's invocation)
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "action.flow_memory_stats", *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestFlowMemoryStatsCLI:
    def test_missing_store_json_zeros_exit_0(self, tmp_path: Path) -> None:
        proc = _run_cli("--store", str(tmp_path / "missing.json"), "--json")
        assert proc.returncode == 0, proc.stderr
        stats = json.loads(proc.stdout.strip())
        assert stats["patterns"] == 0
        assert stats["sites"] == 0

    def test_populated_store_json_shape(self, tmp_path: Path) -> None:
        store_path = _seeded_store(tmp_path)
        proc = _run_cli("--store", str(store_path), "--json")
        assert proc.returncode == 0, proc.stderr
        stats = json.loads(proc.stdout.strip())
        assert stats["patterns"] == 3
        assert stats["path"] == str(store_path)

    def test_plain_mode_human_line(self, tmp_path: Path) -> None:
        proc = _run_cli("--store", str(tmp_path / "missing.json"))
        assert proc.returncode == 0
        assert "patterns" in proc.stdout
