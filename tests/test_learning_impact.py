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


def test_rag_usage_diagnostic_records_decisive_and_counterfactual(tmp_path: Path, monkeypatch: Any) -> None:
    # AI-059 effect trace: the usage line must also carry whether the RAG
    # bonus actually DECIDED the winner (decisive) and what a no-RAG
    # re-resolution would have picked (counterfactual_selector).
    from src.placeholder_orchestrator import PlaceholderOrchestrator

    path = tmp_path / "rag.jsonl"
    monkeypatch.setenv("AI059_RAG_DIAGNOSTICS_PATH", str(path))
    usage = [
        {
            "description": "Add to cart",
            "source": "learned",
            "site_hash": "s",
            "eligible": True,
            "matched": True,
            "bonus": 5,
        }
    ]
    PlaceholderOrchestrator._write_rag_usage_diagnostic(
        "CLICK",
        "Add to cart",
        usage,
        decisive=True,
        counterfactual_selector="#other",
    )
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["decisive"] is True
    assert row["counterfactual_selector"] == "#other"
    assert row["usage"][0]["bonus"] == 5
    # When no counterfactual was computed, the fields serialize as null.
    PlaceholderOrchestrator._write_rag_usage_diagnostic("FILL", "Email", usage)
    row2 = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row2["decisive"] is None
    assert row2["counterfactual_selector"] is None


def test_effective_site_identity_honors_opt_in_scope(monkeypatch: Any) -> None:
    # AI-061: an opt-in AITEST_RAG_SCOPE key must participate in the RAG site
    # identity so two projects on the same host:port stay isolated, while an
    # unset scope preserves the legacy host[:port] behavior (B-047).
    from src.rag_learn import effective_site_identity, site_hash

    monkeypatch.delenv("AITEST_RAG_SCOPE", raising=False)
    assert effective_site_identity("http://localhost:8781/x.html") == "localhost:8781"

    monkeypatch.setenv("AITEST_RAG_SCOPE", "proj-a")
    # Scope overrides host:port and is namespaced so it can't collide with a
    # real domain string that happens to equal the scope value.
    assert effective_site_identity("http://localhost:8781/x.html") == "scope:proj-a"
    assert site_hash("scope:proj-a") != site_hash("localhost:8781")


def test_learn_scopes_by_opt_in_scope_not_host_port(monkeypatch: Any) -> None:
    # AI-061: a learned pattern written under a scope key must be tagged with
    # the scope identity, not the host:port hash — proving two projects on the
    # same port no longer bleed into each other.
    from src.rag_learn import _step_to_pattern, site_hash

    step = {
        "type": "click",
        "label": "Add to cart",
        "locator": "#add",
        "url": "http://localhost:8781/generated_tests/mock.html",
        "result": {"status": "passed"},
    }
    monkeypatch.delenv("AITEST_RAG_SCOPE", raising=False)
    base = _step_to_pattern(step)
    assert base is not None
    assert base.site_hash == site_hash("localhost:8781")

    monkeypatch.setenv("AITEST_RAG_SCOPE", "proj-a")
    scoped = _step_to_pattern(step)
    assert scoped is not None
    assert scoped.site_hash == site_hash("scope:proj-a")
    assert scoped.site_hash != base.site_hash


def test_scope_key_isolates_learned_patterns_between_projects(monkeypatch: Any) -> None:
    # End-to-end-at-unit-level: a learned pattern scoped to one project is
    # eligible + applied only when the resolver runs under the SAME scope.
    from src.rag_learn import effective_site_identity, site_hash
    from src.rag_retriever import RAGRetriever
    from src.rag_store import RetrievedPattern

    url = "http://localhost:8781/generated_tests/mock.html"
    monkeypatch.setenv("AITEST_RAG_SCOPE", "proj-a")
    site_a = site_hash(effective_site_identity(url))
    learned_a = RetrievedPattern("Email", "#email", "FILL", 1.0, source="learned", site_hash=site_a)

    retriever = RAGRetriever(store=None)
    usage = retriever.pattern_usage([learned_a], site_a, "#email")
    assert usage[0]["eligible"] is True
    assert usage[0]["matched"] is True
    assert usage[0]["bonus"] == 5

    # A different scope → different site identity → the pattern is NOT eligible.
    monkeypatch.setenv("AITEST_RAG_SCOPE", "proj-b")
    site_b = site_hash(effective_site_identity(url))
    assert site_b != site_a
    usage_b = retriever.pattern_usage([learned_a], site_b, "#email")
    assert usage_b[0]["eligible"] is False
    assert usage_b[0]["bonus"] == 0


def test_pattern_usage_reports_eligible_match_and_bonus() -> None:
    # Exercises the Deliverable-2 usage tracer directly: for each retrieved
    # pattern it must report eligibility (site gate), whether it matched the
    # winner, and the bonus contributed — including legacy (empty site_hash)
    # goldens, same-site learned, and cross-site non-matches.
    from src.rag_retriever import RAGRetriever
    from src.rag_store import RetrievedPattern

    site = "site-abc"
    cross = "other-site"
    golden_same = RetrievedPattern("Add to cart", "#add", "CLICK", 0.9, source="golden", site_hash=site)
    golden_cross = RetrievedPattern("Add to cart", "#add", "CLICK", 0.9, source="golden", site_hash=cross)
    golden_legacy = RetrievedPattern("Add to cart", "#add", "CLICK", 0.9, source="golden")
    learned_same = RetrievedPattern("Email", "#email", "FILL", 1.0, source="learned", site_hash=site)
    learned_cross = RetrievedPattern("Email", "#email", "FILL", 1.0, source="learned", site_hash=cross)

    retriever = RAGRetriever(store=None)

    # Same-site golden: eligible + direct match → GOLDEN_PATTERN_BONUS * conf.
    usage = retriever.pattern_usage([golden_same], site, "#add")
    assert usage[0]["eligible"] is True
    assert usage[0]["matched"] is True
    assert usage[0]["bonus"] == 18  # 20 * 0.9

    # Same-site learned: eligible + direct match → SAME_SITE_LEARNED_BONUS * conf.
    usage = retriever.pattern_usage([learned_same], site, "#email")
    assert usage[0]["eligible"] is True
    assert usage[0]["matched"] is True
    assert usage[0]["bonus"] == 5  # 5 * 1.0

    # Cross-site golden: not eligible on this site.
    usage = retriever.pattern_usage([golden_cross], site, "#add")
    assert usage[0]["eligible"] is False
    assert usage[0]["matched"] is False
    assert usage[0]["bonus"] == 0

    # Legacy golden (empty site_hash): site-agnostic → eligible everywhere.
    usage = retriever.pattern_usage([golden_legacy], site, "#add")
    assert usage[0]["eligible"] is True
    assert usage[0]["matched"] is True
    assert usage[0]["bonus"] == 18

    # Cross-site learned: not eligible.
    usage = retriever.pattern_usage([learned_cross], site, "#email")
    assert usage[0]["eligible"] is False
    assert usage[0]["bonus"] == 0

    # Substring match scales the bonus by 0.5 * confidence.
    usage = retriever.pattern_usage([golden_same], site, "div #add span")
    assert usage[0]["eligible"] is True
    assert usage[0]["matched"] is True
    assert usage[0]["bonus"] == 9  # 20 * 0.5 * 0.9

    # scoring_bonus_for delegates to pattern_usage and returns the first bonus.
    bonus = retriever.scoring_bonus_for({"selector": "#add"}, [golden_same, learned_same], site)
    assert bonus == 18.0


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
