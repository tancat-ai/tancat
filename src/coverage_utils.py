"""Utilities for requirement coverage analysis.

This module centralises the logic for turning acceptance criteria and
generated test code into structured coverage information that can be
reused by different frontends (Streamli UI, CLI, reports).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class RequirementCoverage:
    """Track coverage for a single requirement."""

    id: str
    description: str
    status: str  # "not_covered", "covered", "partial"
    linked_tests: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a serialisable representation of this requirement."""
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "linked_tests": list(self.linked_tests),
        }


class CoverageRunResult(Protocol):
    """Protocol for minimal test-run result objects used in coverage mapping."""

    name: str
    status: str
    duration: float


@dataclass
class CoverageDisplayRow:
    """Display-compatible coverage row for UI tables."""

    id_cell: str
    requirement: str
    status: str
    tests: str
    result: str
    runtime: str = ""
    has_evidence: bool = False

    def to_dict(self) -> dict[str, str]:
        """Convert row into a Streamlit dataframe-friendly dictionary."""
        return {
            "ID": self.id_cell,
            "Requirement": self.requirement,
            "Status": self.status,
            "Tests": self.tests,
            "Result": self.result,
            "Runtime": self.runtime,
            "Evidence": "📸" if self.has_evidence else "",
        }


_TEST_DEF_pattern = re.compile(r"^def (test_\w+)", re.MULTILINE)


def extract_test_names(generated_code: str) -> list[str]:
    """Extract pytest-style test function names from Python source code."""
    if not generated_code:
        return []
    return _TEST_DEF_pattern.findall(generated_code)


def _get_base_test_name(name: str) -> str:
    """Strip browser markers and path separators to get the core test name."""
    # Handle full pytest node IDs like "path/to/test_file.py::test_name[chromium]"
    if "::" in name:
        name = name.split("::")[-1]
    # Extract just the filename if there's a path (e.g., "path/to/test_name.py" -> "test_name.py")
    if "/" in name or "\\" in name:
        name = name.split("/")[-1].split("\\")[-1]
    # Strip file extension if present (e.g., "test_name.py" -> "test_name")
    if name.endswith(".py"):
        name = name[:-3]
    # Strip browser markers and parametrize suffixes
    return name.split("[")[0].split("(")[0].strip()


def _extract_criterion_number(test_name: str) -> int | None:
    """Extract the criterion number from a test function name.

    Test names follow the convention::

        test_<prefix><criterion_number>_<description>

    where ``<prefix>`` is optional letters+digits (e.g. ``TC01_``, ``tc01_``, ``tc01``)
    and ``<criterion_number>`` is a 1-2 digit number followed by ``_``.

    The criterion number is the LAST ``<1-2 digit number>_`` segment in the test name.
    This handles both ``test_tc01_02_...`` (separator before criterion number)
    and ``test_tc0108_...`` (no separator before criterion number, leading zero
    is stripped so ``08`` → ``8``).
    """
    matches = list(re.finditer(r"(\d{1,2})_", test_name))
    if not matches:
        return None
    return int(matches[-1].group(1))


def build_requirement_coverages(
    acceptance_criteria_lines: list[str],
    generated_code: str,
) -> list[RequirementCoverage]:
    """Build RequirementCoverage objects from criteria and generated test code."""
    test_names_in_code = extract_test_names(generated_code)

    requirements: list[RequirementCoverage] = []
    for index, criterion in enumerate(acceptance_criteria_lines, start=1):
        req_id = f"TC-{index:03d}"

        linked = []
        for name in test_names_in_code:
            criterion_num = _extract_criterion_number(name)
            if criterion_num is not None and criterion_num == index:
                linked.append(name)

        if not linked:
            words = {word for word in criterion.lower().split() if len(word) > 3}
            for name in test_names_in_code:
                test_words = set(name.lower().replace("_", " ").split())
                if words and (words & test_words):
                    linked.append(name)

        status = "covered" if linked else "not_covered"
        requirements.append(
            RequirementCoverage(
                id=req_id,
                description=criterion,
                status=status,
                linked_tests=linked,
            )
        )
    return requirements


def build_coverage_analysis(
    acceptance_criteria_lines: list[str],
    generated_code: str,
) -> dict[str, list[RequirementCoverage]]:
    """Return the coverage analysis dict used by UIs and report builders."""
    return {"requirements": build_requirement_coverages(acceptance_criteria_lines, generated_code)}


def _status_emoji(status: str) -> str:
    """Return a visual status marker for requirement coverage status."""
    if status == "covered":
        return "✅"
    if status == "partial":
        return "⚠️"
    return "❌"


def _result_icon(status: str) -> str:
    """Return a visual status marker for test execution result."""
    if status == "passed":
        return "✅"
    if status == "failed":
        return "❌"
    if status == "skipped":
        return "⏭️"
    return "⏳"


def build_coverage_display_rows(
    requirements: list[RequirementCoverage],
    run_results: Sequence[CoverageRunResult] | None = None,
) -> list[CoverageDisplayRow]:
    """Build display-ready rows from RequirementCoverage objects."""
    # Build lookup maps for run results
    run_map: dict[str, str] = {}  # base_name -> status
    duration_map: dict[str, float] = {}  # base_name -> duration
    if run_results:
        for tr in run_results:
            base = _get_base_test_name(tr.name)
            run_map[base] = tr.status
            if tr.duration > 0:
                duration_map[base] = tr.duration

    rows: list[CoverageDisplayRow] = []
    for req in requirements:
        status_emoji = _status_emoji(req.status)
        id_cell = f"{status_emoji} {req.id}"
        status_label = req.status.upper()

        tests_cell = "; ".join(req.linked_tests[:3])
        if len(req.linked_tests) > 3:
            tests_cell += "..."

        result_cell = ""
        runtime_cell = ""
        has_evidence = False
        if run_results and req.linked_tests:
            icons: list[str] = []
            durations: list[float] = []
            for test_name in req.linked_tests:
                base = _get_base_test_name(test_name)
                if base in run_map:
                    icons.append(_result_icon(run_map[base]))
                    if base in duration_map:
                        durations.append(duration_map[base])
                else:
                    icons.append(_result_icon("not_run"))
            # Aggregate into a single status icon (worst-case semantics):
            # any failure → ❌, any skip and no failure → ⏭️, all passed → ✅
            if icons:
                if any(icon == "❌" for icon in icons):
                    result_cell = "❌"
                elif any(icon == "⏭️" for icon in icons):
                    result_cell = "⏭️"
                elif all(icon == "✅" for icon in icons):
                    result_cell = "✅"
                else:
                    result_cell = "⏳"
            if durations:
                avg_duration = sum(durations) / len(durations)
                runtime_cell = f"{avg_duration:.2f}s"
            # Evidence is available if any linked test has been run
            has_evidence = any(base in run_map for base in [_get_base_test_name(t) for t in req.linked_tests])
        elif not req.linked_tests:
            result_cell = "N/A"

        rows.append(
            CoverageDisplayRow(
                id_cell=id_cell,
                requirement=req.description,
                status=status_label,
                tests=tests_cell,
                result=result_cell,
                runtime=runtime_cell,
                has_evidence=has_evidence,
            )
        )

    return rows
