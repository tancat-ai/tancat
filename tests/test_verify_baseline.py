"""Tests for ``src.verify_baseline`` — expected-red baseline comparison.

The point of B-058 is that a fresh ``verify_production`` run must fail only on
*new* gate failures, never on the known unresolved-ASSERT class. These tests
pin that behaviour without a browser, LLM, or network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.verify_baseline import (
    SiteBaseline,
    compare_run,
    compare_site,
    load_baseline,
    parse_baseline,
    short_test_name,
    stable_gate_key,
)

BASELINE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "verify_production_baseline.json"


# ── stable_gate_key ─────────────────────────────────────────────────────────


def test_stable_gate_key_strips_dynamic_suffixes() -> None:
    assert stable_gate_key("Test execution (44.1s)") == "Test execution"
    assert stable_gate_key("Pipeline generation (12.3s)") == "Pipeline generation"
    assert stable_gate_key("LLM connected (openai-local/qwen)") == "LLM connected"


def test_stable_gate_key_keeps_static_names() -> None:
    assert stable_gate_key("Test functions >= 5") == "Test functions >= 5"
    assert stable_gate_key("No pytest.skip") == "No pytest.skip"
    assert stable_gate_key("Pipeline resolved all placeholders") == "Pipeline resolved all placeholders"


# ── parse_baseline / load_baseline ──────────────────────────────────────────


def _payload() -> dict[str, object]:
    return {
        "version": 1,
        "recorded": "2026-09-11",
        "recorded_commit": "abc1234",
        "sites": {
            "saucedemo": {
                "known_failing_gates": ["No pytest.skip", "Test execution (1.0s)"],
                "max_unresolved_placeholders": 2,
                "known_unresolved_placeholders": ["item in cart"],
                "expected_failing_tests": ["test_04"],
                "expected_min_tests": 5,
            }
        },
    }


def test_parse_baseline_normalises_gate_names() -> None:
    baseline = parse_baseline(_payload())
    entry = baseline.sites["saucedemo"]
    assert entry.known_failing_gates == ("No pytest.skip", "Test execution")
    assert entry.max_unresolved_placeholders == 2
    assert entry.expected_min_tests == 5
    assert entry.expected_failing_tests == ("test_04",)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: "bad", id="not-a-dict"),
        pytest.param(lambda d: {**d, "sites": {}}, id="empty-sites"),
        pytest.param(lambda d: {**d, "sites": {"s": {"known_failing_gates": "nope"}}}, id="gates-not-list"),
        pytest.param(lambda d: {**d, "sites": {"s": {"max_unresolved_placeholders": -1}}}, id="negative-budget"),
        pytest.param(lambda d: {**d, "sites": {"s": {"max_unresolved_placeholders": True}}}, id="bool-budget"),
        pytest.param(
            lambda d: {**d, "sites": {"s": {"expected_failing_tests": "test_01"}}}, id="expected-tests-not-list"
        ),
    ],
)
def test_parse_baseline_rejects_invalid(mutate: object) -> None:
    payload = mutate(_payload())  # type: ignore[operator]
    with pytest.raises(ValueError):
        parse_baseline(payload, source="test")


def test_load_baseline_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    baseline = load_baseline(path)
    assert baseline.recorded == "2026-09-11"
    assert baseline.recorded_commit == "abc1234"


def test_load_baseline_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        load_baseline(tmp_path / "absent.json")


# ── compare_site ────────────────────────────────────────────────────────────


def _entry() -> SiteBaseline:
    return SiteBaseline(
        known_failing_gates=("No pytest.skip", "Pipeline resolved all placeholders"),
        max_unresolved_placeholders=2,
    )


def test_known_red_is_tolerated() -> None:
    gates = [("LLM connected (m)", True), ("No pytest.skip", False), ("Pipeline resolved all placeholders", False)]
    cmp = compare_site("saucedemo", gates, ["skip a", "skip b"], _entry())
    assert cmp.regressed is False
    assert sorted(cmp.tolerated_failures) == ["No pytest.skip", "Pipeline resolved all placeholders"]
    assert cmp.new_failures == []


def test_new_failure_regresses() -> None:
    gates = [
        ("No pytest.skip", False),
        ("Pipeline resolved all placeholders", False),
        ("Evidence JSON generated", False),
    ]
    cmp = compare_site("saucedemo", gates, ["skip a", "skip b"], _entry())
    assert cmp.regressed is True
    assert cmp.new_failures == ["Evidence JSON generated"]


def test_fixed_gate_reported_as_improvement() -> None:
    gates = [("No pytest.skip", True), ("Pipeline resolved all placeholders", True)]
    cmp = compare_site("saucedemo", gates, [], _entry())
    assert cmp.regressed is False
    assert sorted(cmp.fixed_gates) == ["No pytest.skip", "Pipeline resolved all placeholders"]


def test_unresolved_over_budget_regresses() -> None:
    gates = [("No pytest.skip", False)]
    cmp = compare_site("saucedemo", gates, ["a", "b", "c"], _entry())
    assert cmp.unresolved_over_budget == 1
    assert cmp.regressed is True


def test_unresolved_within_budget_is_fine() -> None:
    gates = [("No pytest.skip", False)]
    cmp = compare_site("saucedemo", gates, ["a"], _entry())
    assert cmp.unresolved_over_budget == 0
    assert cmp.regressed is False


def test_dynamic_gate_name_matches_baseline_key() -> None:
    # A gate recorded statically must match the timed run name.
    entry = SiteBaseline(known_failing_gates=("Test execution",), max_unresolved_placeholders=0)
    cmp = compare_site("saucedemo", [("Test execution (99.9s)", False)], [], entry)
    assert cmp.regressed is False
    assert cmp.tolerated_failures == ["Test execution"]


# ── expected-failing tests (known ASSERT-resolution class) ──────────────────


def _assert_entry() -> SiteBaseline:
    return SiteBaseline(
        known_failing_gates=("Pipeline resolved all placeholders", "No pytest.skip"),
        max_unresolved_placeholders=8,
        expected_failing_tests=("test_04", "test_07"),
    )


def test_expected_failing_test_is_tolerated() -> None:
    gates = [("Pipeline resolved all placeholders", False), ("No pytest.skip", False), ("Test execution", False)]
    cmp = compare_site("automationexercise", gates, [], _assert_entry(), ["test_07_example"])
    assert cmp.regressed is False
    assert cmp.tolerated_failed_tests == ["test_07_example"]
    assert cmp.new_failed_tests == []
    # Execution is tolerated only because every failing test is expected.
    assert "Test execution" in cmp.tolerated_failures


def test_unexpected_failing_test_regresses() -> None:
    gates = [("Pipeline resolved all placeholders", False), ("No pytest.skip", False), ("Test execution", False)]
    cmp = compare_site("automationexercise", gates, [], _assert_entry(), ["test_07_example", "test_02_click"])
    assert cmp.regressed is True
    assert cmp.new_failed_tests == ["test_02_click"]
    assert "Test execution" in cmp.new_failures


def test_execution_failure_with_no_parsed_tests_regresses() -> None:
    # A timeout / collection error with no FAILED lines is not tolerated.
    cmp = compare_site("automationexercise", [("Test execution", False)], [], _assert_entry(), [])
    assert cmp.regressed is True
    assert cmp.new_failures == ["Test execution"]


def test_short_test_name_strips_path_and_params() -> None:
    assert short_test_name("generated_tests/x/test_a.py::test_07_example[chromium]") == "test_07_example"
    assert short_test_name("test_04") == "test_04"


# ── compare_run ─────────────────────────────────────────────────────────────


def test_compare_run_site_absent_from_baseline_always_regresses() -> None:
    baseline = parse_baseline(_payload())
    runs: dict[str, tuple[list[tuple[str, bool]], list[str], list[str]]] = {
        "brand-new-site": ([("Evidence JSON generated", False)], [], [])
    }
    cmp = compare_run(baseline, runs)
    assert cmp.regressed is True
    assert cmp.new_failures == ["brand-new-site: Evidence JSON generated"]


def test_compare_run_aggregates_fixed_gates() -> None:
    baseline = parse_baseline(_payload())
    runs: dict[str, tuple[list[tuple[str, bool]], list[str], list[str]]] = {
        "saucedemo": ([("No pytest.skip", True), ("Test execution (9.0s)", True)], [], [])
    }
    cmp = compare_run(baseline, runs)
    assert cmp.regressed is False
    assert sorted(cmp.fixed_gates) == ["saucedemo: No pytest.skip", "saucedemo: Test execution"]


# ── the committed baseline ──────────────────────────────────────────────────


def test_committed_baseline_is_valid_and_covers_both_sites() -> None:
    baseline = load_baseline(BASELINE_PATH)
    assert set(baseline.sites) == {"saucedemo", "automationexercise"}
    for entry in baseline.sites.values():
        assert "Pipeline resolved all placeholders" in entry.known_failing_gates
        assert "No pytest.skip" in entry.known_failing_gates
        # Variance ceiling, not the exact count — must be >= the observed max (4).
        assert entry.max_unresolved_placeholders >= 4
        assert entry.known_unresolved_placeholders
        assert entry.expected_failing_tests
    assert "test_07" in baseline.sites["automationexercise"].expected_failing_tests
