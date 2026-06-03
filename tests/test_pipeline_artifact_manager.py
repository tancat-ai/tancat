"""Tests for src.pipeline_artifact_manager — package metadata persistence."""

from __future__ import annotations

import json
from pathlib import Path

from src.pipeline_artifact_manager import (
    MANIFEST_FILENAME,
    PackageManifest,
    add_report_to_manifest,
    find_existing_packages,
    load_package_manifest,
    save_package_manifest,
    update_last_run_at,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_manifest(**overrides: object) -> PackageManifest:
    """Build a default PackageManifest with optional field overrides."""
    defaults: dict[str, object] = {
        "package_name": "test_20260602_login",
        "created_at": "2026-06-02T14:30:22+01:00",
        "source_story": "As a user, I want to login",
        "starting_url": "https://example.com/login",
        "additional_urls": ["https://example.com/dashboard"],
        "provider": "ollama",
        "model": "qwen3.5:35b",
        "generated_test_files": ["test_01_login.py"],
        "page_object_files": ["pages/po_login_page.py"],
        "scrape_manifest_path": "scrape_manifest.json",
        "reports": [],
        "evidence_paths": [],
        "run_results_count": 0,
        "last_run_at": "",
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return PackageManifest(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# PackageManifest dataclass tests
# ---------------------------------------------------------------------------


class TestPackageManifestDataclass:
    def test_to_dict_round_trip(self) -> None:
        m = _make_manifest()
        d = m.to_dict()
        assert d["package_name"] == "test_20260602_login"
        assert d["source_story"] == "As a user, I want to login"
        assert d["provider"] == "ollama"
        assert d["run_results_count"] == 0

    def test_from_dict(self) -> None:
        data = {
            "package_name": "test_20260601_checkout",
            "created_at": "2026-06-01T10:00:00+01:00",
            "source_story": "checkout story",
            "starting_url": "https://shop.com",
            "additional_urls": [],
            "provider": "lm-studio",
            "model": "qwen3.6-27b",
            "generated_test_files": ["test_01_checkout.py", "test_02_payment.py"],
            "page_object_files": [],
            "scrape_manifest_path": "",
            "reports": [{"format": "jira", "path": "reports/r.md", "generated_at": "2026-06-01T11:00:00"}],
            "evidence_paths": [],
            "run_results_count": 2,
            "last_run_at": "2026-06-01T12:00:00",
        }
        m = PackageManifest.from_dict(data)
        assert m.package_name == "test_20260601_checkout"
        assert m.provider == "lm-studio"
        assert len(m.generated_test_files) == 2
        assert m.run_results_count == 2
        assert len(m.reports) == 1

    def test_from_dict_defaults_for_missing_fields(self) -> None:
        data: dict[str, object] = {"package_name": "minimal"}
        m = PackageManifest.from_dict(data)
        assert m.package_name == "minimal"
        assert m.provider == ""
        assert m.generated_test_files == []
        assert m.reports == []


# ---------------------------------------------------------------------------
# save / load tests
# ---------------------------------------------------------------------------


class TestSaveAndLoadManifest:
    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        package_root = tmp_path / "test_pkg"
        package_root.mkdir()
        manifest = _make_manifest(package_name="test_pkg")

        save_package_manifest(package_root, manifest)

        loaded = load_package_manifest(package_root / MANIFEST_FILENAME)
        assert loaded.package_name == "test_pkg"
        assert loaded.source_story == manifest.source_story
        assert loaded.provider == "ollama"

    def test_save_includes_all_fields(self, tmp_path: Path) -> None:
        package_root = tmp_path / "test_pkg"
        package_root.mkdir()
        manifest = _make_manifest(
            package_name="test_pkg",
            additional_urls=["https://a.com", "https://b.com"],
            evidence_paths=["evidence/screenshot_01.png"],
        )
        save_package_manifest(package_root, manifest)

        raw = json.loads((package_root / MANIFEST_FILENAME).read_text())
        assert raw["additional_urls"] == ["https://a.com", "https://b.com"]
        assert raw["evidence_paths"] == ["evidence/screenshot_01.png"]

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "no_such" / MANIFEST_FILENAME
        try:
            load_package_manifest(path)
            raise AssertionError("Expected FileNotFoundError")
        except FileNotFoundError:
            pass  # expected

    def test_load_populates_package_name_from_parent(self, tmp_path: Path) -> None:
        """When package_name is empty in JSON, it should be filled from the parent dir."""
        package_root = tmp_path / "my_package"
        package_root.mkdir()
        # Write manifest with empty package_name
        (package_root / MANIFEST_FILENAME).write_text(
            json.dumps({"package_name": "", "created_at": "2026-01-01"}),
            encoding="utf-8",
        )
        loaded = load_package_manifest(package_root / MANIFEST_FILENAME)
        assert loaded.package_name == "my_package"


# ---------------------------------------------------------------------------
# find_existing_packages tests
# ---------------------------------------------------------------------------


class TestFindExistingPackages:
    def test_returns_empty_for_nonexistent_dir(self) -> None:
        assert find_existing_packages(Path("/nonexistent/path")) == []

    def test_finds_packages_with_manifest(self, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        base.mkdir()

        # Create two packages with manifests
        for name, created in [("pkg_b", "2026-06-02"), ("pkg_a", "2026-06-01")]:
            pkg_dir = base / name
            pkg_dir.mkdir()
            manifest = _make_manifest(package_name=name, created_at=created)
            save_package_manifest(pkg_dir, manifest)

        found = find_existing_packages(base)
        assert len(found) == 2
        # Should be sorted by created_at descending
        assert found[0].package_name == "pkg_b"
        assert found[1].package_name == "pkg_a"

    def test_discovers_legacy_packages_without_manifest(self, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        base.mkdir()

        # Legacy package: has test_*.py but no package_manifest.json
        pkg_dir = base / "legacy_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "test_01_something.py").write_text("import pytest", encoding="utf-8")

        found = find_existing_packages(base)
        assert len(found) == 1
        assert found[0].package_name == "legacy_pkg"
        assert found[0].source_story == "unknown"

    def test_skips_non_package_directories(self, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        base.mkdir()

        # A regular dir with no test files and no manifest
        (base / "random_dir").mkdir()
        (base / "random_dir" / "notes.txt").write_text("hello", encoding="utf-8")

        # An __pycache__ dir (should be skipped)
        (base / "__pycache__").mkdir()

        found = find_existing_packages(base)
        assert len(found) == 0

    def test_prefer_canonical_manifest_over_reconstruct(self, tmp_path: Path) -> None:
        base = tmp_path / "generated_tests"
        base.mkdir()

        pkg_dir = base / "mixed_pkg"
        pkg_dir.mkdir()
        # Has both a manifest AND test files
        manifest = _make_manifest(package_name="mixed_pkg", created_at="2026-06-01", source_story="my story")
        save_package_manifest(pkg_dir, manifest)
        (pkg_dir / "test_01.py").write_text("x=1", encoding="utf-8")

        found = find_existing_packages(base)
        assert len(found) == 1
        assert found[0].source_story == "my story"  # from canonical, not "unknown"


# ---------------------------------------------------------------------------
# reconstruct tests
# ---------------------------------------------------------------------------


class TestReconstructOldPackage:
    def test_reconstruct_from_package_root(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "old_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "test_01_login.py").write_text("def test(): pass", encoding="utf-8")
        (pkg_dir / "scrape_manifest.json").write_text("{}", encoding="utf-8")
        pages = pkg_dir / "pages"
        pages.mkdir()
        (pages / "po_login.py").write_text("class X: pass", encoding="utf-8")

        manifest = load_package_manifest(pkg_dir, reconstruct=True)
        assert manifest.package_name == "old_pkg"
        assert manifest.source_story == "unknown"
        assert "test_01_login.py" in manifest.generated_test_files
        assert any("po_login" in f for f in manifest.page_object_files)
        assert manifest.scrape_manifest_path == "scrape_manifest.json"

    def test_reconstruct_skips__init_files(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "old_pkg"
        pkg_dir.mkdir()
        pages = pkg_dir / "pages"
        pages.mkdir()
        (pages / "__init__.py").write_text("", encoding="utf-8")
        (pages / "po_home.py").write_text("class Home: pass", encoding="utf-8")

        manifest = load_package_manifest(pkg_dir, reconstruct=True)
        assert not any("__init__" in f for f in manifest.page_object_files)
        assert any("po_home" in f for f in manifest.page_object_files)


# ---------------------------------------------------------------------------
# load with reconstruct flag tests
# ---------------------------------------------------------------------------


class TestLoadReconstructFlag:
    def test_reconstruct_true_with_canonical_present(self, tmp_path: Path) -> None:
        """When reconstruct=True but canonical manifest exists, load it."""
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        manifest = _make_manifest(package_name="pkg", source_story="real story")
        save_package_manifest(pkg_dir, manifest)

        loaded = load_package_manifest(pkg_dir, reconstruct=True)
        assert loaded.source_story == "real story"

    def test_reconstruct_true_no_manifest(self, tmp_path: Path) -> None:
        """When reconstruct=True and no manifest, rebuild from disk."""
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "test_01.py").write_text("x=1", encoding="utf-8")

        loaded = load_package_manifest(pkg_dir, reconstruct=True)
        assert loaded.package_name == "pkg"
        assert loaded.source_story == "unknown"

    def test_reconstruct_false_no_manifest_raises(self, tmp_path: Path) -> None:
        """When reconstruct=False and no manifest file, raise."""
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "test_01.py").write_text("x=1", encoding="utf-8")

        try:
            load_package_manifest(pkg_dir / MANIFEST_FILENAME, reconstruct=False)
            raise AssertionError("Expected FileNotFoundError")
        except FileNotFoundError:
            pass  # expected


# ---------------------------------------------------------------------------
# Report / evidence helpers
# ---------------------------------------------------------------------------


class TestReportHelpers:
    def test_add_report_to_manifest(self) -> None:
        m = _make_manifest()
        assert len(m.reports) == 0

        add_report_to_manifest(m, "jira", "/path/to/report.md")
        assert len(m.reports) == 1
        assert m.reports[0]["format"] == "jira"
        assert m.reports[0]["path"] == "/path/to/report.md"
        assert "generated_at" in m.reports[0]

    def test_update_last_run_at_default(self) -> None:
        m = _make_manifest()
        assert m.last_run_at == ""
        assert m.run_results_count == 0

        update_last_run_at(m)
        assert m.last_run_at != ""
        assert m.run_results_count == 1

    def test_update_last_run_at_explicit(self) -> None:
        m = _make_manifest()
        update_last_run_at(m, timestamp="2026-06-02T15:00:00+00:00")
        assert m.last_run_at == "2026-06-02T15:00:00+00:00"
        assert m.run_results_count == 1


# ---------------------------------------------------------------------------
# Run results counting
# ---------------------------------------------------------------------------


class TestRunResultsCounting:
    def test_count_run_results_in_package(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "run_results_001.json").write_text("{}", encoding="utf-8")
        (pkg_dir / "run_results_002.json").write_text("{}", encoding="utf-8")

        manifest = load_package_manifest(pkg_dir, reconstruct=True)
        assert manifest.run_results_count == 2

    def test_count_run_results_in_evidence_subdir(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        ev_dir = pkg_dir / "evidence"
        ev_dir.mkdir()
        (ev_dir / "run_results_001.json").write_text("{}", encoding="utf-8")

        manifest = load_package_manifest(pkg_dir, reconstruct=True)
        assert manifest.run_results_count == 1
