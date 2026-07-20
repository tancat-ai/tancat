"""Tests for src/evidence_index.py.

Covers schema creation, build/refresh (full + incremental), search
(full-text + faceted filters), filter options, and edge cases.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.evidence_index import (
    EvidenceIndex,
)
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
    page_url: str = "https://automationexercise.com/products",
    steps: list[dict] | None = None,
    test_package_dir: str | None = None,
) -> Path:
    """Create a minimal evidence sidecar JSON file and return its path.

    When *test_package_dir* is given the sidecar is placed inside a
    ``<package>/evidence/`` tree below *evidence_dir*, otherwise
    directly inside *evidence_dir*.
    """
    if test_package_dir is not None:
        pkg = evidence_dir / test_package_dir / "evidence"
    else:
        pkg = evidence_dir
    pkg.mkdir(parents=True, exist_ok=True)

    if steps is None:
        steps = [
            {
                "step": 1,
                "type": "navigate",
                "label": f"Navigate to {page_url}",
                "value": page_url,
            },
            {
                "step": 2,
                "type": "assertion",
                "label": "product grid visible",
                "value": None,
            },
        ]

    sidecar = {
        "schema_version": "1.0",
        "test": {
            "name": test_name,
            "condition_ref": condition_ref,
            "story_ref": story_ref,
            "status": status,
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
def tmp_db(tmp_path: Path) -> Path:
    """Return a unique database path for each test."""
    return tmp_path / "test_evidence.sqlite"


@pytest.fixture()
def index(tmp_db: Path) -> EvidenceIndex:
    """Create an EvidenceIndex backed by a temp SQLite database."""
    db = SQLitePersistence(db_path=tmp_db)
    return EvidenceIndex(db=db)


@pytest.fixture()
def populated_index(index: EvidenceIndex, tmp_path: Path) -> EvidenceIndex:
    """An index populated with 3 sidecars across 2 test packages."""
    base = tmp_path / "generated_tests"
    base.mkdir()

    _make_sidecar(
        base,
        "test_login[chromium].evidence.json",
        test_name="test_login[chromium]",
        condition_ref="TC01.01",
        story_ref="S06",
        status="passed",
        page_url="https://automationexercise.com/login",
        test_package_dir="test_20260701_login",
    )

    _make_sidecar(
        base,
        "test_cart[chromium].evidence.json",
        test_name="test_cart[chromium]",
        condition_ref="TC01.05",
        story_ref="S06",
        status="failed",
        page_url="https://automationexercise.com/view_cart",
        steps=[
            {"step": 1, "type": "navigate", "label": "Navigate to cart"},
            {"step": 2, "type": "click", "label": "dress product"},
            {"step": 3, "type": "assertion", "label": "dress in cart"},
        ],
        test_package_dir="test_20260701_cart",
    )

    _make_sidecar(
        base,
        "test_search[chromium].evidence.json",
        test_name="test_search[chromium]",
        condition_ref="TC02.01",
        story_ref="S07",
        status="passed",
        page_url="https://saucedemo.com/inventory.html",
        test_package_dir="test_20260701_search",
    )

    index.build_or_refresh(base_dir=base)
    return index


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    def test_evidence_index_table_exists(self, index: EvidenceIndex) -> None:
        """Schema is created automatically on first use."""
        row = index._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_index'"
        ).fetchone()
        assert row is not None

    def test_indexes_created(self, index: EvidenceIndex) -> None:
        rows = index._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_evidence_%'"
        ).fetchall()
        names = {r[0] for r in rows}
        expected = {
            "idx_evidence_status",
            "idx_evidence_condition_ref",
            "idx_evidence_story_ref",
            "idx_evidence_page_url",
            "idx_evidence_test_name",
        }
        assert expected <= names


# ---------------------------------------------------------------------------
# Build / refresh
# ---------------------------------------------------------------------------


class TestBuildOrRefresh:
    def test_empty_directory_returns_zero(self, index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "empty"
        base.mkdir()
        count = index.build_or_refresh(base_dir=base)
        assert count == 0

    def test_indexes_sidecars(self, populated_index: EvidenceIndex) -> None:
        row = populated_index._conn.execute("SELECT COUNT(*) FROM evidence_index").fetchone()
        assert row[0] == 3

    def test_incremental_skips_unchanged_files(self, populated_index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        count = populated_index.build_or_refresh(base_dir=base)
        assert count == 0  # nothing changed

    def test_incremental_picks_up_new_file(self, populated_index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        _make_sidecar(
            base,
            "test_new[chromium].evidence.json",
            test_name="test_new[chromium]",
            test_package_dir="test_20260701_new",
        )
        count = populated_index.build_or_refresh(base_dir=base)
        assert count == 1

    def test_incremental_picks_up_modified_file(self, populated_index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        sidecar = base / "test_20260701_login" / "evidence" / "test_login[chromium].evidence.json"
        # Modify the file
        time.sleep(0.1)  # ensure mtime changes
        data = json.loads(sidecar.read_text())
        data["test"]["status"] = "failed"
        sidecar.write_text(json.dumps(data))
        count = populated_index.build_or_refresh(base_dir=base)
        assert count == 1
        # Verify status was updated
        row = populated_index._conn.execute(
            "SELECT status FROM evidence_index WHERE test_name = ?",
            ("test_login[chromium]",),
        ).fetchone()
        assert row["status"] == "failed"

    def test_force_rebuild_reindexes_all(self, populated_index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        count = populated_index.build_or_refresh(base_dir=base, force=True)
        assert count == 3  # re-indexed all 3

    def test_corrupt_json_skipped(self, index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        base.mkdir()
        bad = base / "corrupt.evidence.json"
        bad.write_text("not json", encoding="utf-8")
        count = index.build_or_refresh(base_dir=base)
        assert count == 0

    def test_returns_indexed_count(self, index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        base.mkdir()
        _make_sidecar(base, "a.evidence.json")
        _make_sidecar(base, "b.evidence.json")
        count = index.build_or_refresh(base_dir=base)
        assert count == 2


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearchFullText:
    def test_empty_query_returns_all(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search()
        assert len(results) == 3

    def test_search_by_test_name(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(query="login")
        assert len(results) == 1
        assert results[0].test_name == "test_login[chromium]"

    def test_search_by_step_label(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(query="dress")
        assert len(results) == 1
        assert results[0].matched_field == "step_labels"

    def test_search_by_url(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(query="saucedemo")
        assert len(results) == 1
        assert results[0].test_name == "test_search[chromium]"

    def test_search_by_condition_ref(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(query="TC02")
        assert len(results) == 1
        assert results[0].condition_ref == "TC02.01"

    def test_search_case_insensitive(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(query="LOGIN")
        assert len(results) == 1

    def test_search_no_match(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(query="nonexistent")
        assert len(results) == 0

    def test_matched_field_populated(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(query="login")
        assert results[0].matched_field


class TestSearchFilters:
    def test_filter_by_status_passed(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(status="passed")
        assert len(results) == 2
        assert all(r.status == "passed" for r in results)

    def test_filter_by_status_failed(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(status="failed")
        assert len(results) == 1
        assert results[0].status == "failed"

    def test_filter_by_domain(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(url_domain="automationexercise.com")
        assert len(results) == 2

    def test_filter_by_condition_prefix(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(condition_prefix="TC02")
        assert len(results) == 1
        assert results[0].condition_ref == "TC02.01"

    def test_filter_by_story_ref(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(story_ref="S07")
        assert len(results) == 1
        assert results[0].story_ref == "S07"

    def test_filter_by_step_type(self, populated_index: EvidenceIndex) -> None:
        # Only the cart test has a "click" step
        results = populated_index.search(step_type="click")
        assert len(results) == 1
        assert results[0].test_name == "test_cart[chromium]"


class TestSearchCombined:
    def test_query_and_status(self, populated_index: EvidenceIndex) -> None:
        # cart + failed
        results = populated_index.search(query="cart", status="failed")
        assert len(results) == 1
        assert results[0].test_name == "test_cart[chromium]"

    def test_query_and_domain(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(query="login", url_domain="automationexercise.com")
        assert len(results) == 1

    def test_all_filters_combined(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(
            query="dress",
            status="failed",
            url_domain="automationexercise.com",
        )
        assert len(results) == 1
        assert "cart" in results[0].test_name

    def test_no_results_with_contradictory_filters(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(status="passed", story_ref="S07", step_type="click")
        # S07 has TC02.01 which is passed but has navigate+assertion, not click
        assert len(results) == 0

    def test_limit(self, populated_index: EvidenceIndex) -> None:
        results = populated_index.search(limit=2)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Filter options
# ---------------------------------------------------------------------------


class TestFilterOptions:
    def test_statuses(self, populated_index: EvidenceIndex) -> None:
        opts = populated_index.get_filter_options()
        assert set(opts.statuses) == {"failed", "passed"}

    def test_domains(self, populated_index: EvidenceIndex) -> None:
        opts = populated_index.get_filter_options()
        assert "automationexercise.com" in opts.domains
        assert "saucedemo.com" in opts.domains

    def test_condition_prefixes(self, populated_index: EvidenceIndex) -> None:
        opts = populated_index.get_filter_options()
        assert set(opts.condition_prefixes) == {"TC01", "TC02"}

    def test_story_refs(self, populated_index: EvidenceIndex) -> None:
        opts = populated_index.get_filter_options()
        assert set(opts.story_refs) == {"S06", "S07"}

    def test_step_types(self, populated_index: EvidenceIndex) -> None:
        opts = populated_index.get_filter_options()
        assert "navigate" in opts.step_types
        assert "assertion" in opts.step_types
        assert "click" in opts.step_types

    def test_total_indexed(self, populated_index: EvidenceIndex) -> None:
        opts = populated_index.get_filter_options()
        assert opts.total_indexed == 3

    def test_last_refreshed(self, populated_index: EvidenceIndex) -> None:
        opts = populated_index.get_filter_options()
        assert opts.last_refreshed is not None


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    def test_resolves_sidecar_path(self, populated_index: EvidenceIndex) -> None:
        path = populated_index.get_test_package_path("test_20260701_login/evidence/test_login[chromium].evidence.json")
        assert path.name == "test_login[chromium].evidence.json"
        assert "generated_tests" in str(path) or "test_20260701_login" in str(path)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_nonexistent_base_dir(self, index: EvidenceIndex, tmp_path: Path) -> None:
        count = index.build_or_refresh(base_dir=tmp_path / "does_not_exist")
        assert count == 0

    def test_missing_steps_field(self, index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        base.mkdir()
        pkg = base / "test_pkg" / "evidence"
        pkg.mkdir(parents=True)
        sidecar = pkg / "minimal.evidence.json"
        sidecar.write_text(json.dumps({"test": {"name": "t", "status": "passed"}, "page": {"url": ""}}))
        count = index.build_or_refresh(base_dir=base)
        assert count == 1

    def test_unknown_status(self, index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        _make_sidecar(base, "unknown.evidence.json", status="skipped")
        index.build_or_refresh(base_dir=base)
        results = index.search()
        assert results[0].status == "skipped"

    def test_empty_condition_and_story(self, index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        _make_sidecar(base, "bare.evidence.json", condition_ref="", story_ref="")
        index.build_or_refresh(base_dir=base)
        results = index.search()
        assert results[0].condition_ref == ""
        assert results[0].story_ref == ""

    def test_search_after_refresh_picks_up_new(self, populated_index: EvidenceIndex, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        _make_sidecar(
            base,
            "test_after[chromium].evidence.json",
            test_name="test_after[chromium]",
            test_package_dir="test_late",
        )
        populated_index.build_or_refresh(base_dir=base)
        results = populated_index.search(query="after")
        assert len(results) == 1
