"""Tests for the eval runner's test counts (d-0050).

A generated test that prints its own journey summary - "...: 1 ran, 0 passed." -
used to satisfy the console scan, so eval-002's 6 executed tests (2 failed, 4
passed, JUnit holding 6 cases) were recorded as "Tests: 0".

The counts now come from the JUnit XML the runner already receives; the console
is only a fallback, anchored to pytest's own final summary line.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from eval_runner import _counts_from_log, _test_counts  # noqa: E402

CARRY_ON = "test_02_add_item[chromium] PASSED\n  Journey summary: 1 ran, 0 passed.\n"
PYTEST_TAIL = "=========================== 4 passed, 2 failed in 131.00s (0:02:11) ===========================\n"

JUNIT_SIX_CASES_TWO_FAILED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="6" failures="2" errors="0" skipped="0">
    <testcase classname="test_eval_002" name="test_01_login[chromium]" time="1.0" />
    <testcase classname="test_eval_002" name="test_02_add_item[chromium]" time="1.0" />
    <testcase classname="test_eval_002" name="test_03_navigate_cart[chromium]" time="1.0">
      <failure message="page mismatch">ran on the wrong page</failure>
    </testcase>
    <testcase classname="test_eval_002" name="test_04_verify_item[chromium]" time="1.0" />
    <testcase classname="test_eval_002" name="test_05_checkout[chromium]" time="1.0">
      <failure message="timeout">locator not found</failure>
    </testcase>
    <testcase classname="test_eval_002" name="test_06_confirm[chromium]" time="1.0" />
  </testsuite>
</testsuites>
"""


def _junit(tmp_path: Path, body: str = JUNIT_SIX_CASES_TWO_FAILED) -> Path:
    path = tmp_path / "results.xml"
    path.write_text(body, encoding="utf-8")
    return path


def test_carry_on_line_before_the_pytest_summary_does_not_zero_the_counts(tmp_path: Path) -> None:
    """The regression: JUnit says 6 cases, the console starts with 0 passed."""
    output = CARRY_ON + PYTEST_TAIL
    total, passed, failed, skipped, duration, source = _test_counts(_junit(tmp_path), output)
    assert (total, passed, failed, skipped) == (6, 4, 2, 0)
    assert duration == pytest.approx(131.0)
    assert source == "junit"


def test_clean_log_is_unchanged(tmp_path: Path) -> None:
    output = "test_01_login[chromium] PASSED\ntest_02_add_item[chromium] FAILED\n" + PYTEST_TAIL
    total, passed, failed, skipped, duration, source = _test_counts(_junit(tmp_path), output)
    assert (total, passed, failed, skipped) == (6, 4, 2, 0)
    assert source == "junit"


def test_log_fallback_reads_pytest_summary_not_the_first_passed_line() -> None:
    """No JUnit: the console fallback must still ignore the carry-on line."""
    output = CARRY_ON + PYTEST_TAIL
    counts = _counts_from_log(output)
    assert counts[:4] == (6, 4, 2, 0)
    assert counts[4] == pytest.approx(131.0)


def test_no_summary_line_means_unknown_not_zero(tmp_path: Path) -> None:
    """A run with neither source says "none", so a zero is not a silent guess."""
    total, passed, failed, skipped, duration, source = _test_counts(tmp_path / "missing.xml", CARRY_ON)
    assert (total, passed, failed, skipped) == (0, 0, 0, 0)
    assert duration == 0.0
    assert source == "none"
