"""AI-059 controlled baseline runner tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from src.learning_impact import (
    BaselineLeg,
    ControlledBaselineRunner,
    lab_site_hash,
    measurement_environment,
    rebuild_warm_store_from_evidence,
    restore_store_snapshot,
)
from src.rag_store import RAGStore, VectorStoreBackend


def test_rag_diagnostics_are_opt_in_and_jsonl(tmp_path: Path, monkeypatch: Any) -> None:
    # Keep this test independent of a live RAG backend: it exercises the
    # diagnostic serialization seam directly.
    from src.placeholder_orchestrator import PlaceholderOrchestrator
    from src.rag_store import RetrievedPattern

    path = tmp_path / "rag.jsonl"
    monkeypatch.setenv("AI059_RAG_DIAGNOSTICS_PATH", str(path))
    PlaceholderOrchestrator._write_rag_diagnostic(
        "CLICK",
        "Add to cart",
        [RetrievedPattern("Add to cart", "#add", "CLICK", 0.9, source="learned")],
    )
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["action"] == "CLICK"
    assert row["results"][0]["selector"] == "#add"


def test_restore_store_snapshot_supports_files_and_empty_store(tmp_path: Path) -> None:
    snapshot = tmp_path / "golden.json"
    target = tmp_path / "active.json"
    snapshot.write_text("golden", encoding="utf-8")
    snapshot.with_name(snapshot.name + ".embedder.json").write_text("stamp", encoding="utf-8")
    target.write_text("stale", encoding="utf-8")
    restore_store_snapshot(snapshot, target)
    assert target.read_text(encoding="utf-8") == "golden"
    assert target.with_name(target.name + ".embedder.json").read_text(encoding="utf-8") == "stamp"
    restore_store_snapshot(None, target)
    assert not target.exists()
    assert not target.with_name(target.name + ".embedder.json").exists()


def test_measurement_environment_disables_learning_without_disabling_rag() -> None:
    env = measurement_environment({"RAG_ENABLED": "1"})
    assert env["AI059_DISABLE_AUTO_LEARN"] == "1"
    assert env["RAG_AUTO_LEARN"] == "0"
    assert env["FLOW_MEMORY_AUTO_LEARN"] == "0"
    assert env["RAG_ENABLED"] == "1"


def test_runner_restores_store_and_persists_metrics_per_leg(tmp_path: Path) -> None:
    snapshot = tmp_path / "golden.json"
    target = tmp_path / "active.json"
    snapshot.write_text("golden", encoding="utf-8")
    # The child emits one passing sidecar into the runner-provided directory.
    child = (
        "import json, os, pathlib; "
        "p=pathlib.Path(os.environ['AI059_EVIDENCE_DIR']); p.mkdir(parents=True, exist_ok=True); "
        "(p/'test.evidence.json').write_text(json.dumps({'test': {'name': os.environ['AI059_LEG'], 'status': 'passed'}, 'steps': [{'result': {'status': 'passed'}}]}))"
    )
    runner = ControlledBaselineRunner(
        evidence_root=tmp_path / "evidence",
        output_root=tmp_path / "output",
        store_target=target,
        base_env={"PATH": "", "RAG_ENABLED": "1"},
        timeout_s=20,
    )
    report = runner.run([sys.executable, "-c", child], [BaselineLeg("cold", snapshot), BaselineLeg("warm", snapshot)])
    assert [leg.name for leg in report.legs] == ["cold", "warm"]
    assert all(leg.succeeded for leg in report.legs)
    assert all(leg.metrics.first_pass_green_rate == 1.0 for leg in report.legs)
    assert (tmp_path / "output" / "cold" / "metrics.json").exists()
    assert (tmp_path / "output" / "warm" / "metrics.json").exists()
    persisted = json.loads((tmp_path / "output" / "baseline_report.json").read_text(encoding="utf-8"))
    assert persisted["legs"]
    assert persisted["metadata"]["harness"] == "AI-059"
    assert persisted["legs"][0]["store_snapshot_sha256"]
    assert target.read_text(encoding="utf-8") == "golden"


def test_rebuild_warm_store_from_evidence_tags_sentinel(tmp_path: Path) -> None:
    (tmp_path / "pass.evidence.json").write_text(
        json.dumps(
            {
                "test": {"name": "pass", "status": "passed"},
                "steps": [
                    {"type": "click", "label": "Add to cart", "locator": "#add", "result": {"status": "passed"}},
                    {"type": "fill", "label": "Email", "locator": "#email", "result": {"status": "passed"}},
                    {"type": "click", "label": "Skip", "locator": "#skip", "result": {"status": "failed"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "fail.evidence.json").write_text(
        json.dumps(
            {
                "test": {"name": "fail", "status": "failed"},
                "steps": [{"type": "click", "label": "Z", "locator": "#z", "result": {"status": "passed"}}],
            }
        ),
        encoding="utf-8",
    )
    fake = _FakeBackend()
    store = RAGStore(fake, _FakeEmbedder())
    result = rebuild_warm_store_from_evidence(tmp_path, store=store, lab_site_identity="ai059-lab:ecommerce")
    assert result == {"inserted": 2, "exists": 0, "skipped": 0}
    sentinel = lab_site_hash("ai059-lab:ecommerce")
    md = {entry.metadata["description"]: entry.metadata for entry in fake.entries}
    assert set(md) == {"Add to cart", "Email"}
    assert md["Add to cart"]["action_type"] == "CLICK"
    assert md["Email"]["action_type"] == "FILL"
    assert md["Add to cart"]["site_hash"] == sentinel


def test_lab_site_hash_is_deterministic_and_distinct_from_localhost() -> None:
    assert lab_site_hash("ai059-lab:ecommerce") == lab_site_hash("ai059-lab:ecommerce")
    from src.rag_learn import site_hash as url_site_hash

    assert lab_site_hash("ai059-lab:ecommerce") != url_site_hash("localhost:8781")


def test_build_lab_identity_isolates_experiment_cells() -> None:
    from src.learning_impact import build_lab_identity

    v1 = build_lab_identity(site="ecommerce", input_version="v1")
    v2 = build_lab_identity(site="ecommerce", input_version="v2")
    other_site = build_lab_identity(site="banking", input_version="v1")
    # Editing a site/input changes the scope -> no bleed between versions.
    assert lab_site_hash(v1) != lab_site_hash(v2)
    # Different sites stay isolated even at the same version.
    assert lab_site_hash(v1) != lab_site_hash(other_site)
    # The same cell reproduces across reruns.
    assert build_lab_identity(site="ecommerce", input_version="v1") == v1
    assert lab_site_hash(v1) == lab_site_hash(build_lab_identity(site="ecommerce", input_version="v1"))


class _FakeEmbedder:
    dimension = 384

    @property
    def identity(self) -> str:
        return "fake@384"

    def embed(self, text: str) -> list[float]:
        return [0.0] * self.dimension

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dimension for _ in texts]


class _FakeBackend(VectorStoreBackend):
    def __init__(self) -> None:
        self.entries: list = []

    @property
    def dimension(self) -> int:
        return 384

    def upsert(self, entries: list) -> int:
        self.entries.extend(entries)
        return len(entries)

    def find_learned(self, action_type: str, description: str, site_hash: str) -> dict[str, Any] | None:
        for entry in self.entries:
            md = entry.metadata
            if (
                md.get("entry_type") == "learned"
                and md.get("action_type") == action_type
                and md.get("description") == description
                and md.get("site_hash") == site_hash
            ):
                return md
        return None

    def increment_learned_hit(self, row: dict) -> int:
        return 1

    def search(self, query_vector: list[float], k: int) -> list:
        return []

    def count(self) -> int:
        return len(self.entries)

    def clear(self) -> None:
        self.entries.clear()

    def counts_by_type(self) -> dict[str, int]:
        return {}

    def query_dedup_keys(self, entry_type: str) -> list[str]:
        return []

    def delete_learned(self) -> int:
        return 0

    def verify_embedder(self, embedder_identity: str | None) -> None:
        return None
