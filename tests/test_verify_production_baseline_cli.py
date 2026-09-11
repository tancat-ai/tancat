"""Tests for the ``scripts/verify_production.py`` baseline CLI glue.

The pure comparison logic lives in ``src/verify_baseline.py`` (tested in
``tests/test_verify_baseline.py``). These tests cover the thin script helpers
that only exist there: pytest-output parsing, baseline serialisation, and the
offline ``--check-baseline`` validation path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_production as vp  # noqa: E402

COMMITTED_BASELINE = SCRIPTS_DIR / "verify_production_baseline.json"


# ── _parse_failed_tests ─────────────────────────────────────────────────────


def test_parse_failed_tests_strips_path_and_params() -> None:
    stdout = (
        "=========================== short test summary info ===========================\n"
        "FAILED generated_tests/verify_x/test_x.py::test_07_example[chromium] - AssertionError\n"
        "FAILED generated_tests/verify_x/test_x.py::test_02_click[chromium] - TimeoutError\n"
    )
    assert vp._parse_failed_tests(stdout) == ["test_07_example", "test_02_click"]


def test_parse_failed_tests_dedupes_and_ignores_pass_lines() -> None:
    stdout = "PASSED x::test_01\nFAILED x::test_03\nFAILED x::test_03\n"
    assert vp._parse_failed_tests(stdout) == ["test_03"]


def test_parse_failed_tests_empty_on_no_failures() -> None:
    assert vp._parse_failed_tests("5 passed, 2 skipped in 40.0s") == []


# ── _write_baseline ─────────────────────────────────────────────────────────


def _site() -> vp.SiteVerification:
    return vp.SiteVerification(
        site_id="saucedemo",
        gates=[
            vp.Gate("LLM connected (m)", True),
            vp.Gate("No pytest.skip", False),
            vp.Gate("Pipeline resolved all placeholders", False),
        ],
        unresolved_placeholders=[
            "pytest.skip(\"Skipping: unresolved placeholders for: 'item in cart'\")",
            "pytest.skip(\"Skipping: unresolved placeholders for: 'success message'\")",
        ],
        failed_tests=["test_04_example"],
    )


def test_write_baseline_applies_ceiling_and_records_fragile_tests(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    vp._write_baseline(path, [_site()])

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    entry = data["sites"]["saucedemo"]
    assert entry["known_failing_gates"] == ["No pytest.skip", "Pipeline resolved all placeholders"]
    # 2 skip lines -> ceiling is 2x = 4 (variance headroom, not the exact count).
    assert entry["max_unresolved_placeholders"] == 4
    assert entry["known_unresolved_placeholders"] == ["item in cart", "success message"]
    assert entry["expected_failing_tests"] == ["test_04_example"]
    assert entry["expected_min_tests"] == 5


def test_written_baseline_round_trips_through_loader(tmp_path: Path) -> None:
    from src.verify_baseline import load_baseline

    path = tmp_path / "baseline.json"
    vp._write_baseline(path, [_site()])
    baseline = load_baseline(path)
    assert baseline.sites["saucedemo"].max_unresolved_placeholders == 4


# ── _check_baseline ─────────────────────────────────────────────────────────


def test_check_baseline_accepts_committed_file() -> None:
    assert vp._check_baseline(COMMITTED_BASELINE) == 0


def test_check_baseline_rejects_malformed_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert vp._check_baseline(path) == 1


def test_check_baseline_rejects_unknown_site(tmp_path: Path) -> None:
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps({"version": 1, "sites": {"does-not-exist": {}}}), encoding="utf-8")
    assert vp._check_baseline(path) == 1


def test_check_baseline_missing_file(tmp_path: Path) -> None:
    assert vp._check_baseline(tmp_path / "absent.json") == 1


def test_gate_key_strips_duration_suffix() -> None:
    assert vp.Gate("Test execution (44.1s)", True).key == "Test execution"
    assert vp.Gate("No pytest.skip", False).key == "No pytest.skip"
