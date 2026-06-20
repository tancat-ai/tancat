"""Unit tests for CLI test orchestrator."""

from __future__ import annotations

from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from src.analyzer import AnalyzedTestCase
from src.cli.input_parser import ParsedInput, TestCase
from src.cli.test_case_orchestrator import TestCaseOrchestrator
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


def test_build_feature_spec_request_extracts_numbered_acceptance_criteria() -> None:
    orchestrator = TestCaseOrchestrator(analysis_mode=AnalysisMode.FAST)
    raw_requirements = """## User Story
As a shopper I want to buy products so that I can check out.

## Acceptance Criteria
1. Open the home page
2. Add an item to the cart
"""

    result = orchestrator._build_feature_spec_request(raw_requirements)

    assert result is not None
    user_story, conditions_text = result
    assert user_story == "As a shopper I want to buy products so that I can check out."
    assert conditions_text == "1. Open the home page\n2. Add an item to the cart"


def test_process_parsed_uses_output_dir_from_caller(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    orchestrator = TestCaseOrchestrator(analysis_mode=AnalysisMode.FAST)
    parsed = ParsedInput(
        test_cases=[TestCase(title="Main Flow", description="As a user I want to log in so that I can continue.")],
        source_format="plain_text",
        raw_input="As a user I want to log in so that I can continue.",
    )

    captured: dict[str, str] = {}

    def fake_generate_test_files(
        cases: list[AnalyzedTestCase],
        url: str | None = None,
        output_dir: str = "",
        raw_requirements: str = "",
    ) -> list[str]:
        captured["output_dir"] = output_dir
        return [str(tmp_path / "generated.py")]

    monkeypatch.setattr(orchestrator, "_generate_test_files", fake_generate_test_files)

    result = orchestrator.process_parsed(parsed, output_dir=str(tmp_path))

    assert result.generated_files == [str(tmp_path / "generated.py")]
    assert captured["output_dir"] == str(tmp_path)
