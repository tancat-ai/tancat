#!/usr/bin/env python3
"""AI-058 metric gate — seeded A/B on the CONTROLLED AMBIGUOUS mock.

The available mocks never emit a *recoverable* wrong-element failure: a clean
mock resolves correctly (no signal to learn), and a hard mock times out on a
single candidate (a negative can't steer anywhere). The AI-058 acceptance gate
(``warm+negatives > warm`` on ``mean_pass_depth``) therefore had nothing to
measure against.

This script closes that gap with a purpose-built mock (``mock_sites/ambiguous``)
where the success-message step has 2+ genuine candidates:

  * ``#order-success-message``  — the golden (visible, high-scoring)
  * ``#order-success-title``    — the other correct element
  * ``#order-note``             — the VISIBLE TRAP: shares the "Your order ..."
                                  text prefix, is a real scraped candidate, and
                                  is the wrong pick for "order success message"

The ONLY variable between legs is a step-scoped learned negative seeded against
the trap (``#order-note`` for the ASSERT 'order success message' step). The
control leg runs with an empty store. We then verify whether the negative
demotes the trap and lets the correct success element win — i.e. whether the
step-scoped negative flips the resolver on the very step it was recorded on,
with no cross-step bleed.

Isolation guarantees (no leaks into baseline / eval / other results):
- Every store + evidence + generated test lives under ONE temp dir;
  ``AITEST_STORAGE_ROOT``/``AITEST_WORKSPACE`` point there for every leg.
- Auto-learn is disabled (``AI059_DISABLE_AUTO_LEARN=1``, ``RAG_AUTO_LEARN=0``);
  the driver's own conftest writes evidence into the temp dir only.
- ``scripts/eval/baseline.json`` / ``eval_results.db`` are NEVER touched.
- ``generated_tests/`` is never written.
- The mock is served read-only from ``mock_sites/ambiguous``.
- The seeded store is built in-memory from a hardcoded LearnedPattern.

Usage:
    python scripts/ai058_ambiguous_seeded_ab.py
"""

from __future__ import annotations

import asyncio
import os
import re
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

LAB_IDENTITY = "ai059-lab:ambiguous"
MOCK_DIR = PROJECT_ROOT / "mock_sites" / "ambiguous"
MOCK_URL = "http://localhost:8781/index.html"
PORT = 8781  # the pipeline's standard mock port (nothing else holds it during this run)

# The trap selector the negative is seeded against, and the correct selectors.
TRAP_SELECTOR = "#order-note"
CORRECT_SELECTORS = ("#order-success-message", "#order-success-title")

CONFTEST_TEMPLATE = textwrap.dedent(
    """\
    from pathlib import Path
    from typing import Any
    from playwright.sync_api import Page
    import pytest
    from src.evidence_tracker import EvidenceTracker

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_makereport(item: Any, call: Any) -> None:
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

STORY = {
    "user_story": (
        "As a customer, I want to browse the store, choose a product, choose how "
        "many I want, and complete my purchase, ending with a clear confirmation "
        "that my order was placed."
    ),
    "conditions": [
        "1. Open the store home page in the browser",
        "2. On the order form, choose the 'Grey Hoodie' item from the item dropdown",
        "3. Set the quantity field to 2",
        "4. Click the 'Place Order' button to submit the order",
        "5. Confirm the browser has navigated to the order confirmation page",
        "6. Verify the 'Order Confirmed' heading is displayed",
        "7. Verify the order success message summarising the purchased item and quantity is displayed",
        "8. Click the 'Back to Store' link to return to the home page",
    ],
    "target_urls": [MOCK_URL],
}


def _store_path(root: Path) -> Path:
    return root / "default" / "evidence" / "rag_store.db"


def build_store(root: Path, *, seed_negative: bool) -> Path:
    """Create a store at *root*; when *seed_negative* is set, insert the ONE
    known ``#order-note`` negative for the exact (ASSERT, 'order success
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
                description="order success message",
                locator=TRAP_SELECTOR,
                site_hash=sentinel,
                confidence=1.0,
                source="learned_negative",
            )
        )
    return rag_path


def run_pipeline_once(store_root: Path) -> tuple[str, list]:
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
    (output_dir / "test_ambiguous.py").write_text(code, encoding="utf-8")
    if page_objects:
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        (pages_dir / "__init__.py").write_text("", encoding="utf-8")
        for page_obj in page_objects:
            (pages_dir / f"{page_obj.module_name}.py").write_text(page_obj.module_source)


def _success_locator(code: str) -> str:
    """Extract the selector the generated test asserts for the success message."""
    loc = "UNRESOLVED"
    for line in code.splitlines():
        if "success message" in line.lower() or "order success" in line.lower():
            m = re.search(r"['\"]([^'\"]*(?:[#\.\[]|has-text)[^'\"]*)['\"]", line)
            if m:
                loc = m.group(1)
                break
    return loc


def run_leg(output_dir: Path, label: str) -> tuple[float, str]:
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
    code = (output_dir / "test_ambiguous.py").read_text(encoding="utf-8")
    loc = _success_locator(code)
    ev_dir = output_dir / "evidence"
    metrics = analyze_sidecars(ev_dir if ev_dir.exists() else output_dir)
    print(
        f"  [{label}] rc={proc.returncode} mean_pass_depth={metrics.mean_pass_depth:.3f} "
        f"green_rate={metrics.first_pass_green_rate:.3f} tests={metrics.tests_analyzed} "
        f"passed={metrics.tests_passed} | success locator={loc}"
    )
    return metrics.mean_pass_depth, loc


def main() -> int:
    load_dotenv()
    base = Path(tempfile.mkdtemp(prefix="ai058_amb_seeded_"))
    print(f"Isolated work dir: {base}")

    os.environ["RAG_ENABLED"] = "1"
    os.environ["AI059_DISABLE_AUTO_LEARN"] = "1"
    os.environ["RAG_AUTO_LEARN"] = "0"
    os.environ["PLAYWRIGHT_HEADLESS"] = "1"

    with MockServer.start(port=PORT, directory=MOCK_DIR):
        print(f"Mock serving on :{PORT} (read-only from {MOCK_DIR})")

        # ---- CONTROL: empty store, no negative ----
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

        # ---- TREATMENT: ONE seeded #order-note negative ----
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
    print("AI-058 metric gate — seeded A/B on the ambiguous mock")
    print("  (the ONLY variable is the step-scoped negative on the trap)")
    print("=" * 64)
    print(f"  CONTROL   success locator : {loc_c}")
    print(f"  TREATMENT success locator : {loc_t}")
    print(f"  control   mean_pass_depth : {mpd_c:.3f}")
    print(f"  treatment mean_pass_depth : {mpd_t:.3f}")
    print(f"  work dir retained (temp, no repo writes): {base}")

    control_trap = TRAP_SELECTOR.lstrip("#") in loc_c
    treatment_trap = TRAP_SELECTOR.lstrip("#") in loc_t
    print("\n  TRAP AVOIDANCE (the real signal — does the negative demote the trap?):")
    print(f"    control picked the trap   : {control_trap}")
    print(f"    treatment picked the trap : {treatment_trap}")
    if control_trap and not treatment_trap:
        print(
            "    VERDICT: FLIP — the step-scoped negative demoted the trap; "
            "correct element now wins. AI-058 gate demonstrable."
        )
    elif not control_trap and not treatment_trap:
        print(
            "    VERDICT: NO TRAP PICKED ON EITHER LEG — the resolver already "
            "avoids the trap on a clean run; the negative is a no-op here "
            "(mechanism is safe but this run did not force the failure)."
        )
    else:
        print("    VERDICT: UNEXPECTED — see locators above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
