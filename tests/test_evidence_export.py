"""Tests for src/evidence_export.py.

Covers CSV, NDJSON, and JUnit XML exporters with filtering,
file output, and edge cases.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.evidence_export import (
    export_csv,
    export_junit_xml,
    export_ndjson,
)
from src.evidence_index import EvidenceIndex
from src.sqlite_persistence import SQLitePersistence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sidecar(
    evidence_dir: Path,
    filename: str,
    *,
    test_name: str = "test_example[chromium]",
    condition_ref: str = "TC01.01",
    story_ref: str = "S06",
    status: str = "passed",
    page_url: str = "https://automationexercise.com/view_cart",
    steps: list[dict] | None = None,
    duration_s: float = 0.0,
    test_package_dir: str | None = None,
) -> Path:
    """Create a minimal evidence sidecar JSON file and return its path."""
    if test_package_dir is not None:
        pkg = evidence_dir / test_package_dir / "evidence"
    else:
        pkg = evidence_dir
    pkg.mkdir(parents=True, exist_ok=True)

    if steps is None:
        steps = [
            {"step": 1, "type": "navigate", "label": "Navigate to site"},
            {"step": 2, "type": "assertion", "label": "product visible"},
        ]

    sidecar = {
        "schema_version": "1.0",
        "test": {
            "name": test_name,
            "condition_ref": condition_ref,
            "story_ref": story_ref,
            "status": status,
            "duration_s": duration_s,
        },
        "page": {"url": page_url},
        "steps": steps,
    }

    path = pkg / filename
    path.write_text(json.dumps(sidecar), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def index(tmp_path: Path) -> EvidenceIndex:
    """An EvidenceIndex populated with 4 sidecars of mixed status."""
    db = SQLitePersistence(db_path=tmp_path / "test.sqlite")
    idx = EvidenceIndex(db=db)
    base = tmp_path / "generated_tests"
    base.mkdir()

    _make_sidecar(
        base,
        "test_view_cart[chromium].evidence.json",
        test_name="test_view_cart[chromium]",
        condition_ref="TC01.05",
        status="passed",
        test_package_dir="test_pkg_1",
    )
    _make_sidecar(
        base,
        "test_cart[chromium].evidence.json",
        test_name="test_cart[chromium]",
        condition_ref="TC01.06",
        status="failed",
        page_url="https://automationexercise.com/view_cart",
        steps=[
            {"step": 1, "type": "navigate", "label": "Go to cart"},
            {"step": 2, "type": "click", "label": "checkout button"},
            {
                "step": 3,
                "type": "assertion",
                "label": "cart items visible",
                "result": {"error": "TimeoutError: element not found"},
            },
        ],
        duration_s=2.34,
        test_package_dir="test_pkg_1",
    )
    _make_sidecar(
        base,
        "test_login[chromium].evidence.json",
        test_name="test_login[chromium]",
        condition_ref="TC01.01",
        status="passed",
        page_url="https://saucedemo.com/inventory.html",
        test_package_dir="test_pkg_2",
    )
    _make_sidecar(
        base,
        "test_skipped[chromium].evidence.json",
        test_name="test_skipped[chromium]",
        condition_ref="TC01.99",
        status="skipped",
        steps=[],
        test_package_dir="test_pkg_2",
    )

    idx.build_or_refresh(base_dir=base)
    return idx


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


class TestExportCsv:
    def test_has_bom(self, index: EvidenceIndex) -> None:
        csv_text = export_csv(index)
        assert csv_text.startswith("\ufeff")

    def test_header_row(self, index: EvidenceIndex) -> None:
        csv_text = export_csv(index)
        lines = csv_text.splitlines()
        assert lines[0].startswith("\ufefftest_name")  # BOM + header
        assert "condition_ref" in lines[0]
        assert "story_ref" in lines[0]
        assert "status" in lines[0]
        assert "page_url" in lines[0]
        assert "step_count" in lines[0]
        assert "step_types" in lines[0]
        assert "step_labels" in lines[0]
        assert "duration_s" in lines[0]
        assert "test_package" in lines[0]
        assert "sidecar_path" in lines[0]

    def test_row_count_without_filters(self, index: EvidenceIndex) -> None:
        csv_text = export_csv(index)
        # Header + 4 data rows
        assert len(csv_text.splitlines()) == 5

    def test_filter_by_status(self, index: EvidenceIndex) -> None:
        csv_text = export_csv(index, status="failed")
        assert len(csv_text.splitlines()) == 2  # header + 1

    def test_filter_by_query(self, index: EvidenceIndex) -> None:
        csv_text = export_csv(index, query="login")
        assert len(csv_text.splitlines()) == 2  # header + 1

    def test_combined_filters(self, index: EvidenceIndex) -> None:
        csv_text = export_csv(index, status="passed", url_domain="automationexercise.com")
        lines = csv_text.splitlines()
        assert len(lines) == 2  # header + 1 (view_cart is passed)
        assert "test_view_cart" in lines[1]

    def test_writes_to_file(self, index: EvidenceIndex, tmp_path: Path) -> None:
        out = tmp_path / "export.csv"
        result = export_csv(index, output=out)
        assert str(out) == result
        assert out.exists()
        content = out.read_text(encoding="utf-8-sig")
        # CSV with BOM written as utf-8-sig — starts with header
        assert "test_name" in content.splitlines()[0]

    def test_empty_results_returns_header_only(self, index: EvidenceIndex) -> None:
        csv_text = export_csv(index, query="nonexistent")
        lines = csv_text.splitlines()
        assert len(lines) == 1  # header only
        assert "test_name" in lines[0]

    def test_step_count_correct(self, index: EvidenceIndex) -> None:
        # The cart test has 3 steps — find it by test name
        csv_text = export_csv(index, query="test_cart")
        line = csv_text.splitlines()[1]
        # step_count is column index 6 (0-based) — should be 3
        cols = line.split(",")
        assert cols[5] == "3"

    def test_duration_s_included(self, index: EvidenceIndex) -> None:
        # The cart test has duration_s=2.34 — find it by test name
        csv_text = export_csv(index, query="test_cart")
        line = csv_text.splitlines()[1]
        # duration_s is column index 9 (0-based)
        cols = line.split(",")
        assert cols[8] == "2.34"


# ---------------------------------------------------------------------------
# NDJSON
# ---------------------------------------------------------------------------


class TestExportNdjson:
    def test_valid_json_lines(self, index: EvidenceIndex) -> None:
        ndjson_text = export_ndjson(index)
        lines = ndjson_text.strip().split("\n")
        assert len(lines) == 4
        for line in lines:
            obj = json.loads(line)
            assert "test" in obj
            assert "page" in obj
            assert "steps" in obj

    def test_filtered_export(self, index: EvidenceIndex) -> None:
        ndjson_text = export_ndjson(index, status="passed")
        lines = ndjson_text.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert obj["test"]["status"] == "passed"

    def test_writes_to_file(self, index: EvidenceIndex, tmp_path: Path) -> None:
        out = tmp_path / "export.ndjson"
        result = export_ndjson(index, output=out)
        assert str(out) == result
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 4

    def test_pandas_compatible(self, index: EvidenceIndex) -> None:
        """NDJSON should parse with pd.read_json(lines=True)."""
        ndjson_text = export_ndjson(index)
        # Smoke test: each line is valid JSON
        for line in ndjson_text.strip().split("\n"):
            json.loads(line)

    def test_empty_results(self, index: EvidenceIndex) -> None:
        ndjson_text = export_ndjson(index, query="nonexistent")
        assert ndjson_text == ""


# ---------------------------------------------------------------------------
# JUnit XML
# ---------------------------------------------------------------------------


class TestExportJunitXml:
    def test_valid_xml(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        assert root.tag == "testsuites"

    def test_suite_attributes(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("tests") == "4"
        assert suite.get("failures") == "1"
        assert suite.get("errors") == "0"
        assert suite.get("skipped") == "1"

    def test_testcase_elements(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        cases = suite.findall("testcase")
        assert len(cases) == 4

    def test_classname_derived_from_url(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        classnames = {tc.get("classname") for tc in suite.findall("testcase")}
        assert "automationexercise.view_cart" in classnames
        assert "saucedemo.inventory" in classnames

    def test_name_includes_condition_ref(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        names = {tc.get("name") or "" for tc in suite.findall("testcase")}
        assert any(n.startswith("TC01.05") for n in names)
        assert any(n.startswith("TC01.06") for n in names)

    def test_failure_element_for_failed(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        for tc in suite.findall("testcase"):
            name = tc.get("name") or ""
            if name.startswith("TC01.06"):
                failure = tc.find("failure")
                assert failure is not None
                assert "TimeoutError" in (failure.get("message", "") or "")

    def test_skipped_element(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        for tc in suite.findall("testcase"):
            name = tc.get("name") or ""
            if name.startswith("TC01.99"):
                assert tc.find("skipped") is not None

    def test_time_attribute(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        assert float(suite.get("time", "0")) == pytest.approx(2.34, abs=0.01)

    def test_custom_suite_name(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index, suite_name="my_suite")
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("name") == "my_suite"

    def test_writes_to_file(self, index: EvidenceIndex, tmp_path: Path) -> None:
        out = tmp_path / "junit.xml"
        result = export_junit_xml(index, output=out)
        assert str(out) == result
        root = ET.fromstring(out.read_text())
        assert root.tag == "testsuites"

    def test_filtered_export(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index, status="failed")
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("tests") == "1"
        assert suite.get("failures") == "1"

    def test_empty_results(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index, query="nonexistent")
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("tests") == "0"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestExportEdgeCases:
    def test_csv_empty_index(self, index: EvidenceIndex) -> None:
        csv_text = export_csv(index, query="nonexistent")
        lines = csv_text.strip().split("\n")
        assert len(lines) == 1  # header only
        assert "test_name" in lines[0]

    def test_ndjson_empty_index(self, index: EvidenceIndex) -> None:
        ndjson_text = export_ndjson(index, query="nonexistent")
        assert ndjson_text == ""

    def test_junit_empty_index(self, index: EvidenceIndex) -> None:
        xml_text = export_junit_xml(index, query="nonexistent")
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("tests") == "0"
        assert suite.get("failures") == "0"

    def test_error_status(self, index: EvidenceIndex, tmp_path: Path) -> None:
        """Sidecars with 'error' status get counted as errors in JUnit."""
        base = tmp_path / "generated_tests"
        _make_sidecar(
            base,
            "test_error[chromium].evidence.json",
            test_name="test_error[chromium]",
            status="error",
            test_package_dir="test_pkg_3",
        )
        index.build_or_refresh(base_dir=base)

        xml_text = export_junit_xml(index)
        root = ET.fromstring(xml_text)
        suite = root.find("testsuite")
        assert suite is not None
        assert suite.get("errors") == "1"
