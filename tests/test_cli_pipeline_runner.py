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
    _display_test_rows_table,
    _edit_test_row_interactive,
    _select_conditions_for_generation,
    build_test_table_interactive,
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


# ── Test Table (AI-034 Phase 2) ─────────────────────────────────────────


class TestTestTableInteractive:
    """Cover the interactive test-table flow with mocked prompts."""

    @staticmethod
    def _session() -> Session:
        from src.spec_analyzer import TestCondition
        from src.test_plan import TestPlan

        session = Session()
        session.test_plan = TestPlan.from_conditions(
            story_ref="story_x",
            sprint="Backlog",
            conditions=[
                TestCondition(
                    id="TC01.03",
                    type="happy_path",
                    text="filters — A-Z, Z-A",
                    expected="Works",
                    source="AC 3",
                    src="manual",
                )
            ],
        )
        session.plan_confirmed = True
        session.provider = "ollama"
        session.provider_base_url = "http://localhost:11434"
        session.model_name = "qwen3"
        return session

    @staticmethod
    def _expanded_table() -> object:
        from src.test_table import TestRow, TestTable

        return TestTable(
            rows=[
                TestRow(id="T01", condition_ref="TC01.03", intent="Filter A-Z", expected_action="SELECT"),
                TestRow(id="T02", condition_ref="TC01.03", intent="Filter Z-A", expected_action="SELECT"),
            ],
            confirmed_ids=set(),
        )

    def test_confirm_all_rows_sets_confirmed(self, capsys: pytest.CaptureFixture) -> None:
        session = self._session()
        with (
            patch("src.cli.pipeline_runner.ui_build_test_table", return_value=self._expanded_table()),
            patch("src.cli.pipeline_runner.print_menu", return_value=2),
        ):
            build_test_table_interactive(session)

        assert session.test_table is not None
        assert session.test_table_confirmed is True
        assert len(session.test_table.rows) == 2  # type: ignore[union-attr]
        captured = capsys.readouterr()
        assert "confirmed" in captured.out

    def test_skip_leaves_table_unconfirmed(self, capsys: pytest.CaptureFixture) -> None:
        session = self._session()
        with (
            patch("src.cli.pipeline_runner.ui_build_test_table", return_value=self._expanded_table()),
            patch("src.cli.pipeline_runner.print_menu", return_value=3),
        ):
            build_test_table_interactive(session)

        assert session.test_table is not None
        assert session.test_table_confirmed is False
        captured = capsys.readouterr()
        assert "not confirmed" in captured.out

    def test_requires_signed_off_plan(self, capsys: pytest.CaptureFixture) -> None:
        session = self._session()
        session.plan_confirmed = False
        with patch("src.cli.pipeline_runner.ui_build_test_table") as mock_build:
            build_test_table_interactive(session)
        mock_build.assert_not_called()
        assert session.test_table is None
        captured = capsys.readouterr()
        assert "not signed off" in captured.out

    def test_requires_plan_to_exist(self, capsys: pytest.CaptureFixture) -> None:
        session = Session()
        session.plan_confirmed = True
        build_test_table_interactive(session)
        assert session.test_table is None
        captured = capsys.readouterr()
        assert "No plan" in captured.out

    def test_llm_failure_falls_back_to_conditions(self, capsys: pytest.CaptureFixture) -> None:
        """Expansion failure must not crash the CLI — proceed without a table."""
        session = self._session()
        with patch("src.cli.pipeline_runner.ui_build_test_table", side_effect=RuntimeError("LLM down")):
            build_test_table_interactive(session)
        assert session.test_table is None
        captured = capsys.readouterr()
        assert "Could not expand" in captured.out

    def test_display_rows_table_prints_rows(self, capsys: pytest.CaptureFixture) -> None:
        _display_test_rows_table(self._expanded_table())
        captured = capsys.readouterr()
        assert "T01" in captured.out
        assert "T02" in captured.out
        assert "Filter A-Z" in captured.out

    def test_edit_test_row_updates_intent(self, capsys: pytest.CaptureFixture) -> None:
        session = self._session()
        session.test_table = self._expanded_table()  # type: ignore[assignment]
        with (
            patch(
                "src.cli.pipeline_runner.print_menu",
                side_effect=[0, 0, 3],  # row 0 → Intent field → Done
            ),
            patch("src.cli.pipeline_runner.read_optional", return_value="Filter A-Z (edited)"),
        ):
            _edit_test_row_interactive(session)

        assert session.test_table is not None
        edited = session.test_table.rows[0]
        assert edited.intent == "Filter A-Z (edited)"
        assert edited.id == "T01"


class TestSelectConditionsForGeneration:
    """AI-034 Phase 3 — confirmed test rows win over raw plan conditions."""

    @staticmethod
    def _session_with_plan() -> Session:
        from src.spec_analyzer import TestCondition
        from src.test_plan import TestPlan

        session = Session()
        session.test_plan = TestPlan.from_conditions(
            story_ref="story",
            sprint="Backlog",
            conditions=[
                TestCondition(
                    id="TC01.03", type="happy_path", text="filters", expected="ok", source="AC", src="manual"
                ),
            ],
        )
        session.pipeline_conditions = list(session.test_plan.conditions)
        return session

    def test_confirmed_table_beats_plan_conditions(self) -> None:
        from src.test_table import TestRow, TestTable

        session = self._session_with_plan()
        session.test_table = TestTable(
            rows=[
                TestRow(id="T01", condition_ref="TC01.03", intent="Filter A-Z", expected_action="SELECT"),
                TestRow(id="T02", condition_ref="TC01.03", intent="Filter Z-A", expected_action="SELECT"),
            ],
            confirmed_ids={"T01", "T02"},
        )
        conditions = _select_conditions_for_generation(session)
        assert [c.id for c in conditions] == ["T01", "T02"]

    def test_partial_confirmation_skips_unconfirmed_rows(self) -> None:
        from src.test_table import TestRow, TestTable

        session = self._session_with_plan()
        session.test_table = TestTable(
            rows=[
                TestRow(id="T01", condition_ref="TC01.03", intent="Filter A-Z"),
                TestRow(id="T02", condition_ref="TC01.03", intent="Filter Z-A"),
            ],
            confirmed_ids={"T02"},
        )
        conditions = _select_conditions_for_generation(session)
        assert [c.id for c in conditions] == ["T02"]

    def test_no_table_uses_pipeline_conditions(self) -> None:
        session = self._session_with_plan()
        conditions = _select_conditions_for_generation(session)
        assert [c.id for c in conditions] == ["TC01.03"]

    def test_no_table_no_pipeline_conditions_uses_plan(self) -> None:
        session = self._session_with_plan()
        session.pipeline_conditions = []
        conditions = _select_conditions_for_generation(session)
        assert [c.id for c in conditions] == ["TC01.03"]


class TestStorySlug:
    """Session.story_slug — the export flow referenced it without defining it."""

    def test_empty_when_no_requirements(self) -> None:
        session = Session()
        assert session.story_slug == ""

    def test_slugified_from_raw_requirements(self) -> None:
        session = Session()
        session.raw_requirements = "As a shopper I want to view product details on the store"
        assert session.story_slug == "as_a_shopper_i_want_to_view_product_details_on_the"


class TestExportCleanPackage:
    """export_clean_package must not raise AttributeError on story_slug."""

    def test_export_calls_service_with_story_slug(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        session = Session()
        pkg = tmp_path / "test_20260802_120000_as_a_shopper"
        pkg.mkdir()
        session.pipeline_saved_path = str(pkg)
        session.raw_requirements = "As a shopper I want to view product details"

        fake_result = SimpleNamespace(summary=lambda: "Exported OK")

        with (
            patch("src.cli.menu_renderer.print_menu", return_value=0),
            patch("src.cli.pipeline_runner.export_clean_suite", return_value=fake_result) as mock_export,
            patch("builtins.input", return_value=""),
        ):
            from src.cli.pipeline_runner import export_clean_package

            export_clean_package(session)

        mock_export.assert_called_once()
        _, kwargs = mock_export.call_args
        assert kwargs["story_slug"] == "as_a_shopper_i_want_to_view_product_details"


class TestExportSourceNormalization:
    """export_clean_package must derive the package dir when the saved path is the test file."""

    def test_file_saved_path_resolves_to_package_dir(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        session = Session()
        pkg = tmp_path / "test_20260802_120000_as_a_shopper"
        pkg.mkdir()
        test_file = pkg / "test_as_a_shopper.py"
        test_file.write_text("def test_x():\n    pass\n", encoding="utf-8")
        # ui_pipeline stores the artifact FILE path — the bug that produced
        # "Tests: 0 / Page Objects: 0" exports.
        session.pipeline_saved_path = str(test_file)
        session.raw_requirements = "As a shopper I want to view product details"

        fake_result = SimpleNamespace(summary=lambda: "Exported OK")

        with (
            patch("src.cli.menu_renderer.print_menu", return_value=0),
            patch("src.cli.pipeline_runner.export_clean_suite", return_value=fake_result) as mock_export,
            patch("builtins.input", return_value=""),
        ):
            from src.cli.pipeline_runner import export_clean_package

            export_clean_package(session)

        mock_export.assert_called_once()
        args, kwargs = mock_export.call_args
        assert Path(kwargs["source_package_dir"]) == pkg

    def test_dir_saved_path_passed_through(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        session = Session()
        pkg = tmp_path / "test_pkg_dir"
        pkg.mkdir()
        session.pipeline_saved_path = str(pkg)

        fake_result = SimpleNamespace(summary=lambda: "Exported OK")

        with (
            patch("src.cli.menu_renderer.print_menu", return_value=0),
            patch("src.cli.pipeline_runner.export_clean_suite", return_value=fake_result) as mock_export,
            patch("builtins.input", return_value=""),
        ):
            from src.cli.pipeline_runner import export_clean_package

            export_clean_package(session)

        mock_export.assert_called_once()
        _, kwargs = mock_export.call_args
        assert Path(kwargs["source_package_dir"]) == pkg
