"""AI-059 controlled baseline runner tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

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


# ---------------------------------------------------------------------------
# B-048 — the lab wipe must never touch the production RAG store
# ---------------------------------------------------------------------------


class _FakeProductionStorage:
    """Storage stub whose rag_path() points inside ``tmp_path``."""

    def __init__(self, evidence_dir: Path) -> None:
        self._evidence_dir = evidence_dir

    def rag_path(self) -> Path:
        return self._evidence_dir / "rag_store.db"


def test_restore_refuses_production_store_target(tmp_path: Path, monkeypatch: Any) -> None:
    """The exact B-048 incident: target == production rag_path → refuse, no wipe."""
    evidence = tmp_path / "evidence"
    production = evidence / "rag_store.db"
    production.mkdir(parents=True)
    (production / "milvus.db").write_text("golden patterns", encoding="utf-8")
    monkeypatch.setattr("src.storage.get_storage", lambda: _FakeProductionStorage(evidence))

    with pytest.raises(ValueError, match="production RAG store"):
        restore_store_snapshot(None, production)
    # Nothing was deleted — the golden pack survives.
    assert (production / "milvus.db").exists()


def test_restore_refuses_ancestor_of_production_store(tmp_path: Path, monkeypatch: Any) -> None:
    """Wiping evidence/ (or the storage root) kills the store too → refuse."""
    evidence = tmp_path / "evidence"
    (evidence / "rag_store.db").mkdir(parents=True)
    monkeypatch.setattr("src.storage.get_storage", lambda: _FakeProductionStorage(evidence))

    with pytest.raises(ValueError, match="production RAG store"):
        restore_store_snapshot(None, evidence)


def test_restore_refuses_production_embedder_companion(tmp_path: Path, monkeypatch: Any) -> None:
    evidence = tmp_path / "evidence"
    production = evidence / "rag_store.db"
    production.mkdir(parents=True)
    monkeypatch.setattr("src.storage.get_storage", lambda: _FakeProductionStorage(evidence))

    companion = Path(str(production) + ".embedder.json")
    companion.write_text("stamp", encoding="utf-8")
    with pytest.raises(ValueError, match="production RAG store"):
        restore_store_snapshot(None, companion)
    assert companion.exists()


def test_restore_production_override_restores_deliberately(tmp_path: Path, monkeypatch: Any) -> None:
    """allow_production_store=True is the explicit, documented escape hatch."""
    evidence = tmp_path / "evidence"
    production = evidence / "rag_store.db"
    production.mkdir(parents=True)
    (production / "stale.db").write_text("stale", encoding="utf-8")
    monkeypatch.setattr("src.storage.get_storage", lambda: _FakeProductionStorage(evidence))

    snapshot = tmp_path / "golden_snapshot.json"
    snapshot.write_text("golden", encoding="utf-8")
    restore_store_snapshot(snapshot, production, allow_production_store=True)
    assert production.is_file()
    assert production.read_text(encoding="utf-8") == "golden"


def test_restore_unrelated_targets_are_untouched_by_guard(tmp_path: Path) -> None:
    """Lab/tmp targets nowhere near the production store keep working."""
    snapshot = tmp_path / "snap.json"
    snapshot.write_text("golden", encoding="utf-8")
    target = tmp_path / "lab_store.db"
    target.write_text("stale", encoding="utf-8")
    restore_store_snapshot(snapshot, target)
    assert target.read_text(encoding="utf-8") == "golden"


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
    # The failed steps here carry no locator-class error, so no negatives yet
    # — the sentinel-positive path is unchanged.
    assert result == {"inserted": 2, "exists": 0, "skipped": 0, "negatives_inserted": 0, "negatives_exists": 0}
    sentinel = lab_site_hash("ai059-lab:ecommerce")
    md = {entry.metadata["description"]: entry.metadata for entry in fake.entries}
    assert set(md) == {"Add to cart", "Email"}
    assert md["Add to cart"]["action_type"] == "CLICK"
    assert md["Email"]["action_type"] == "FILL"
    assert md["Add to cart"]["site_hash"] == sentinel


def test_rebuild_warm_store_negative_aware_records_negatives(tmp_path: Path) -> None:
    """AI-058 Slice 2 + AI-063: a failed locator-class step becomes a
    sentinel-tagged learned_negative; an assertion failure WITH a resolved
    selector is now ALSO a resolved-but-wrong negative (lower confidence)."""
    (tmp_path / "fail.evidence.json").write_text(
        json.dumps(
            {
                "test": {"name": "fail", "status": "failed"},
                "steps": [
                    {
                        "type": "click",
                        "label": "Add to cart",
                        "locator": "#wrong-add",
                        "result": {
                            "status": "failed",
                            "error": (
                                "TimeoutError: Timeout 5000ms exceeded.\n"
                                "waiting for locator('page.locator(\"#wrong-add\")') to be visible"
                            ),
                        },
                    },
                    {
                        "type": "click",
                        "label": "Proceed",
                        "locator": "#proceed",
                        "result": {"status": "failed", "error": "AssertionError: text mismatch"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    fake = _FakeBackend()
    store = RAGStore(fake, _FakeEmbedder())
    result = rebuild_warm_store_from_evidence(tmp_path, store=store, lab_site_identity="ai059-lab:ecommerce")
    assert result["inserted"] == 0
    assert result["negatives_inserted"] == 2
    assert result["negatives_exists"] == 0
    sentinel = lab_site_hash("ai059-lab:ecommerce")
    negs = [e.metadata for e in fake.entries if e.metadata.get("entry_type") == "learned_negative"]
    assert len(negs) == 2
    by_loc = {n["selector"]: n for n in negs}
    assert by_loc["#wrong-add"]["site_hash"] == sentinel
    assert by_loc["#wrong-add"]["source"] == "learned_negative"
    assert by_loc["#wrong-add"]["confidence"] == 0.9
    # AI-063: resolved-but-wrong assertion pick is the second negative.
    assert by_loc["#proceed"]["confidence"] == 0.6
    # No learned positives from a failed test.
    assert not any(e.metadata.get("entry_type") == "learned" for e in fake.entries)


def test_rebuild_warm_store_negative_aware_toggle(tmp_path: Path) -> None:
    """``learn_negatives=False`` yields the positives-only control store."""
    (tmp_path / "fail.evidence.json").write_text(
        json.dumps(
            {
                "test": {"name": "fail", "status": "failed"},
                "steps": [
                    {
                        "type": "click",
                        "label": "Add to cart",
                        "locator": "#wrong-add",
                        "result": {
                            "status": "failed",
                            "error": (
                                "TimeoutError: Timeout 5000ms exceeded.\n"
                                "waiting for locator('page.locator(\"#wrong-add\")') to be visible"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    fake = _FakeBackend()
    store = RAGStore(fake, _FakeEmbedder())
    result = rebuild_warm_store_from_evidence(
        tmp_path, store=store, lab_site_identity="ai059-lab:ecommerce", learn_negatives=False
    )
    assert result["negatives_inserted"] == 0
    assert not any(e.metadata.get("entry_type") == "learned_negative" for e in fake.entries)


def test_rebuild_ab_warm_vs_warm_negatives_differ(tmp_path: Path) -> None:
    """AI-058 Slice 2 A/B: from the SAME evidence, the negative-aware rebuild
    carries strictly more signal than the positives-only rebuild — exactly the
    two stores the ``ControlledBaselineRunner`` compares (``warm-positive`` vs
    ``warm-positive-negative``)."""
    (tmp_path / "a.evidence.json").write_text(
        json.dumps(
            {
                "test": {"name": "a", "status": "passed"},
                "steps": [
                    {"type": "click", "label": "Add to cart", "locator": "#add", "result": {"status": "passed"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "b.evidence.json").write_text(
        json.dumps(
            {
                "test": {"name": "b", "status": "failed"},
                "steps": [
                    {
                        "type": "click",
                        "label": "Add to cart",
                        "locator": "#wrong-add",
                        "result": {
                            "status": "failed",
                            "error": (
                                "TimeoutError: Timeout 5000ms exceeded.\n"
                                "waiting for locator('page.locator(\"#wrong-add\")') to be visible"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # Control leg (warm-positive): positives only.
    control = _FakeBackend()
    rebuild_warm_store_from_evidence(
        tmp_path,
        store=RAGStore(control, _FakeEmbedder()),
        lab_site_identity="ai059-lab:ecommerce",
        learn_negatives=False,
    )
    # Treatment leg (warm-positive-negative): positives + negatives.
    treatment = _FakeBackend()
    treatment_result = rebuild_warm_store_from_evidence(
        tmp_path,
        store=RAGStore(treatment, _FakeEmbedder()),
        lab_site_identity="ai059-lab:ecommerce",
        learn_negatives=True,
    )
    control_negs = [e for e in control.entries if e.metadata.get("entry_type") == "learned_negative"]
    treatment_negs = [e for e in treatment.entries if e.metadata.get("entry_type") == "learned_negative"]
    assert len(control_negs) == 0
    assert len(treatment_negs) == 1
    assert treatment_result["negatives_inserted"] == 1
    # Both legs still carry the verified positive.
    assert any(e.metadata.get("selector") == "#add" for e in control.entries)
    assert any(e.metadata.get("selector") == "#add" for e in treatment.entries)


def test_seeded_negative_roundtrips_and_flips_step_scoped_score() -> None:
    """AI-064/AI-058 seeded-store A/B mechanism (the deterministic core of
    ``scripts/ai058_seeded_ab.py``): a single hand-seeded learned_negative for
    the exact (ASSERT, 'payment success message') step survives insertion,
    retrieves site-scoped, and down-weights the wrong locator on ITS step
    while leaving the correct alternative unscathed."""
    from src.placeholder_scorers import PlaceholderScorer
    from src.rag_learn import LearnedPattern
    from src.rag_store import RAGStore

    fake = _FakeBackend()
    store = RAGStore(fake, _FakeEmbedder())
    sentinel = lab_site_hash("ai059-lab:banking")

    # Seed EXACTLY one negative: the recurring banking wrong pick.
    store.upsert_negative_pattern(
        LearnedPattern(
            action_type="ASSERT",
            description="payment success message",
            locator="#payment-error",
            site_hash=sentinel,
            confidence=1.0,
            source="learned_negative",
        )
    )
    negs = [e for e in fake.entries if e.metadata.get("entry_type") == "learned_negative"]
    assert len(negs) == 1
    assert negs[0].metadata["selector"] == "#payment-error"

    # The dedup row (what retrieval's site/step gate would find) is present.
    found = store._backend.find_negative("ASSERT", "payment success message", sentinel)
    assert found is not None
    assert found.get("selector") == "#payment-error"

    # Step-scoped score via a RetrievedPattern built from the stored metadata
    # (equivalent to what RAGStore.retrieve returns with a real embedder).
    from src.rag_store import RetrievedPattern

    pats = [
        RetrievedPattern(
            description=negs[0].metadata.get("text", "ASSERT: payment success message"),
            selector=negs[0].metadata["selector"],
            action_type=negs[0].metadata.get("action_type", "ASSERT"),
            confidence=float(negs[0].metadata.get("confidence", 1.0)),
            source=negs[0].metadata.get("source", "learned_negative"),
            site_hash=negs[0].metadata.get("site_hash", ""),
            hit_count=int(negs[0].metadata.get("hit_count", 1) or 1),
        )
    ]

    # Step-scoped score: penalty on the wrong pick's own step.
    wrong_net = PlaceholderScorer._learned_net_evidence(
        {"selector": "#payment-error"},
        pats,
        sentinel,
        action="ASSERT",
        description="payment success message",
    )
    correct_net = PlaceholderScorer._learned_net_evidence(
        {"selector": "#payment-success-title"},
        pats,
        sentinel,
        action="ASSERT",
        description="payment success message",
    )
    assert wrong_net < 0  # the wrong locator is down-weighted
    assert correct_net == 0  # the correct alternative is unscathed


def test_resolver_ab_downweights_wrong_pick_on_own_step() -> None:
    """AI-064/AI-058 resolver-level A/B (deterministic, no LLM): on the frozen
    payments-only pool (the historical test_09 context), control ranks the
    wrong hidden ``#payment-error`` first; with the seeded negative its score
    drops and the correct title is unscathed; a different step is unchanged.
    Mirrors ``scripts/ai058_resolver_ab.py`` with a fake embedder (no model).

    The frozen ``scraped_pages/`` dumps are gitignored (CI-only artifact);
    skip cleanly when absent (CI) and run fully when present (local/eval).
    """
    from src.placeholder_resolver import PlaceholderResolver

    _pay_dump = Path("scripts/eval/scraped_pages/http_localhost_8781_payments.html.json")
    _ok_dump = Path("scripts/eval/scraped_pages/http_localhost_8781_payment_success.html.json")
    if not (_pay_dump.exists() and _ok_dump.exists()):
        pytest.skip("frozen scraped_pages/ dumps not present (gitignored; regenerate via eval_resolver --mode live)")

    sentinel = lab_site_hash("ai059-lab:banking")
    # Frozen payments-page pool: has the wrong #payment-error, NO success title.
    payments = json.loads(_pay_dump.read_text(encoding="utf-8"))
    pool = payments if isinstance(payments, list) else payments["elements"]
    pool = [dict(e) for e in pool]
    success = json.loads(_ok_dump.read_text(encoding="utf-8"))
    success_pool = success if isinstance(success, list) else success["elements"]
    from src.rag_store import RetrievedPattern

    seed_pat = [
        RetrievedPattern(
            description="ASSERT: payment success message",
            selector="#payment-error",
            action_type="ASSERT",
            confidence=1.0,
            source="learned_negative",
            site_hash=sentinel,
            hit_count=4,
            last_seen=0.0,
        )
    ]

    resolver = PlaceholderResolver(match_threshold=0)
    ctrl = resolver.rank_candidates("ASSERT", "payment success message", pool, golden_patterns=None, site_hash=sentinel)
    treat = resolver.rank_candidates(
        "ASSERT", "payment success message", pool, golden_patterns=seed_pat, site_hash=sentinel
    )
    ctrl_top = ctrl[0][1]["selector"]
    treat_err = [s for s, e in treat if e["selector"] == "#payment-error"]
    ctrl_err = [s for s, e in ctrl if e["selector"] == "#payment-error"]
    assert ctrl_top == "#payment-error"  # historical wrong-pick context reproduced
    assert ctrl_err and treat_err
    assert treat_err[0] < ctrl_err[0]  # seeded negative down-weights it

    # Consolidated pool (both pages): the correct winner is unscathed.
    both = pool + [dict(e) for e in success_pool]
    ctrl2 = resolver.rank_candidates(
        "ASSERT", "payment success message", both, golden_patterns=None, site_hash=sentinel
    )
    treat2 = resolver.rank_candidates(
        "ASSERT", "payment success message", both, golden_patterns=seed_pat, site_hash=sentinel
    )
    assert ctrl2[0][1]["selector"] == "#payment-success-message"
    assert treat2[0][1]["selector"] == "#payment-success-message"

    # Step-scoping guard: a different step ('payee') is unchanged by the seed.
    ctrl3 = resolver.rank_candidates("ASSERT", "payee", both, golden_patterns=None, site_hash=sentinel)
    treat3 = resolver.rank_candidates("ASSERT", "payee", both, golden_patterns=seed_pat, site_hash=sentinel)
    assert [e["selector"] for _, e in ctrl3] == [e["selector"] for _, e in treat3]


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


# ── AI-058: contrastive learned store (negatives) ──────────────────────────


def test_upsert_negative_pattern_inserts_then_dedups() -> None:
    from src.rag_learn import LearnedPattern
    from src.rag_store import RAGStore

    fake = _FakeBackend()
    store = RAGStore(fake, _FakeEmbedder())
    pat = LearnedPattern("CLICK", "Add to cart", "#wrong-add", "site-x", confidence=1.0, source="learned_negative")
    assert store.upsert_negative_pattern(pat) == ("inserted", 1)
    assert store.upsert_negative_pattern(pat) == ("exists", 2)
    rows = [e.metadata for e in fake.entries if e.metadata.get("entry_type") == "learned_negative"]
    assert len(rows) == 1
    assert rows[0]["hit_count"] == 2
    assert rows[0]["last_seen"] > 0
    assert store.counts_by_type().get("learned_negative") == 1


def test_learn_negatives_from_evidence_only_locator_failures() -> None:
    from src.rag_learn import learn_negatives_from_evidence
    from src.rag_store import RAGStore

    fake = _FakeBackend()
    store = RAGStore(fake, _FakeEmbedder())
    locator_err = (
        "TimeoutError: Timeout 5000ms exceeded.\nwaiting for locator('page.locator(\"#wrong-add\")') to be visible"
    )
    steps = [
        # locator-class failure with a resolved selector -> negative
        {
            "type": "click",
            "label": "Add to cart",
            "locator": "#wrong-add",
            "url": "http://localhost:8781/x.html",
            "result": {"status": "failed", "error": locator_err},
        },
        # AI-063 resolved-but-wrong: a failed assertion WITH a resolved selector
        # is a negative at confidence 0.6 (the element existed and was picked,
        # then failed). Infra/nav flakes stay excluded.
        {
            "type": "click",
            "label": "Proceed",
            "locator": "#proceed",
            "url": "http://localhost:8781/x.html",
            "result": {"status": "failed", "error": "AssertionError: expected text"},
        },
        # locator failure but NO resolved selector -> cannot key a negative
        {
            "type": "click",
            "label": "Checkout",
            "locator": "",
            "url": "http://localhost:8781/x.html",
            "result": {"status": "failed", "error": locator_err},
        },
        # passing step -> not a negative
        {
            "type": "click",
            "label": "Pass",
            "locator": "#ok",
            "url": "http://localhost:8781/x.html",
            "result": {"status": "passed"},
        },
    ]
    result = learn_negatives_from_evidence(steps, store=store)
    assert result == {"inserted": 2, "exists": 0}
    negs = [e.metadata for e in fake.entries if e.metadata.get("entry_type") == "learned_negative"]
    assert len(negs) == 2
    by_loc = {n["selector"]: n for n in negs}
    assert by_loc["#wrong-add"]["source"] == "learned_negative"
    assert by_loc["#wrong-add"]["confidence"] == 0.9
    # AI-063: resolved-but-wrong assertion failure with a resolved selector
    # is now a negative at lower confidence.
    assert by_loc["#proceed"]["source"] == "learned_negative"
    assert by_loc["#proceed"]["confidence"] == 0.6


def test_learn_from_patch_records_old_selector_negative() -> None:
    from src.rag_learn import learn_from_patch
    from src.rag_store import RAGStore

    fake = _FakeBackend()
    store = RAGStore(fake, _FakeEmbedder())
    result = learn_from_patch(
        old_text='page.locator("#wrong-add").click()',
        new_text='page.locator("#add-to-cart").click()',
        base_url="http://localhost:8781/x.html",
        description="Add to cart",
        store=store,
    )
    assert result == {"inserted": 1, "exists": 0}
    negs = [e.metadata for e in fake.entries if e.metadata.get("entry_type") == "learned_negative"]
    assert len(negs) == 1
    assert negs[0]["selector"] == "#wrong-add"
    pos = [e.metadata for e in fake.entries if e.metadata.get("entry_type") == "learned"]
    assert len(pos) == 1
    assert pos[0]["selector"] == "#add-to-cart"


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

    def find_negative(self, action_type: str, description: str, site_hash: str) -> dict[str, Any] | None:
        for entry in self.entries:
            md = entry.metadata
            if (
                md.get("entry_type") == "learned_negative"
                and md.get("action_type") == action_type
                and md.get("description") == description
                and md.get("site_hash") == site_hash
            ):
                return md
        return None

    def increment_learned_hit(self, row: dict) -> int:
        for entry in self.entries:
            md = entry.metadata
            if (
                md.get("action_type") == row.get("action_type")
                and md.get("description") == row.get("description")
                and md.get("site_hash") == row.get("site_hash")
            ):
                new_hit = int(md.get("hit_count", 0)) + 1
                md["hit_count"] = new_hit
                md["last_seen"] = 1_700_000_000.0 + new_hit
                return new_hit
        return 1

    def search(self, query_vector: list[float], k: int) -> list:
        return []

    def count(self) -> int:
        return len(self.entries)

    def clear(self) -> None:
        self.entries.clear()

    def counts_by_type(self) -> dict[str, int]:
        counter: dict[str, int] = {}
        for entry in self.entries:
            et = str(entry.metadata.get("entry_type", "unknown"))
            counter[et] = counter.get(et, 0) + 1
        return counter

    def query_dedup_keys(self, entry_type: str) -> list[str]:
        return []

    def delete_learned(self) -> int:
        return 0

    def verify_embedder(self, embedder_identity: str | None) -> None:
        return None
