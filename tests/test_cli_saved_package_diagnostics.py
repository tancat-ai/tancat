"""Tests for AI-026 Step 6: view_saved_package_diagnostics (persisted-package diagnostics).

Verifies that the CLI can display failure diagnostics for loaded saved packages,
including report paths, evidence paths, and per-test failure details.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.pipeline_runner import view_saved_package_diagnostics


class TestViewSavedPackageDiagnostics:
    """Test view_saved_package_diagnostics using real evidence files on disk."""

    def test_shows_no_evidence_message_when_empty(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """When package has no evidence files, shows informative message."""
        _write_manifest(tmp_path, reports=[], evidence_paths=[])
        view_saved_package_diagnostics(str(tmp_path))
        out = capsys.readouterr().out
        assert "No evidence files found" in out
        assert "No reports recorded" in out
        assert "No evidence paths recorded" in out

    def test_shows_report_paths_from_manifest(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """When package has reports in manifest, they are displayed."""
        reports = [
            {"format": "local", "path": "report_local.md", "generated_at": "2026-06-03T13:00:00"},
            {"format": "jira", "path": "report_jira.md", "generated_at": "2026-06-03T13:00:00"},
        ]
        _write_manifest(tmp_path, reports=reports, evidence_paths=[])
        view_saved_package_diagnostics(str(tmp_path))
        out = capsys.readouterr().out
        assert "Reports" in out
        assert "report_local.md" in out
        assert "report_jira.md" in out
        assert "local" in out
        assert "jira" in out

    def test_shows_evidence_paths_from_manifest(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """When package has evidence_paths in manifest, they are displayed."""
        evidence_paths = [
            "evidence/test_01_evidence.json",
            "evidence/test_02_evidence.json",
        ]
        _write_manifest(tmp_path, reports=[], evidence_paths=evidence_paths)
        view_saved_package_diagnostics(str(tmp_path))
        out = capsys.readouterr().out
        assert "evidence" in out.lower()
        assert "evidence_paths" in out.lower() or "test_01_evidence" in out

    def test_displays_failure_diagnostics_per_test(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """When evidence contains failed steps, diagnostics are displayed."""
        _write_manifest(tmp_path, reports=[], evidence_paths=[])
        _write_evidence(
            tmp_path,
            "test_01_login",
            {
                "test": {"status": "failed", "duration_s": 1.5},
                "page": {"url": "https://example.com/login"},
                "steps": [
                    {
                        "step": 1,
                        "type": "CLICK",
                        "label": "Login button",
                        "locator": "#login-btn",
                        "result": {
                            "status": "failed",
                            "error": "TimeoutError: timeout 30000ms exceeded",
                            "failure_note": "Element not found",
                            "diagnosis": {
                                "url": "https://example.com/login",
                                "title": "Login Page",
                                "suggested_locators": [],
                                "available_elements": [],
                            },
                        },
                    }
                ],
            },
        )
        view_saved_package_diagnostics(str(tmp_path))
        out = capsys.readouterr().out
        assert "test_01_login" in out
        assert "CLICK" in out
        assert "Login button" in out
        assert "#login-btn" in out

    def test_shows_no_failures_when_all_passed(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """When all tests pass, shows success message."""
        _write_manifest(tmp_path, reports=[], evidence_paths=[])
        _write_evidence(
            tmp_path,
            "test_01_login",
            {
                "test": {"status": "passed", "duration_s": 0.5},
                "page": {"url": "https://example.com/login"},
                "steps": [],
            },
        )
        view_saved_package_diagnostics(str(tmp_path))
        out = capsys.readouterr().out
        assert "No failures found" in out or "passed" in out.lower()

    def test_shows_multiple_evidence_files(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """When multiple evidence files exist, count is displayed."""
        _write_manifest(tmp_path, reports=[], evidence_paths=[])
        _write_evidence(
            tmp_path, "test_01", {"test": {"status": "passed"}, "page": {"url": "http://a.com"}, "steps": []}
        )
        _write_evidence(
            tmp_path, "test_02", {"test": {"status": "passed"}, "page": {"url": "http://a.com"}, "steps": []}
        )
        _write_evidence(
            tmp_path,
            "test_03",
            {
                "test": {"status": "failed"},
                "page": {"url": "http://x.com"},
                "steps": [
                    {
                        "step": 1,
                        "type": "FILL",
                        "label": "Field",
                        "locator": "#f",
                        "result": {"status": "failed", "error": "err", "diagnosis": None},
                    }
                ],
            },
        )
        view_saved_package_diagnostics(str(tmp_path))
        out = capsys.readouterr().out
        assert "3 evidence" in out or "3" in out


def _write_manifest(
    tmp_path: Path,
    reports: list[dict[str, str]],
    evidence_paths: list[str],
) -> None:
    """Write a minimal package_manifest.json."""
    manifest_path = tmp_path / "package_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "package_name": "test_package",
                "created_at": "2026-06-03T12:00:00+00:00",
                "source_story": "Test story",
                "starting_url": "https://example.com",
                "additional_urls": [],
                "provider": "ollama",
                "model": "qwen3.5:35b",
                "generated_test_files": ["test_01.py"],
                "page_object_files": [],
                "scrape_manifest_path": "scrape_manifest.json",
                "reports": reports,
                "evidence_paths": evidence_paths,
                "run_results_count": 1,
                "last_run_at": "2026-06-03T13:00:00",
            }
        )
    )


def _write_evidence(tmp_path: Path, test_name: str, data: dict[str, object]) -> None:
    """Write an evidence JSON file to the evidence/ subdirectory.

    Evidence files use the pattern: <test_name>.evidence.json
    """
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    (evidence_dir / f"{test_name}.evidence.json").write_text(json.dumps(data))


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
