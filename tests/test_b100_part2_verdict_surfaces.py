"""B-100 part 2: the runtime evidence sidecar and the reports carry the verdict.

Part 1 classified each test at emit time (verified_by_element /
verified_by_page_arrival / unverified + reason) and wrote it into the emitted
package. This file pins part 2:

1. ``EvidenceTracker`` reads ``verification_strength.json`` from the test
   package and stamps the verdict under ``test.verification`` in the sidecar.
2. The report surfaces (local markdown, Jira markdown, standalone HTML, local
   JSON) render the verdict, including the reason for an unverified criterion.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.coverage_utils import RequirementCoverage
from src.evidence_loader import (
    get_verification,
    load_verification_strength,
    match_verification_to_test,
)
from src.evidence_tracker import EvidenceTracker
from src.pipeline_report_service import PipelineReportService
from src.pytest_output_parser import RunResult, TestResult
from src.report_builder import build_report_dicts
from src.report_formatters import (
    generate_html_report,
    generate_jira_report,
    generate_local_report,
    verification_line,
)
from src.report_utils import verification_line as report_utils_verification_line
from tests.test_usage_meter import _paid_license

_VERIFIED = {
    "test_name": "test_01_login",
    "status": "verified_by_element",
    "label": "verified by element",
    "checked": "'#login-button'",
    "page_url": "https://example.com/",
    "reason": "",
}
_UNVERIFIED = {
    "test_name": "test_02_cart",
    "status": "unverified",
    "label": "unverified",
    "checked": "",
    "page_url": "",
    "reason": "1 of 2 placeholders unresolved: 'order success message'",
}


def _write_verification_strength(package_dir: Path, verdicts: list[dict[str, Any]]) -> Path:
    path = package_dir / "verification_strength.json"
    path.write_text(json.dumps({"generated_at": "2026-01-01T00:00:00", "verdicts": verdicts}), encoding="utf-8")
    return path


def _write_sidecar(package_dir: Path, test_name: str, verification: dict[str, Any]) -> Path:
    evidence_dir = package_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "test": {
            "name": test_name,
            "condition_ref": "TC-001",
            "story_ref": "S01",
            "status": "passed",
            "duration_s": 1.0,
            "verification": verification,
        },
        "page": {"url": "https://example.com/"},
        "run_history": {"total_runs": 1, "passed_runs": 1, "failed_runs": 0},
        "steps": [],
    }
    path = evidence_dir / f"{test_name}.evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. The runtime evidence sidecar
# ---------------------------------------------------------------------------


class TestSidecar:
    def test_tracker_stamps_the_verdict_under_test_verification(self, tmp_path: Path) -> None:
        _write_verification_strength(tmp_path, [_VERIFIED, _UNVERIFIED])
        tracker = EvidenceTracker(MagicMock(), "test_01_login", "TC-001", "S01", test_package_dir=tmp_path)

        written = Path(tracker.write("passed"))
        payload = json.loads(written.read_text(encoding="utf-8"))

        assert payload["test"]["verification"]["status"] == "verified_by_element"
        assert payload["test"]["verification"]["label"] == "verified by element"
        assert payload["test"]["verification"]["checked"] == "'#login-button'"

    def test_unverified_verdict_keeps_its_reason_in_the_sidecar(self, tmp_path: Path) -> None:
        _write_verification_strength(tmp_path, [_VERIFIED, _UNVERIFIED])
        tracker = EvidenceTracker(MagicMock(), "test_02_cart", test_package_dir=tmp_path)

        payload = json.loads(Path(tracker.write("skipped")).read_text(encoding="utf-8"))

        verification = payload["test"]["verification"]
        assert verification["status"] == "unverified"
        assert verification["reason"]

    def test_parameterized_test_name_matches_its_base_verdict(self, tmp_path: Path) -> None:
        """pytest reports ``test_01_login[chromium]``; the pipeline key has no
        suffix."""
        _write_verification_strength(tmp_path, [_VERIFIED])
        tracker = EvidenceTracker(MagicMock(), "test_01_login[chromium]", test_package_dir=tmp_path)

        payload = json.loads(Path(tracker.write("passed")).read_text(encoding="utf-8"))

        assert payload["test"]["verification"]["status"] == "verified_by_element"

    def test_package_without_verification_file_stays_empty(self, tmp_path: Path) -> None:
        """An older package must not crash and must not invent a verdict."""
        tracker = EvidenceTracker(MagicMock(), "test_01_login", test_package_dir=tmp_path)

        payload = json.loads(Path(tracker.write("passed")).read_text(encoding="utf-8"))

        assert payload["test"]["verification"] == {}


class TestVerificationLoader:
    def test_loads_and_keys_by_test_name(self, tmp_path: Path) -> None:
        _write_verification_strength(tmp_path, [_VERIFIED, _UNVERIFIED])
        loaded = load_verification_strength(tmp_path)
        assert set(loaded) == {"test_01_login", "test_02_cart"}
        assert loaded["test_01_login"]["label"] == "verified by element"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_verification_strength(tmp_path) == {}

    def test_malformed_file_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "verification_strength.json").write_text("{not json", encoding="utf-8")
        assert load_verification_strength(tmp_path) == {}

    def test_match_handles_parameter_suffixes(self) -> None:
        verdicts = {"test_01_login": _VERIFIED}
        assert match_verification_to_test(verdicts, "test_01_login[chromium]") is not None
        assert match_verification_to_test(verdicts, "test_99_missing") is None

    def test_get_verification_defaults_to_empty(self) -> None:
        assert get_verification({"test": {}}) == {}
        assert get_verification({"test": {"verification": _VERIFIED}}) == _VERIFIED


# ---------------------------------------------------------------------------
# 2a. Report rows carry the verdict (report_builder / report_utils)
# ---------------------------------------------------------------------------


def _coverage() -> dict[str, Any]:
    return {
        "requirements": [
            RequirementCoverage(
                id="TC-001",
                description="Login works",
                status="covered",
                linked_tests=["test_01_login"],
            )
        ]
    }


def _run_result() -> RunResult:
    return RunResult(
        results=[
            TestResult(
                name="test_01_login",
                status="passed",
                duration=1.2,
                error_message="",
                file_path="generated_tests/test_demo.py",
            )
        ],
        total=1,
        passed=1,
        failed=0,
        duration=1.2,
    )


class TestReportRows:
    def test_build_report_dicts_carries_the_verdict(self, tmp_path: Path) -> None:
        _write_sidecar(tmp_path, "test_01_login", _VERIFIED)

        rows = build_report_dicts(_coverage(), _run_result(), package_dir=str(tmp_path))

        assert rows[0]["verification"]["status"] == "verified_by_element"
        assert rows[0]["verification"]["checked"] == "'#login-button'"

    def test_row_without_evidence_has_no_verdict(self, tmp_path: Path) -> None:
        rows = build_report_dicts(_coverage(), _run_result(), package_dir=str(tmp_path))
        assert rows[0]["verification"] == {}


# ---------------------------------------------------------------------------
# 2b. The report formatters render the verdict
# ---------------------------------------------------------------------------


def _row(verification: dict[str, Any]) -> dict[str, Any]:
    return {
        "test_name": "Login works",
        "status": "passed",
        "duration": 1.2,
        "screenshots": [],
        "error_message": "",
        "verification": verification,
    }


class TestFormatters:
    def test_verification_line_for_both_states(self) -> None:
        assert verification_line(_row(_VERIFIED)) == "verified by element ('#login-button')"
        assert (
            verification_line(_row(_UNVERIFIED))
            == "unverified - 1 of 2 placeholders unresolved: 'order success message'"
        )
        assert verification_line(_row({})) == ""

    def test_report_utils_exposes_the_helper(self) -> None:
        assert report_utils_verification_line(_row(_VERIFIED)) == "verified by element ('#login-button')"

    def test_local_report_renders_element_and_reason(self) -> None:
        rendered = generate_local_report([_row(_VERIFIED), _row(_UNVERIFIED)])
        assert "**Verification:** verified by element ('#login-button')" in rendered
        assert "**Verification:** unverified - 1 of 2 placeholders unresolved" in rendered

    def test_jira_report_renders_element_and_reason(self) -> None:
        rendered = generate_jira_report([_row(_VERIFIED), _row(_UNVERIFIED)])
        assert "*Verification:* verified by element ('#login-button')" in rendered
        assert "*Verification:* unverified - 1 of 2 placeholders unresolved" in rendered

    def test_html_report_renders_and_escapes(self) -> None:
        unsafe = dict(_UNVERIFIED, reason="1 of 2 unresolved: <script>")
        rendered = generate_html_report([_row(unsafe)])
        assert "Verification:</span>" in rendered
        assert "unverified - 1 of 2 unresolved: &lt;script&gt;" in rendered
        assert "<script>" not in rendered

    def test_rows_without_verification_render_nothing(self) -> None:
        rendered = generate_local_report([_row({})])
        assert "Verification:" not in rendered


# ---------------------------------------------------------------------------
# 2c. The pipeline report bundle writes the local JSON surface
# ---------------------------------------------------------------------------


class TestPipelineReportService:
    def test_build_reports_writes_local_json_with_verdicts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Jira is the gated format; licence the deployment so all three human
        # surfaces are produced regardless of this machine's free-tier ledger.
        _paid_license(monkeypatch, tier="self-serve")
        _write_sidecar(tmp_path, "test_01_login", _VERIFIED)
        service = PipelineReportService()

        bundle = service.build_reports(
            criteria_text="1. login works",
            generated_code="def test_01_login(page):\n    pass",
            run_result=_run_result(),
            package_dir=str(tmp_path),
        )

        assert Path(bundle.local_json_path).exists()
        assert Path(bundle.local_json_path).name == "report_local.json"
        payload = json.loads(Path(bundle.local_json_path).read_text(encoding="utf-8"))
        assert payload["coverage"][0]["verification"]["status"] == "verified_by_element"
        # The three human surfaces carry the same verdict.
        assert "verified by element" in bundle.local_report
        assert "verified by element" in bundle.jira_report
        assert "verified by element" in bundle.html_report

    def test_build_reports_without_package_dir_has_no_json_path(self) -> None:
        bundle = PipelineReportService().build_reports(
            criteria_text="1. login works",
            generated_code="def test_01_login(page):\n    pass",
            run_result=_run_result(),
        )
        assert bundle.local_json_path == ""
        assert "verified by element" not in bundle.local_report
