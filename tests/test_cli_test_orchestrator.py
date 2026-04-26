"""Unit tests for CLI test orchestrator."""

from __future__ import annotations

from cli.test_case_orchestrator import TestCaseOrchestrator
from src.analyzer import AnalyzedTestCase
from src.config import AnalysisMode


def _make_case(title: str, deps: list[str] | None = None, complexity: str = "medium") -> AnalyzedTestCase:
    return AnalyzedTestCase(
        title=title,
        description="desc",
        expected_outcome="outcome",
        preconditions=[],
        dependencies=deps or [],
        identified_expectations=[],
        suggested_data={},
        estimated_complexity=complexity,
        test_type="general",
    )


def test_order_test_cases_respects_dependencies_and_complexity() -> None:
    """Cases with dependencies should appear after their prerequisites."""
    orchestrator = TestCaseOrchestrator(analysis_mode=AnalysisMode.FAST)
    case_a = _make_case("Login")
    case_b = _make_case("Checkout", deps=["Depends on: Login"])
    ordered = orchestrator._order_test_cases([case_b, case_a])
    titles = [c.title for c in ordered]
    assert titles.index("Login") < titles.index("Checkout")


def test_order_test_cases_handles_no_dependencies() -> None:
    """When there are no dependencies, ordering falls back to complexity."""
    orchestrator = TestCaseOrchestrator(analysis_mode=AnalysisMode.FAST)
    low = _make_case("Low", complexity="low")
    high = _make_case("High", complexity="high")
    ordered = orchestrator._order_test_cases([high, low])
    titles = [c.title for c in ordered]
    assert titles[0] == "Low"
