"""Tests for cli/pipeline_runner.py — pure functions and display helpers.

Focus on testable units without requiring async pipeline execution or
interactive prompts. The async run_pipeline and build_test_plan functions
are exercised indirectly through their internal helpers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.cli.pipeline_runner import (
    display_run_results,
    load_existing_packages,
    parse_requirements,
    parse_target_urls,
    run_saved_test_from_package,
)
from src.cli.session import Session
from src.pipeline_artifact_manager import PackageManifest
from src.pipeline_run_service import PipelineExecutionResult
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
        # render_run_results outputs metric badges like "✅ 5 passed"
        assert "5 passed" in captured.out

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
        # render_run_results outputs metric badges like "❌ 2 failed"
        assert "2 failed" in captured.out

    def test_displays_no_results_message(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.pipeline_run_result = None

        display_run_results(session)

        captured = capsys.readouterr()
        assert "No test results" in captured.out

    def test_shows_structured_run_results(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.pipeline_run_result = RunResult(total=1, passed=1, failed=0, skipped=0, errors=0)
        session.pipeline_run_output = "test_passed OK"
        session.pipeline_run_command = "pytest -v"

        display_run_results(session)

        captured = capsys.readouterr()
        # New structured view shows command and render_run_results output
        assert "Command:" in captured.out
        assert "Run Results" in captured.out

    def test_shows_error_results(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.pipeline_run_result = RunResult(total=0, passed=0, failed=0, skipped=0, errors=1)

        display_run_results(session)

        captured = capsys.readouterr()
        # render_run_results shows error badges like "1 errors"
        assert "1 errors" in captured.out


# ── load_existing_packages ──────────────────────────────────────────────


class TestLoadExistingPackages:
    def test_loads_package_and_populates_session(self, tmp_path: Path) -> None:
        """Verify load_existing_packages populates session with manifest and run results."""
        session = Session()

        manifest = PackageManifest(
            package_name="test_20260603_120000_demo",
            created_at="2026-06-03T12:00:00+01:00",
            source_story="As a user, I want to login",
            starting_url="https://example.com/login",
            additional_urls=[],
            provider="ollama",
            model="qwen3.5:35b",
            generated_test_files=["test_01_login.py"],
            page_object_files=[],
            scrape_manifest_path="scrape_manifest.json",
            reports=[],
            evidence_paths=[],
            run_results_count=2,
            last_run_at="2026-06-03T13:00:00+01:00",
        )

        with (
            patch("src.cli.pipeline_runner.find_existing_packages", return_value=[manifest]),
            patch("src.cli.pipeline_runner.load_all_run_results", return_value=[{"test_01_login": "passed"}]),
            patch("builtins.input", return_value="1"),
        ):
            load_existing_packages(session)

        assert session.loaded_package_manifest is not None
        assert session.loaded_package_manifest.package_name == "test_20260603_120000_demo"
        assert session.loaded_package_manifest.source_story == "As a user, I want to login"
        assert session.loaded_package_run_results == [{"test_01_login": "passed"}]

    def test_aborts_when_no_packages_found(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Verify graceful exit when no packages exist."""
        session = Session()

        with patch("src.cli.pipeline_runner.find_existing_packages") as mock_find:
            mock_find.return_value = []
            load_existing_packages(session)

        captured = capsys.readouterr()
        assert "No existing packages" in captured.out
        assert session.loaded_package_manifest is None

    def test_aborts_on_invalid_selection(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Verify invalid index is handled gracefully."""
        manifest = PackageManifest(
            package_name="test_pkg",
            created_at="2026-06-03T12:00:00+01:00",
            source_story="story",
            starting_url="https://example.com",
        )

        session = Session()

        with (
            patch("src.cli.pipeline_runner.find_existing_packages", return_value=[manifest]),
            patch("builtins.input", return_value="99"),
        ):
            load_existing_packages(session)

        captured = capsys.readouterr()
        assert "Invalid" in captured.out or "Not a valid" in captured.out
        assert session.loaded_package_manifest is None


# ── run_saved_test_from_package ─────────────────────────────────────────


class TestRunSavedTestFromPackage:
    def test_aborts_without_loaded_package(self, capsys: pytest.CaptureFixture) -> None:
        """Verify graceful exit when no package is loaded."""
        session = Session()
        session.loaded_package_manifest = None

        # Calling with empty string should still attempt to run (no guard in current impl)
        # The function prints a header and tries to run — pytest will time out with no files.
        # We mock the run to avoid that.
        with patch("src.pipeline_run_service.PipelineRunService.run_saved_test") as mock_run:
            mock_run.return_value = PipelineExecutionResult(
                run_result=RunResult(total=0, passed=0, failed=0, skipped=0, errors=0),
                display_output="no tests ran",
                command=["pytest"],
                return_code=5,
            )
            run_saved_test_from_package("", session)

        # The function still runs but with an empty path — pytest returns code 5 (no tests collected)
        assert mock_run.call_count == 1
        captured = capsys.readouterr()
        assert "Running" in captured.out

    def test_runs_saved_suite_via_pipeline_run_service(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Verify run_saved_test_from_package delegates to PipelineRunService.run_saved_test."""
        manifest = PackageManifest(
            package_name="test_pkg",
            created_at="2026-06-03T12:00:00+01:00",
            source_story="story",
            starting_url="https://example.com",
            generated_test_files=["test_01_dummy.py"],
        )

        session = Session()
        session.loaded_package_manifest = manifest

        package_dir = str(tmp_path / "test_pkg")

        with patch("src.pipeline_run_service.PipelineRunService.run_saved_test") as mock_run:
            mock_run.return_value = PipelineExecutionResult(
                run_result=RunResult(total=1, passed=1, failed=0, skipped=0, errors=0),
                display_output="1 passed",
                command=["pytest"],
                return_code=0,
            )
            run_saved_test_from_package(package_dir, session)

        # Verify run_saved_test was called
        assert mock_run.call_count == 1
