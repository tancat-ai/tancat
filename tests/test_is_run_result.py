"""Unit tests for the reload-safe RunResult check (B-044)."""

from __future__ import annotations

from dataclasses import make_dataclass

from src.pytest_output_parser import RunResult, TestResult, is_run_result


def test_real_run_result_passes() -> None:
    rr = RunResult(results=[], total=14, passed=14)
    assert is_run_result(rr) is True


def test_reloaded_class_still_passes() -> None:
    """Simulate Streamlit's module reload: a class with the same name/shape
    but a DIFFERENT class object than the imported RunResult."""
    ReloadedRunResult = make_dataclass("RunResult", [("results", list), ("total", int), ("passed", int)])
    stale = ReloadedRunResult(results=[], total=7, passed=7)
    assert isinstance(stale, RunResult) is False  # isinstance fails after reload
    assert is_run_result(stale) is True  # duck-type check passes


def test_non_run_result_fails() -> None:
    assert is_run_result(None) is False
    assert is_run_result("RunResult") is False
    assert is_run_result({"results": [], "total": 1}) is False
    assert is_run_result(RunResult()) is True


def test_test_result_does_not_pass() -> None:
    assert is_run_result(TestResult(name="x", status="passed", duration=0.0, error_message="", file_path="")) is False
