"""Data preparation functions for report generation.

This module converts coverage analysis and run results into the list[dict] format
consumed by the renderers in report_formatters. Also contains shared private helpers.
"""

from __future__ import annotations

import html as _html
from typing import Any

from src.coverage_utils import RequirementCoverage
from src.pytest_output_parser import RunResult, TestResult


def escape_html(text: str) -> str:
    """Escape HTML special characters for safe embedding in HTML documents.

    Args:
        text: Raw text to escape

    Returns:
        HTML-escaped text with &, <, >, ", and ' character escaped
    """
    return _html.escape(text, quote=True)


def _normalise_test_name(name: str) -> str:
    """Return test name without pytest parameterization suffix."""
    return name.split("[", 1)[0]


def _find_matching_run_result(run_map: dict[str, TestResult], test_name: str) -> TestResult | None:
    """Find run result by exact, prefix, or de-parameterized test name."""
    direct = run_map.get(test_name)
    if direct is not None:
        return direct

    test_name_base = _normalise_test_name(test_name)
    for result_name, result in run_map.items():
        if result_name == test_name:
            return result
        if result_name.startswith(f"{test_name}["):
            return result
        if _normalise_test_name(result_name) == test_name_base:
            return result
    return None


def build_report_dicts(
    coverage_analysis: dict | None,
    run_result: RunResult | None,
) -> list[dict]:
    """Convert RequirementCoverage + RunResult to the dict format used by report_utils.

    Args:
        coverage_analysis: dict with "requirements" key containing RequirementCoverage list
        run_result: RunResult from pytest parser, or None

    Returns:
        List of dicts with keys: test_name, status, icon, tc_id, story_ref,
        expected_locators, actual_locators, matched_locators, run_status, run_result
    """
    if coverage_analysis is None:
        return []

    requirements = coverage_analysis.get("requirements", [])
    if not isinstance(requirements, list):
        return []

    # Build run result lookup
    run_map: dict[str, TestResult] = {}
    if run_result is not None and isinstance(run_result, RunResult):
        for tr in run_result.results:
            if isinstance(tr, TestResult):
                run_map[tr.name] = tr

    results: list[dict] = []
    for req in requirements:
        # Handle both RequirementCoverage objects and dicts
        if isinstance(req, RequirementCoverage):
            tc_id = req.id
            description = req.description
            cov_status = req.status
            linked_tests = req.linked_tests
        elif isinstance(req, dict):
            tc_id = str(req.get("id", req.get("tc_id", "")))
            description = str(req.get("description", req.get("test_name", "unknown")))
            cov_status = str(req.get("status", "unknown"))
            linked_tests = req.get("linked_tests", req.get("test_name", []))
            if isinstance(linked_tests, str):
                linked_tests = [linked_tests]
        else:
            continue

        # Pre-run status logic
        run: TestResult | None = None
        if run_result is None:
            if cov_status == "covered":
                status = "pending"
            else:
                status = "unknown"
        else:
            # Post-run: find matching test result by linked test names
            test_names = linked_tests if isinstance(linked_tests, list) else [linked_tests]
            for test_name in test_names:
                run = _find_matching_run_result(run_map, str(test_name))
                if run is not None:
                    status = run.status
                    break
            else:
                status = cov_status

        tc_id_display = str(tc_id)
        icon = _status_icon(status)

        results.append(
            {
                "test_name": description,
                "status": status,
                "icon": icon,
                "tc_id": tc_id_display,
                "story_ref": "",
                "expected_locators": linked_tests if isinstance(linked_tests, list) else [linked_tests],
                "actual_locators": [],
                "matched_locators": [],
                "run_status": run.status if run is not None else None,
                "run_result": run.error_message if run is not None else None,
                "duration": run.duration if run is not None else 0.0,
                "screenshots": [],
            }
        )

    return results


def _status_summary(coverage: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    """Return passed, failed, pending, unknown counts."""
    passed = failed = pending = unknown = 0
    for row in coverage:
        status = row.get("status", "unknown")
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        elif status == "pending":
            pending += 1
        else:
            unknown += 1
    return passed, failed, pending, unknown


def _status_icon(status: str) -> str:
    """Return icon for a row status."""
    icons = {
        "passed": "\U00002705",
        "failed": "\U0000274c",
        "pending": "\U000023f3",
        "unknown": "\U00002753",
    }
    return icons.get(status, "\U00002753")
