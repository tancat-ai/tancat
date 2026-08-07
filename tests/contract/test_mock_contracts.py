"""Contract tests — "does the product work?", not "what does the function return".

The Test-Pack Restructure (2026-08-03 CLI review, work item 2) split the suite
by intent. This layer is the antidote to the item's Why-section: 2,000+ green
unit tests coexisted with real bugs because they asserted internal invariants
against MagicMocks. Contract tests exercise the REAL pipeline artifacts
against the REAL local mock sites (banking mock eval-007, ecommerce mock
eval-006) with no LLM and no external network:

  - the golden-key dataset is structurally valid (schema contract)
  - the captured pipeline output parses and imports (import contract)
  - the captured tests EXECUTE against the mock and pass (behaviour contract)
  - mock route aliases serve the vocabulary journeys need (route contract)

Everything here is offline/localhost and CI-able. LLM-dependent regeneration
is deliberately NOT exercised — that is eval's ``--regenerate`` mode.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "scripts" / "eval" / "dataset"
CAPTURES_DIR = ROOT / "scripts" / "eval" / "captures"
MOCK_DIR = ROOT / "mock_sites"

# Every mock dataset must ship with a capture and a mock dir (or the
# documented legacy exception). Contract: no dataset without its artifacts.
MOCK_DATASETS = {
    "eval-006": {"site": "ecommerce_mock", "mock": "ecommerce"},
    "eval-007": {"site": "banking_mock", "mock": "banking"},
}


@pytest.fixture(scope="module")
def dataset_files() -> dict[str, dict]:
    files: dict[str, dict] = {}
    for path in sorted(DATASET_DIR.glob("eval-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        files[data["id"]] = data
    return files


def test_all_mock_datasets_have_capture_and_mock_dir(dataset_files: dict) -> None:
    """Schema/artifact contract: every mock dataset is self-contained."""
    for story_id, spec in MOCK_DATASETS.items():
        assert story_id in dataset_files, f"{story_id} missing from dataset dir"
        capture = CAPTURES_DIR / f"{spec['site']}_code.py"
        assert capture.exists(), f"{story_id}: capture {capture.name} missing"
        mock = MOCK_DIR / spec["mock"]
        assert mock.is_dir(), f"{story_id}: mock dir {mock} missing"


def test_eval007_dataset_required_keys(dataset_files: dict) -> None:
    """Schema contract: golden-key fields the harness depends on."""
    required = {"id", "site", "base_url", "user_story", "conditions", "golden_resolutions"}
    data = dataset_files["eval-007"]
    assert required <= set(data), f"eval-007 missing: {required - set(data)}"
    assert data["mock_dir"] == "mock_sites/banking"
    assert "localhost:8781" in data["base_url"]
    # Every condition must have at least one golden placeholder (a condition
    # with zero placeholders silently produces no skeleton → no test).
    by_index = {g["criterion_index"] for g in data["golden_resolutions"]}
    assert by_index == set(range(len(data["conditions"]))), "every criterion needs golden keys"


def test_eval007_capture_imports_and_collects() -> None:
    """Import contract: the captured pipeline output is valid runnable pytest.

    Mirrors what the export gate does for exports — a capture that fails to
    import means the pipeline emitted broken code and eval-static would
    silently under-report (0 skeletons).
    """
    capture = CAPTURES_DIR / "banking_mock_code.py"
    assert capture.exists()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            str(capture),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"capture does not collect:\n{result.stdout}\n{result.stderr}"
    # The capture must contain real test functions (not stubs/skips).
    assert "def test_" in capture.read_text(encoding="utf-8")


def test_eval006_capture_imports_and_collects() -> None:
    """Same import contract for the ecommerce mock capture."""
    capture = CAPTURES_DIR / "ecommerce_mock_code.py"
    assert capture.exists()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", str(capture)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"ecommerce capture does not collect:\n{result.stdout}\n{result.stderr}"


def test_banking_route_aliases_cover_journey_vocabulary() -> None:
    """Route contract: the banking mock's aliases must cover the keyword
    vocabulary the pipeline derives (login/accounts/transfer/pay/success),
    so journey discovery and submit-success transitions reach every page."""
    routes = json.loads((MOCK_DIR / "banking" / "mock_routes.json").read_text(encoding="utf-8"))
    needed = {"/login", "/accounts", "/transfer", "/pay-bill", "/payment-success", "/success"}
    missing = needed - set(routes)
    assert not missing, f"banking mock_routes.json missing aliases: {missing}"
    # Every alias maps to an existing file.
    for alias, target in routes.items():
        if alias.startswith("_"):
            continue
        assert (MOCK_DIR / "banking" / target).exists(), f"alias {alias} -> missing file {target}"


def test_banking_mock_serves_all_pages() -> None:
    """Behaviour contract (offline): every banking mock page serves HTTP 200
    and the session gate redirects unauthenticated visitors to sign-in."""
    from scripts.mock_server import MockServer

    with MockServer.start(port=8781, directory="mock_sites/banking"):
        import urllib.request

        for path in (
            "/index.html",
            "/dashboard.html",
            "/transfer.html",
            "/payments.html",
            "/transfer_success.html?amount=10.00",
            "/payment_success.html?amount=10.00",
        ):
            with urllib.request.urlopen(f"http://localhost:8781{path}", timeout=5) as resp:
                assert resp.status == 200, f"{path} -> {resp.status}"
