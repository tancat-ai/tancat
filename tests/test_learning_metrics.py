"""AI-059 metric extractor tests using synthetic evidence sidecars."""

from __future__ import annotations

import json
from pathlib import Path

from src.learning_metrics import analyze_sidecar, analyze_sidecars


def _sidecar(name: str, steps: list[dict], *, status: str = "failed", **test_fields: object) -> dict:
    return {"test": {"name": name, "status": status, **test_fields}, "steps": steps}


def _step(number: int, status: str = "passed", **result: object) -> dict:
    return {"step": number, "type": "click", "result": {"status": status, **result}}


def test_mean_pass_depth_uses_steps_before_first_failure() -> None:
    metrics = analyze_sidecar(_sidecar("A", [_step(1)] * 5, status="passed"))
    assert metrics.pass_depth == 1.0
    assert (
        analyze_sidecar(_sidecar("B", [_step(1), _step(2), _step(3, "failed"), _step(4), _step(5)])).pass_depth == 0.4
    )
    assert analyze_sidecar(_sidecar("C", [_step(1, "failed"), _step(2), _step(3), _step(4)])).pass_depth == 0.0


def test_aggregate_primary_example(tmp_path: Path) -> None:
    payloads = [
        _sidecar("A", [_step(i) for i in range(5)], status="passed"),
        _sidecar("B", [_step(1), _step(2), _step(3, "failed"), _step(4), _step(5)]),
        _sidecar("C", [_step(1, "failed"), _step(2), _step(3), _step(4)]),
    ]
    for payload in payloads:
        name = payload["test"]["name"]
        (tmp_path / f"{name}.evidence.json").write_text(json.dumps(payload), encoding="utf-8")
    metrics = analyze_sidecars(tmp_path)
    assert metrics.mean_pass_depth == (1.0 + 0.4 + 0.0) / 3
    assert metrics.first_pass_green_rate == 1 / 3
    assert metrics.tests_analyzed == 3


def test_declared_total_steps_preserves_depth_when_execution_stops_early() -> None:
    payload = _sidecar("early", [_step(1), _step(2), _step(3, "failed")], total_steps=5)
    assert analyze_sidecar(payload).pass_depth == 2 / 5
    assert analyze_sidecar(payload).total_steps == 5


def test_failure_breakdown_and_explicit_false_positive(tmp_path: Path) -> None:
    payloads = [
        _sidecar("locator", [_step(1, "failed", error="TimeoutError: waiting for locator('#buy')")]),
        _sidecar("assertion", [{**_step(1, "failed", error="AssertionError: expected text"), "type": "assertion"}]),
        _sidecar("navigation", [{**_step(1, "failed", error="net::ERR_CONNECTION_REFUSED"), "type": "navigate"}]),
        _sidecar("infra", [_step(1, "failed", error="TimeoutError: worker timed out")]),
        _sidecar("positive", [_step(1)], status="passed", false_positive=True),
    ]
    for payload in payloads:
        name = payload["test"]["name"]
        (tmp_path / f"{name}.evidence.json").write_text(json.dumps(payload), encoding="utf-8")
    metrics = analyze_sidecars(tmp_path)
    assert metrics.failure_class_breakdown == {
        "locator_failure": 1,
        "assertion_failure": 1,
        "navigation_failure": 1,
        "infrastructure_timeout_failure": 1,
    }
    assert metrics.false_positive_count == 1
    assert metrics.false_positive_rate == 1 / 5


def test_analyzer_accepts_explicit_sidecar_paths(tmp_path: Path) -> None:
    first = tmp_path / "first.evidence.json"
    second = tmp_path / "second.evidence.json"
    first.write_text(json.dumps(_sidecar("first", [_step(1)], status="passed")), encoding="utf-8")
    second.write_text(json.dumps(_sidecar("second", [_step(1)], status="passed")), encoding="utf-8")
    assert analyze_sidecars([first, second]).tests_analyzed == 2
    assert analyze_sidecars(first).tests_analyzed == 1


def test_corrupt_sidecars_are_counted_and_skipped(tmp_path: Path) -> None:
    (tmp_path / "bad.evidence.json").write_text("not json", encoding="utf-8")
    (tmp_path / "good.evidence.json").write_text(json.dumps(_sidecar("good", [], status="failed")), encoding="utf-8")
    metrics = analyze_sidecars(tmp_path)
    assert metrics.errors == 1
    assert metrics.tests_analyzed == 1
