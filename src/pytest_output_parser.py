"""
pytest_output_parser.py — Parse raw pytest stdout into structured data.

Converts verbose pytest -v output into typed RunResult / TestResult objects
that the Streamlit UI can render as a readable results table.

No Streamlit imports — fully unit testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Regex patterns — matched against raw pytest -v output lines
# ---------------------------------------------------------------------------

# Note: We capture the test name, and optionally skip over the [browser] marker to find the status.
_PASSED_RE = re.compile(r"(\S+\.py)::([^\[\s]+)(?:\[[^\]]+\])?\s+PASSED")
_FAILED_RE = re.compile(r"(\S+\.py)::([^\[\s]+)(?:\[[^\]]+\])?\s+FAILED")
_SKIPPED_RE = re.compile(r"(\S+\.py)::([^\[\s]+)(?:\[[^\]]+\])?\s+SKIPPED")
_SUMMARY_LINE_RE = re.compile(r" in ([\d.]+)s(?: \([\d:]+\))?\s*=")
_PASSED_COUNT_RE = re.compile(r"(\d+) passed")
_FAILED_COUNT_RE = re.compile(r"(\d+) failed")
_SKIPPED_COUNT_RE = re.compile(r"(\d+) skipped")
_ERROR_COUNT_RE = re.compile(r"(\d+) error(?:s)?")
_ERROR_RE = re.compile(r"FAILED .+::(\S+) - (.+)")
_FAILURES_HEADER_RE = re.compile(r"^=+ FAILURES =+")
_FAILURE_NAME_RE = re.compile(r"^_+ (\w+) _+")
_ASSERTION_RE = re.compile(r"^(AssertionError|Error|Exception|TimeoutError): (.+)")

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    """Result for a single test function."""

    __test__ = False

    name: str
    status: str  # "passed" | "failed" | "skipped" | "error"
    duration: float  # seconds; 0.0 when not available
    error_message: str  # empty string when passed
    file_path: str  # relative path, e.g. "generated_tests/test_foo.py"


@dataclass
class RunResult:
    """Aggregated result for a full pytest run."""

    results: list[TestResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    raw_output: str = ""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_pytest_output(raw: str) -> RunResult:
    """Parse raw pytest -v stdout into a structured RunResult.

    Handles these pytest output patterns::

        # PASSED line
        generated_tests/test_foo.py::test_01_login_visible PASSED [ 33%]

        # FAILED line
        generated_tests/test_foo.py::test_02_inventory FAILED [100%]

        # Inline error summary (after FAILURES block header)
        FAILED generated_tests/test_foo.py::test_02_inventory - AssertionError: ...

        # FAILURES block (multi-line, contains assertion details)
        =================================== FAILURES ===================================
        __________________________ test_02_password_field ___________________________
        ...
        AssertionError: assert False == True

        # Duration line (last line of output)
        2 passed, 1 failed in 3.45s
        1 failed, 2 passed in 3.45s
        3 passed in 1.20s

    Args:
        raw: Complete stdout captured from subprocess pytest run.

    Returns:
        Populated RunResult. Never raises — returns empty RunResult on
        unparseable input so callers don't need to guard.
    """
    run = RunResult(raw_output=raw)
    results_by_name: dict[str, TestResult] = {}

    in_failures_block = False
    current_failed_name: str | None = None

    for line in raw.splitlines():
        # ── Detect entry into the FAILURES block ──────────────────────────
        if _FAILURES_HEADER_RE.search(line):
            in_failures_block = True
            continue

        # ── Inside FAILURES block: grab test name and error message ───────
        if in_failures_block:
            name_match = _FAILURE_NAME_RE.match(line)
            if name_match:
                current_failed_name = name_match.group(1)
                continue
            assertion_match = _ASSERTION_RE.match(line)
            if assertion_match and current_failed_name:
                if current_failed_name in results_by_name:
                    results_by_name[current_failed_name].error_message = assertion_match.group(2)
                continue

        # ── PASSED / FAILED test lines ────────────────────────────────────
        passed_match = _PASSED_RE.search(line)
        if passed_match:
            file_path, name = passed_match.group(1), passed_match.group(2)
            results_by_name[name] = TestResult(
                name=name,
                status="passed",
                duration=0.0,
                error_message="",
                file_path=file_path,
            )
            continue

        failed_match = _FAILED_RE.search(line)
        if failed_match:
            file_path, name = failed_match.group(1), failed_match.group(2)
            results_by_name[name] = TestResult(
                name=name,
                status="failed",
                duration=0.0,
                error_message="",
                file_path=file_path,
            )
            continue

        skipped_match = _SKIPPED_RE.search(line)
        if skipped_match:
            file_path, name = skipped_match.group(1), skipped_match.group(2)
            results_by_name[name] = TestResult(
                name=name,
                status="skipped",
                duration=0.0,
                error_message="",
                file_path=file_path,
            )
            continue

        # ── Inline error: "FAILED path::name - ErrorType: detail" ─────────
        error_match = _ERROR_RE.search(line)
        if error_match:
            name, message = error_match.group(1), error_match.group(2)
            if name in results_by_name:
                results_by_name[name].error_message = message
            continue

        # ── Final summary line ─────────────────────────────────────────────
        if _SUMMARY_LINE_RE.search(line):
            passed_m = _PASSED_COUNT_RE.search(line)
            failed_m = _FAILED_COUNT_RE.search(line)
            skipped_m = _SKIPPED_COUNT_RE.search(line)
            error_m = _ERROR_COUNT_RE.search(line)
            dur_m = re.search(r"in ([\d.]+)s", line)
            if passed_m:
                run.passed = int(passed_m.group(1))
            if failed_m:
                run.failed = int(failed_m.group(1))
            if skipped_m:
                run.skipped = int(skipped_m.group(1))
            if error_m:
                run.errors = int(error_m.group(1))
            if dur_m:
                run.duration = float(dur_m.group(1))

    run.results = list(results_by_name.values())

    if run.passed + run.failed == 0 and len(run.results) > 0:
        # Summary line wasn't parsed — derive counts from per-test entries
        run.passed = sum(1 for r in run.results if r.status == "passed")
        run.failed = sum(1 for r in run.results if r.status == "failed")
        run.skipped = sum(1 for r in run.results if r.status == "skipped")

    # Always derive total from the authoritative counts so Total == Passed + Failed + Skipped
    run.total = run.passed + run.failed + run.skipped

    return run


def format_pytest_output_for_display(raw: str, max_lines: int = 80) -> str:
    """Return a concise, high-signal pytest output snippet for UI display."""
    if not raw.strip():
        return ""

    kept_lines: list[str] = []
    seen_lines: set[str] = set()
    interesting_patterns = (
        "::test_",
        "FAILURES",
        "FAILED ",
        "AssertionError",
        "Error:",
        "Exception:",
        "TimeoutError:",
        "NameError:",
        "ERROR collecting",
        "short test summary info",
    )

    for line in raw.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue
        if clean_line.startswith(("platform ", "rootdir:", "plugins:", "configfile:", "cachedir:")):
            continue
        if clean_line.startswith(("Name ", "TOTAL ", "coverage:")):
            continue
        if clean_line.startswith(
            ("---------- coverage:", "----------- coverage:", "====================================")
        ):
            if "FAILURES" not in clean_line and "short test summary info" not in clean_line:
                continue

        is_interesting = any(pattern in clean_line for pattern in interesting_patterns)
        if not is_interesting and re.search(r"\b\d+\s+(passed|failed|error|errors)\b.*\bin\s+\d+\.\d+s", clean_line):
            is_interesting = True

        if is_interesting and clean_line not in seen_lines:
            kept_lines.append(clean_line)
            seen_lines.add(clean_line)

    if not kept_lines:
        fallback_lines = [line.strip() for line in raw.splitlines() if line.strip()]
        return "\n".join(fallback_lines[-max_lines:])

    return "\n".join(kept_lines[:max_lines])
