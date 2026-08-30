#!/usr/bin/env python3
"""AI-058/AI-064 — deterministic seeded-store A/B (no mock modification, no leaks).

Proves the step-scoped negative flips the resolver for the recurring banking
error: "payment success message" historically resolved to the WRONG hidden
``#payment-error`` on some runs (3 real evidence sidecars) and to the correct
``#payment-success-title`` on others. This script seeds a store with ONLY the
known ``#payment-error`` negative and measures whether the generated test for
that step resolves to the correct element — i.e. whether the negative turns the
failing outcome into the passing one.

Isolation guarantees (no leaks into baseline / eval / other results):
- Every store + evidence + generated test lives under ONE temp dir
  (``tempfile.mkdtemp``); ``AITEST_STORAGE_ROOT``/``AITEST_WORKSPACE`` point
  there for every leg.
- Auto-learn is disabled (``AI059_DISABLE_AUTO_LEARN=1``, ``RAG_AUTO_LEARN=0``);
  the driver's own conftest (not the production one) writes evidence into the
  temp dir only.
- ``scripts/eval/baseline.json`` / ``eval_results.db`` are NEVER touched (no
  ``eval_harness`` persist commands are invoked).
- ``generated_tests/`` is never written.
- The banking mock is served read-only from ``mock_sites/banking``; nothing is
  written there.
- The seeded store is built in-memory from a hardcoded LearnedPattern; nothing
  about the run is persisted beyond the temp dir.

Usage:
    python scripts/ai058_seeded_ab.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))  # for MockServer import

from dotenv import load_dotenv  # noqa: E402

from scripts.mock_server import MockServer  # noqa: E402

LAB_IDENTITY = "ai059-lab:banking"
MOCK_DIR = PROJECT_ROOT / "mock_sites" / "banking"
MOCK_URL = "http://localhost:8781/index.html"
PORT = 8781  # the pipeline's standard mock port (nothing else holds it during this run)

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
        refs = {"condition_ref": "unknown", "story_ref": "unknown"}
        for mark in request.node.iter_markers("evidence"):
            refs["condition_ref"] = mark.kwargs.get("condition_ref", refs["condition_ref"])
            refs["story_ref"] = mark.kwargs.get("story_ref", refs["story_ref"])
        tracker = EvidenceTracker(
            page=page,
            test_name=test_name,
            condition_ref=refs["condition_ref"],
            story_ref=refs["story_ref"],
            test_package_dir=Path(request.node.fspath).parent,
        )
        yield tracker
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


# The story exercises the payment-success step where the recurring wrong pick
# (#payment-error) appears. Conditions mirror the real eval-007 banking story,
# but the CLAIM here is narrow: under a seeded negative the generated locator
# for "payment success message" must be #payment-success-title, not
# #payment-error. Mean-pass-depth is reported but the resolution is the proof.
STORY = {
    "user_story": (
        "As a customer, I want to sign in to my online banking, view my account "
        "balances, transfer money, and pay a bill."
    ),
    "conditions": [
        "1. Navigate to the bank sign-in page",
        "2. Sign in with username and password",
        "3. Verify the accounts dashboard shows my account balances",
        "4. Click the Transfer Money link",
        "5. Fill in the transfer form and submit",
        "6. Verify the transfer success message appears",
        "7. Navigate to Pay Bills and pay a bill",
        "8. Verify the payment success message appears",
    ],
    "target_urls": [MOCK_URL],
}


def _store_path(root: Path) -> Path:
    return root / "default" / "evidence" / "rag_store.db"


def build_store(root: Path, *, seed_negative: bool) -> Path:
    """Create a store at *root*; when *seed_negative* is set, insert the ONE
    known ``#payment-error`` negative for the exact (ASSERT, 'payment success
    message') step. Returns the store path."""
    from src.learning_impact import lab_site_hash
    from src.rag_learn import LearnedPattern
    from src.rag_store import MilvusLiteBackend, RAGStore, SentenceTransformerEmbedder

    rag_path = _store_path(root)
    rag_path.parent.mkdir(parents=True, exist_ok=True)
    embedder = SentenceTransformerEmbedder()
    backend = MilvusLiteBackend(str(rag_path), embedder.dimension, embedder_identity=embedder.identity)
    store = RAGStore(backend, embedder)
    if seed_negative:
        sentinel = lab_site_hash(LAB_IDENTITY)
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
    return rag_path


def run_pipeline_once(store_root: Path) -> tuple[str, list]:
    """Generate the test suite against the mock using the store at *store_root*.

    Returns ``(final_code, page_objects)`` so the caller can write the POM
    ``pages/`` package the generated test imports (same contract as the A/B
    driver)."""
    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.test_generator import TestGenerator

    client = LLMClient(provider=os.environ.get("LLM_PROVIDER", "") or None)
    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=True)
    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story=STORY["user_story"],
            conditions="\n".join(STORY["conditions"]),
            target_urls=STORY["target_urls"],
        )
    )
    page_objects: list = []
    if orchestrator.last_result is not None:
        page_objects = list(orchestrator.last_result.generated_page_objects or [])
    return final_code, page_objects


def write_leg(output_dir: Path, code: str, page_objects: list) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "conftest.py").write_text(CONFTEST_TEMPLATE, encoding="utf-8")
    (output_dir / "test_banking.py").write_text(code, encoding="utf-8")
    if page_objects:
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        (pages_dir / "__init__.py").write_text("", encoding="utf-8")
        for page_obj in page_objects:
            (pages_dir / f"{page_obj.module_name}.py").write_text(page_obj.module_source, encoding="utf-8")


def run_leg(output_dir: Path, label: str) -> tuple[float, str]:
    """Run the generated test, return (mean_pass_depth, payment_success_locator)."""
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
    code = (output_dir / "test_banking.py").read_text(encoding="utf-8")
    loc = "UNRESOLVED"
    for line in code.splitlines():
        if "payment success message" in line.lower():
            if "assert" in line.lower() or "click" in line.lower():
                if "skipping" in line.lower():
                    loc = "SKIPPED"
                elif "select" in line or "has-text" in line or "#" in line or "." in line:
                    # extract the selector argument
                    import re

                    m = re.search(r"['\"]([^'\"]*(?:[#\.\[]|has-text)[^'\"]*)['\"]", line)
                    loc = m.group(1) if m else line.strip()[:80]
    ev_dir = output_dir / "evidence"
    metrics = analyze_sidecars(ev_dir if ev_dir.exists() else output_dir)
    print(
        f"  [{label}] rc={proc.returncode} mean_pass_depth={metrics.mean_pass_depth:.3f} "
        f"green_rate={metrics.first_pass_green_rate:.3f} tests={metrics.tests_analyzed} "
        f"passed={metrics.tests_passed} | payment-success locator={loc}"
    )
    return metrics.mean_pass_depth, loc


def main() -> int:
    load_dotenv()
    base = Path(tempfile.mkdtemp(prefix="ai058_seeded_ab_"))
    print(f"Isolated work dir: {base}")

    os.environ["RAG_ENABLED"] = "1"
    os.environ["AI059_DISABLE_AUTO_LEARN"] = "1"
    os.environ["RAG_AUTO_LEARN"] = "0"
    os.environ["PLAYWRIGHT_HEADLESS"] = "1"

    with MockServer.start(port=PORT, directory=MOCK_DIR):
        print(f"Mock serving on :{PORT} (read-only from {MOCK_DIR})")

        # ---- WARM (control): NO seeded negative, empty store ----
        control_root = base / "control"
        control_root.mkdir(parents=True, exist_ok=True)
        os.environ["AITEST_STORAGE_ROOT"] = str(control_root)
        os.environ["AITEST_WORKSPACE"] = "default"
        os.environ["AI059_LAB_SITE_IDENTITY"] = LAB_IDENTITY
        print("\n[CONTROL] generating (empty store)...")
        code_c, pages_c = run_pipeline_once(control_root)
        out_c = base / "out_control"
        write_leg(out_c, code_c, pages_c)
        mpd_c, loc_c = run_leg(out_c, "CONTROL")

        # ---- WARM+NEGATIVE (treatment): ONE seeded #payment-error negative ----
        seed_root = base / "seed"
        seed_root.mkdir(parents=True, exist_ok=True)
        store_path = build_store(seed_root, seed_negative=True)
        print(f"[SEED] store written: {store_path}")
        os.environ["AITEST_STORAGE_ROOT"] = str(seed_root)
        os.environ["AITEST_WORKSPACE"] = "default"
        os.environ["AI059_LAB_SITE_IDENTITY"] = LAB_IDENTITY
        print("[TREATMENT] generating (seeded negative store)...")
        code_t, pages_t = run_pipeline_once(seed_root)
        out_t = base / "out_seed"
        write_leg(out_t, code_t, pages_t)
        mpd_t, loc_t = run_leg(out_t, "TREATMENT")

    print("\n" + "=" * 64)
    print("AI-058/AI-064 seeded A/B — the ONLY variable is the seeded negative")
    print("=" * 64)
    print(f"  CONTROL (no negative) : locator={loc_c}")
    print(f"  TREATMENT (negative)  : locator={loc_t}")
    print(f"  control mean_pass_depth    : {mpd_c:.3f}")
    print(f"  treatment mean_pass_depth  : {mpd_t:.3f}")
    print(f"  work dir retained (temp, no repo writes): {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
