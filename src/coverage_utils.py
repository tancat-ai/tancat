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

    def to_dict(self) -> dict[str, str]:
        """Convert row into a Streamlit dataframe-friendly dictionary."""
        return {
            "ID": self.id_cell,
            "Requirement": self.requirement,
            "Status": self.status,
            "Tests": self.tests,
            "Result": self.result,
        }


_TEST_DEF_pattern = re.compile(r"^def (test_\w+)", re.MULTILINE)


def extract_test_names(generated_code: str) -> list[str]:
    """Extract pytest-style test function names from Python source code."""
    if not generated_code:
        return []
    return _TEST_DEF_pattern.findall(generated_code)


def _get_base_test_name(name: str) -> str:
    """Strip browser markers and path separators to get the core test name."""
    clean = name.split("::")[-1]
    return clean.split("[")[0].split("(")[0].strip()


def build_requirement_coverages(
    acceptance_criteria_lines: list[str],
    generated_code: str,
) -> list[RequirementCoverage]:
    """Build RequirementCoverage objects from criteria and generated test code."""
    test_names_in_code = extract_test_names(generated_code)

    requirements: list[RequirementCoverage] = []
    for index, criterion in enumerate(acceptance_criteria_lines, start=1):
        req_id = f"TC-{index:03d}"
        prefix_p, prefix_s = f"test_{index:02d}_", f"test_{index}_"

        linked = []
        for name in test_names_in_code:
            if name.startswith(prefix_p) or name.startswith(prefix_s):
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
    run_map: dict[str, str] = {}
    if run_results:
        for tr in run_results:
            base = _get_base_test_name(tr.name)
            run_map[base] = tr.status

    rows: list[CoverageDisplayRow] = []
    for req in requirements:
        status_emoji = _status_emoji(req.status)
        id_cell = f"{status_emoji} {req.id}"
        status_label = req.status.upper()

        tests_cell = "; ".join(req.linked_tests[:3])
        if len(req.linked_tests) > 3:
            tests_cell += "..."

        result_cell = ""
        if run_results and req.linked_tests:
            icons: list[str] = []
            for test_name in req.linked_tests:
                base = _get_base_test_name(test_name)
                if base in run_map:
                    icons.append(_result_icon(run_map[base]))
                else:
                    icons.append(_result_icon("not_run"))
            result_cell = ", ".join(icons)
        elif not req.linked_tests:
            result_cell = "N/A"

        rows.append(
            CoverageDisplayRow(
                id_cell=id_cell,
                requirement=req.description,
                status=status_label,
                tests=tests_cell,
                result=result_cell,
            )
        )

    return rows
