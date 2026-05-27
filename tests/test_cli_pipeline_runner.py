"""Tests for cli/pipeline_runner.py — pure functions and display helpers.

Focus on testable units without requiring async pipeline execution or
interactive prompts. The async run_pipeline and build_test_plan functions
are exercised indirectly through their internal helpers.
"""

from __future__ import annotations

import pytest

from cli.pipeline_runner import (
    display_run_results,
    parse_requirements,
    parse_target_urls,
)
from cli.session import Session
from src.pytest_output_parser import RunResult

# ── parse_target_urls ───────────────────────────────────────────────────


class TestParseTargetUrls:
    def test_single_base_url_only(self) -> None:
        urls = parse_target_urls("http://example.com", "")
        assert urls == ["http://example.com"]

    def test_base_url_plus_additional_lines(self) -> None:
        urls = parse_target_urls(
            "http://example.com",
            "http://example.com/login\nhttp://example.com/cart",
        )
        assert urls == [
            "http://example.com",
            "http://example.com/login",
            "http://example.com/cart",
        ]

    def test_base_url_not_duplicated_when_in_additional(self) -> None:
        urls = parse_target_urls(
            "http://example.com",
            "http://example.com\nhttp://example.com/cart",
        )
        assert urls == ["http://example.com", "http://example.com/cart"]

    def test_empty_base_url_uses_additional_only(self) -> None:
        urls = parse_target_urls("", "http://example.com/cart")
        assert urls == ["http://example.com/cart"]

    def test_blank_lines_stripped(self) -> None:
        urls = parse_target_urls("", "\n  \nhttp://example.com\n  \n")
        assert urls == ["http://example.com"]

    def test_whitespace_stripped_from_urls(self) -> None:
        urls = parse_target_urls("  http://example.com  ", "  http://extra.com  ")
        assert urls == ["http://example.com", "http://extra.com"]


# ── parse_requirements ──────────────────────────────────────────────────


class TestParseRequirements:
    def test_simple_story_returns_itself(self) -> None:
        story, criteria = parse_requirements("As a user I want to login")
        assert story == "As a user I want to login"
        # FeatureParser.build_requirement_model numbers criteria
        assert "As a user I want to login" in criteria

    def test_story_with_criteria_separated_by_newline(self) -> None:
        raw = "As a user I want to login\nGiven I am on the login page\nWhen I enter credentials\nThen I am logged in"
        story, criteria = parse_requirements(raw)
        assert story is not None
        assert criteria is not None
        assert len(story) > 0
        assert len(criteria) > 0

    def test_empty_input_returns_empty(self) -> None:
        story, criteria = parse_requirements("")
        assert story == ""
        assert criteria == ""


# ── display_run_results ─────────────────────────────────────────────────


class TestDisplayRunResults:
    def test_displays_passed_results(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.pipeline_run_result = RunResult(
            total=5,
            passed=5,
            failed=0,
            skipped=0,
            errors=0,
        )
        session.pipeline_run_command = "pytest -v"

        display_run_results(session)

        captured = capsys.readouterr()
        assert "Total: 5" in captured.out
        assert "Passed: 5" in captured.out

    def test_displays_failed_results(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.pipeline_run_result = RunResult(
            total=3,
            passed=1,
            failed=2,
            skipped=0,
            errors=0,
        )

        display_run_results(session)

        captured = capsys.readouterr()
        assert "Failed: 2" in captured.out

    def test_displays_no_results_message(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.pipeline_run_result = None

        display_run_results(session)

        captured = capsys.readouterr()
        assert "No test results" in captured.out

    def test_shows_pytest_output_when_available(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.pipeline_run_result = RunResult(total=1, passed=1, failed=0, skipped=0, errors=0)
        session.pipeline_run_output = "test_passed OK"

        display_run_results(session)

        captured = capsys.readouterr()
        assert "Pytest Output" in captured.out
        assert "test_passed OK" in captured.out

    def test_shows_collection_error_warning(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.pipeline_run_result = RunResult(total=0, passed=0, failed=0, skipped=0, errors=1)

        display_run_results(session)

        captured = capsys.readouterr()
        assert "collection or import error" in captured.out
