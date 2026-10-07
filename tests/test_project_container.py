"""Project container: the workspace promoted to a named project (t-0510).

An unset project keeps today's behaviour - the ``default`` workspace and the
host[:port] RAG scope - so the new surface is ignorable. A named project sets
``AITEST_RAG_SCOPE`` (per-project learned patterns) and "Run Project" runs every
package in the workspace.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.pipeline_run_service import (
    PipelineExecutionResult,
    discover_project_packages,
    run_project_packages,
)
from src.project import apply_rag_scope, project_display_name, project_workspace, rag_scope_for
from src.pytest_output_parser import RunResult, TestResult

URL = "http://localhost:8781/generated_tests/mock.html"


class TestProjectName:
    def test_unset_project_defaults_to_the_host(self) -> None:
        assert project_display_name("", URL) == "localhost:8781"

    def test_unset_project_without_a_url_is_the_default(self) -> None:
        assert project_display_name("") == "default"

    def test_stored_project_wins(self) -> None:
        assert project_display_name("acme", URL) == "acme"

    def test_unset_project_keeps_the_default_workspace(self) -> None:
        assert project_workspace("") == "default"
        assert project_workspace("acme") == "acme"


class TestProjectRagScope:
    def test_named_project_sets_the_rag_scope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AITEST_RAG_SCOPE", raising=False)
        assert rag_scope_for("acme") == "acme"
        assert apply_rag_scope("acme") == "acme"
        assert os.environ["AITEST_RAG_SCOPE"] == "acme"

        from src.rag_learn import effective_site_identity

        assert effective_site_identity(URL) == "scope:acme"

    def test_unset_project_uses_the_host_scope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AITEST_RAG_SCOPE", "stale")
        assert rag_scope_for("") is None
        assert apply_rag_scope("") is None
        assert "AITEST_RAG_SCOPE" not in os.environ

        from src.rag_learn import effective_site_identity

        assert effective_site_identity(URL) == "localhost:8781"

    def test_the_default_project_is_not_a_scope(self) -> None:
        assert rag_scope_for("default") is None


class _FakeRunService:
    """Records every package it is asked to run and returns one passing test."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_saved_test(self, saved_path: str, **_kwargs: object) -> PipelineExecutionResult:
        self.calls.append(str(saved_path))
        result = RunResult(
            results=[
                TestResult(
                    name=f"test_{Path(saved_path).name}",
                    status="passed",
                    duration=0.1,
                    error_message="",
                    file_path="",
                )
            ],
            total=1,
            passed=1,
        )
        return PipelineExecutionResult(command=[], run_result=result, display_output="ok", return_code=0)


class TestRunProject:
    def test_run_project_runs_every_package(self, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        for name in ("pkg_a", "pkg_b"):
            package = base / name
            package.mkdir(parents=True)
            (package / f"test_{name}.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")

        package_dirs = discover_project_packages(base)
        assert len(package_dirs) == 2

        fake = _FakeRunService()
        outcome = run_project_packages(package_dirs, run_service=fake)  # type: ignore[arg-type]

        assert sorted(fake.calls) == sorted(str(d) for d in package_dirs)
        assert outcome.package_count == 2
        assert outcome.run_result.total == 2
        assert outcome.run_result.passed == 2
        assert outcome.run_result.failed == 0

    def test_run_project_with_no_packages_is_empty(self, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        base.mkdir()
        assert discover_project_packages(base) == []
