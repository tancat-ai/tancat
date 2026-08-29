#!/usr/bin/env python3
"""AI-058 Slice 2 — live mock A/B: warm-positives vs warm+negatives.

Serves the ecommerce mock on :8781, generates + executes a test suite
against it for three legs, and measures ``mean_pass_depth`` (the
AI-058 acceptance metric) per leg:

  * cold            — empty store (reference)
  * warm            — store rebuilt from the cold run's PASSED steps only
  * warm+negatives  — store rebuilt from cold run PASSED + locator-failure steps

The negatives leg uses the same lab sentinel (``ai059-lab:ecommerce``) the
resolver scopes to via ``AI059_LAB_SITE_IDENTITY``, so the contrastive
penalty actually applies at resolve time. This is the live measurement the
Slice-2 code gates were built to support.

Usage:
    python scripts/ai058_ab_mock_run.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from contextlib import nullcontext
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))  # for MockServer + eval imports

from dotenv import load_dotenv  # noqa: E402

from scripts.mock_server import MockServer  # noqa: E402

CONFTEST_TEMPLATE = textwrap.dedent(
    """\
    from pathlib import Path
    from typing import Any
    from playwright.sync_api import Page
    import pytest
    from src.evidence_tracker import EvidenceTracker

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_makereport(item: Any, call: Any) -> None:
        # Attach the call report so the evidence fixture can read real status.
        if call.when == "call":
            setattr(item, "rep_call", call)

    @pytest.fixture()
    def evidence_tracker(page: Page, request: Any) -> EvidenceTracker:
        test_name = getattr(request.node, "name", "unknown_test")
        condition_ref = ""
        story_ref = ""
        for mark in request.node.iter_markers("evidence"):
            condition_ref = mark.kwargs.get("condition_ref", condition_ref)
            story_ref = mark.kwargs.get("story_ref", story_ref)
        tracker = EvidenceTracker(
            page=page,
            test_name=test_name,
            condition_ref=condition_ref or "unknown",
            story_ref=story_ref or "unknown",
            test_package_dir=Path(request.node.fspath).parent,
        )
        yield tracker
        # AI-063: mirror the production conftest — the sidecar status must
        # reflect the REAL pytest outcome, not a blanket "passed". Without
        # this the A/B harness can never learn a negative from a failed
        # step (every sidecar says "passed" -> the negative sweep has
        # nothing to scan). rep_call is attached by the pytest
        # pytest_runtest_makereport hook, which the runner includes.
        rep_call = getattr(request.node, "rep_call", None)
        if rep_call is not None and getattr(rep_call, "skipped", False):
            status = "skipped"
        elif rep_call is not None and getattr(rep_call, "passed", False):
            status = "passed"
        else:
            status = "failed"
        if tracker.steps:
            tracker.write(status=status)
    """
)

import glob  # noqa: E402

# Available A/B targets. eval-006 (ecommerce) is a clean single-section mock;
# eval-005 (lv_insurance) is a multi-section SPA served at repo root and is the
# hard case (54% resolution, multi-vehicle/driver flows -> the AI-063 candidate).
DATASETS = {
    "eval-006": {
        "lab": "ai059-lab:ecommerce",
        "mock_dir": "mock_sites/ecommerce",
        "url": "http://localhost:8781/index.html",
    },
    "eval-009": {
        "lab": "ai059-lab:trap",
        "mock_dir": "mock_sites/trap",
        "url": "http://localhost:8781/index.html",
    },
    "eval-005": {
        "lab": "ai059-lab:lv_insurance",
        "mock_dir": None,  # served at repo root (legacy eval-005)
        "url": "http://localhost:8781/generated_tests/mock_insurance_site.html",
    },
    "eval-007": {
        "lab": "ai059-lab:banking",
        "mock_dir": "mock_sites/banking",
        "url": "http://localhost:8781/index.html",
    },
    "eval-001": {
        # Real site (no mock server). lab identity == host so the sentinel
        # equals the URL-derived scope and the resolver applies the store.
        "lab": "www.saucedemo.com",
        "mock_dir": None,
        "real_site": True,
        "url": "https://www.saucedemo.com",
    },
}
DATASET_ID = os.environ.get("AI058_DATASET", "eval-006")
DS = DATASETS[DATASET_ID]
LAB_IDENTITY = DS["lab"]
MOCK_URL = DS["url"]


def _store_path(root: Path) -> Path:
    return root / "default" / "evidence" / "rag_store.db"


def build_store(root: Path, learn_negatives: bool, evidence_dir: Path) -> dict:
    """Rebuild a sentinel-scoped warm store from *evidence_dir* sidecars."""
    from src.learning_impact import rebuild_warm_store_from_evidence
    from src.rag_store import MilvusLiteBackend, RAGStore, SentenceTransformerEmbedder

    root.mkdir(parents=True, exist_ok=True)
    embedder = SentenceTransformerEmbedder()
    rag_path = _store_path(root)
    rag_path.parent.mkdir(parents=True, exist_ok=True)
    backend = MilvusLiteBackend(str(rag_path), embedder.dimension, embedder_identity=embedder.identity)
    store = RAGStore(backend, embedder)
    return rebuild_warm_store_from_evidence(
        evidence_dir, store=store, lab_site_identity=LAB_IDENTITY, learn_negatives=learn_negatives
    )


def run_pipeline_once(story: dict, store_root: Path) -> tuple[str, list]:
    """Generate a test suite against the mock using the store at *store_root*.

    Returns ``(final_code, page_objects)`` so the caller can write the POM
    ``pages/`` package the generated test imports.
    """
    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.test_generator import TestGenerator

    client = LLMClient(provider=os.environ.get("LLM_PROVIDER", "") or None)
    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=True)
    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story=story["user_story"],
            conditions="\n".join(story["conditions"]),
            target_urls=[MOCK_URL],
        )
    )
    page_objects = []
    if orchestrator.last_result is not None:
        page_objects = list(orchestrator.last_result.generated_page_objects or [])
    return final_code, page_objects


def write_leg(output_dir: Path, code: str, page_objects: list) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "conftest.py").write_text(CONFTEST_TEMPLATE, encoding="utf-8")
    (output_dir / "test_ecommerce.py").write_text(code, encoding="utf-8")
    if page_objects:
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        (pages_dir / "__init__.py").write_text("", encoding="utf-8")
        for page_obj in page_objects:
            (pages_dir / f"{page_obj.module_name}.py").write_text(page_obj.module_source, encoding="utf-8")


def execute_leg(output_dir: Path, leg_label: str) -> float:
    """Write + run the generated test, return its mean_pass_depth."""
    from src.learning_metrics import analyze_sidecars

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(output_dir),
            "-o",
            "addopts=",
            "-o",
            f"pythonpath={PROJECT_ROOT}",
            "--browser=chromium",
            "--screenshot=only-on-failure",
            "--timeout=180",
            "-q",
            "--no-header",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(PROJECT_ROOT),
    )
    ev_dir = output_dir / "evidence"
    metrics = analyze_sidecars(ev_dir if ev_dir.exists() else output_dir)
    print(
        f"  [{leg_label}] pytest rc={proc.returncode} "
        f"mean_pass_depth={metrics.mean_pass_depth:.3f} "
        f"green_rate={metrics.first_pass_green_rate:.3f} "
        f"tests={metrics.tests_analyzed} passed={metrics.tests_passed}"
    )
    return metrics.mean_pass_depth


def main() -> int:
    load_dotenv()
    base = Path(tempfile.mkdtemp(prefix="ai058_ab_"))
    print(f"Work dir: {base}")

    cands = glob.glob(str(PROJECT_ROOT / "scripts/eval/dataset" / f"{DATASET_ID}_*.json"))
    if not cands:
        raise SystemExit(f"no dataset json for {DATASET_ID}")
    story = json.loads(Path(cands[0]).read_text(encoding="utf-8"))
    if story.get("base_url"):
        global MOCK_URL
        MOCK_URL = story["base_url"]
    print(f"Dataset: {DATASET_ID} ({story.get('site')})  url={MOCK_URL}")

    os.environ["RAG_ENABLED"] = "1"
    os.environ["AI059_DISABLE_AUTO_LEARN"] = "1"
    os.environ["RAG_AUTO_LEARN"] = "0"
    os.environ["AI059_LAB_SITE_IDENTITY"] = LAB_IDENTITY
    os.environ["PLAYWRIGHT_HEADLESS"] = "1"

    mock_directory = PROJECT_ROOT if DS["mock_dir"] is None else PROJECT_ROOT / DS["mock_dir"]
    ctx = nullcontext() if DS.get("real_site") else MockServer.start(port=8781, directory=mock_directory)
    with ctx as _server:
        print("Mock serving on :8781")

        # ---- COLD: empty (fresh) store, just generate + execute for reference ----
        cold_root = base / "cold"
        cold_root.mkdir(parents=True, exist_ok=True)
        os.environ["AITEST_STORAGE_ROOT"] = str(cold_root)
        os.environ["AITEST_WORKSPACE"] = "default"
        cold_ev = base / "evidence_cold"
        cold_ev.mkdir(parents=True, exist_ok=True)
        print("\n[COLD] generating (empty store)...")
        t0 = time.time()
        code, pages = run_pipeline_once(story, cold_root)
        print(f"  generated in {time.time() - t0:.1f}s ({len(code)} chars), {len(pages)} pages")
        cold_out = base / "out_cold"
        write_leg(cold_out, code, pages)
        cold_mpd = execute_leg(cold_out, "COLD")
        # Harvest the cold evidence into a dir the warm rebuild can consume.
        src_ev = cold_out / "evidence"
        if src_ev.exists():
            for f in src_ev.glob("*.evidence.json"):
                shutil.copy(f, cold_ev / f.name)

        if os.environ.get("AI058_COLD_ONLY") == "1":
            print("\n[COLD-ONLY] skipping warm legs (set AI058_COLD_ONLY unset to run full A/B)")
            print(f"  cold mean_pass_depth={cold_mpd:.3f}")
            return 0

        # ---- Build the two warm stores from the cold evidence ----
        warm_root = base / "warm"
        warmneg_root = base / "warmneg"
        print("\n[BUILD] warm (positives only)...")
        warm_rebuild = build_store(warm_root, learn_negatives=False, evidence_dir=cold_ev)
        print(f"  {warm_rebuild}")
        print("[BUILD] warm+negatives (positives + locator failures)...")
        warmneg_rebuild = build_store(warmneg_root, learn_negatives=True, evidence_dir=cold_ev)
        print(f"  {warmneg_rebuild}")

        # ---- WARM leg ----
        print("\n[WARM] generating (positives store)...")
        os.environ["AITEST_STORAGE_ROOT"] = str(warm_root)
        os.environ["AITEST_WORKSPACE"] = "default"
        t0 = time.time()
        code_w, pages_w = run_pipeline_once(story, warm_root)
        print(f"  generated in {time.time() - t0:.1f}s ({len(code_w)} chars), {len(pages_w)} pages")
        warm_out = base / "out_warm"
        write_leg(warm_out, code_w, pages_w)
        warm_mpd = execute_leg(warm_out, "WARM")

        # ---- WARM+NEGATIVES leg ----
        print("\n[WARM+NEG] generating (positives + negatives store)...")
        os.environ["AITEST_STORAGE_ROOT"] = str(warmneg_root)
        os.environ["AITEST_WORKSPACE"] = "default"
        t0 = time.time()
        code_wn, pages_wn = run_pipeline_once(story, warmneg_root)
        print(f"  generated in {time.time() - t0:.1f}s ({len(code_wn)} chars), {len(pages_wn)} pages")
        wn_out = base / "out_warmneg"
        write_leg(wn_out, code_wn, pages_wn)
        wn_mpd = execute_leg(wn_out, "WARM+NEG")

    print("\n" + "=" * 60)
    print("AI-058 Slice 2 — mock A/B result (mean_pass_depth)")
    print("=" * 60)
    print(f"  cold            : {cold_mpd:.3f}")
    print(f"  warm            : {warm_mpd:.3f}")
    print(f"  warm+negatives  : {wn_mpd:.3f}")
    print(f"  warm+neg - warm : {wn_mpd - warm_mpd:+.3f}")
    if wn_mpd > warm_mpd:
        print("  VERDICT: warm+negatives > warm  ->  Slice 1 is a WIN (proceed to Slice 3)")
    else:
        print("  VERDICT: warm+negatives <= warm  ->  no measurable lift here")
        print("           (likely evidence starvation: clean mock -> few locator failures)")
    print(f"\nWork dir retained: {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
