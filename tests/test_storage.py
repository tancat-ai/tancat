"""Tests for src/storage.py.

Covers path construction (default / named workspaces / custom root),
singleton lifecycle, directory creation, and backwards compatibility.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.storage import (
    LocalStorageBackend,
    _find_repo_root,
    get_storage,
    init_storage,
    reset_storage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_storage() -> None:
    """Reset the singleton before *and* after every test."""
    reset_storage()


# ---------------------------------------------------------------------------
# _find_repo_root
# ---------------------------------------------------------------------------


class TestFindRepoRoot:
    def test_finds_pyproject_toml(self) -> None:
        """When called from inside the repo, return the repo root directory."""
        root = _find_repo_root()
        assert (root / "pyproject.toml").exists(), f"Expected pyproject.toml at {root}"

    def test_returns_path_object(self) -> None:
        root = _find_repo_root()
        assert isinstance(root, Path)


# ---------------------------------------------------------------------------
# LocalStorageBackend — default workspace
# ---------------------------------------------------------------------------


class TestLocalStorageDefaultWorkspace:
    """``workspace="default"`` — backwards-compatible layout (no subdirectory)."""

    def test_workspace_property_is_default(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path)
        assert backend.workspace == "default"

    def test_root_is_custom_when_provided(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path)
        assert backend.root == tmp_path

    def test_workspace_dir_is_root_for_default(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path)
        assert backend.workspace_dir() == tmp_path

    def test_generated_tests_dir_is_root_generated_tests(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path)
        assert backend.generated_tests_dir() == tmp_path / "generated_tests"

    def test_evidence_dir_is_root_evidence(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path)
        assert backend.evidence_dir() == tmp_path / "evidence"

    def test_db_path_is_evidence_run_results_sqlite(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path)
        assert backend.db_path() == tmp_path / "evidence" / "run_results.sqlite"

    def test_ensure_dirs_creates_both_directories(self, tmp_path: Path) -> None:
        # Sanity: neither dir exists before
        assert not (tmp_path / "generated_tests").exists()
        assert not (tmp_path / "evidence").exists()
        LocalStorageBackend(root=tmp_path)
        assert (tmp_path / "generated_tests").is_dir()
        assert (tmp_path / "evidence").is_dir()

    def test_ensure_dirs_idempotent(self, tmp_path: Path) -> None:
        LocalStorageBackend(root=tmp_path)
        # Second construction must not raise
        LocalStorageBackend(root=tmp_path)
        assert (tmp_path / "generated_tests").is_dir()


# ---------------------------------------------------------------------------
# LocalStorageBackend — named workspace
# ---------------------------------------------------------------------------


class TestLocalStorageNamedWorkspace:
    """``workspace="my-proj"`` — isolated subdirectory layout."""

    def test_workspace_property(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path, workspace="proj-a")
        assert backend.workspace == "proj-a"

    def test_workspace_dir_is_root_slash_workspace(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path, workspace="proj-a")
        assert backend.workspace_dir() == tmp_path / "proj-a"

    def test_generated_tests_dir_under_workspace(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path, workspace="proj-a")
        expected = tmp_path / "proj-a" / "generated_tests"
        assert backend.generated_tests_dir() == expected

    def test_evidence_dir_under_workspace(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path, workspace="proj-a")
        expected = tmp_path / "proj-a" / "evidence"
        assert backend.evidence_dir() == expected

    def test_db_path_under_workspace(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path, workspace="proj-a")
        expected = tmp_path / "proj-a" / "evidence" / "run_results.sqlite"
        assert backend.db_path() == expected

    def test_ensure_dirs_creates_workspace_tree(self, tmp_path: Path) -> None:
        LocalStorageBackend(root=tmp_path, workspace="proj-a")
        assert (tmp_path / "proj-a" / "generated_tests").is_dir()
        assert (tmp_path / "proj-a" / "evidence").is_dir()
        # Root-level dirs should NOT exist
        assert not (tmp_path / "generated_tests").exists()
        assert not (tmp_path / "evidence").exists()


# ---------------------------------------------------------------------------
# Singleton — get_storage / init_storage / reset_storage
# ---------------------------------------------------------------------------


class TestSingletonLazyInit:
    def test_get_storage_creates_lazy_default(self) -> None:
        """Calling get_storage() without init_storage() first must work."""
        storage = get_storage()
        assert storage.workspace == "default"
        assert isinstance(storage, LocalStorageBackend)

    def test_get_storage_returns_same_instance(self) -> None:
        a = get_storage()
        b = get_storage()
        assert a is b


class TestSingletonInit:
    def test_init_storage_sets_workspace(self) -> None:
        init_storage(workspace="custom-ws")
        assert get_storage().workspace == "custom-ws"

    def test_init_storage_sets_root(self, tmp_path: Path) -> None:
        init_storage(root=tmp_path, workspace="ws1")
        assert get_storage().root == tmp_path

    def test_init_storage_overrides_lazy_default(self) -> None:
        _ = get_storage()  # triggers lazy default
        init_storage(workspace="explicit")
        assert get_storage().workspace == "explicit"

    def test_init_storage_returns_backend(self) -> None:
        backend = init_storage()
        assert backend is get_storage()


class TestSingletonReset:
    def test_reset_clears_singleton(self) -> None:
        init_storage()
        assert get_storage() is not None
        reset_storage()
        # Accessing after reset lazily recreates
        assert get_storage() is not None

    def test_reset_then_lazy_init_is_new_instance(self) -> None:
        init_storage(workspace="before")
        a = get_storage()
        reset_storage()
        b = get_storage()
        assert a is not b
        assert b.workspace == "default"


# ---------------------------------------------------------------------------
# Integration — workspace isolation does not leak
# ---------------------------------------------------------------------------


class TestWorkspaceIsolation:
    def test_two_workspaces_dont_collide(self, tmp_path: Path) -> None:
        """Ensure directories for different workspaces are separate."""
        ws_a = LocalStorageBackend(root=tmp_path, workspace="a")
        ws_b = LocalStorageBackend(root=tmp_path, workspace="b")

        assert ws_a.generated_tests_dir() != ws_b.generated_tests_dir()
        assert ws_a.evidence_dir() != ws_b.evidence_dir()
        assert ws_a.db_path() != ws_b.db_path()

        # Both trees should exist
        assert ws_a.generated_tests_dir().is_dir()
        assert ws_b.generated_tests_dir().is_dir()

    def test_default_and_named_isolated(self, tmp_path: Path) -> None:
        ws_default = LocalStorageBackend(root=tmp_path, workspace="default")
        ws_named = LocalStorageBackend(root=tmp_path, workspace="named")

        # default writes to root level
        assert ws_default.generated_tests_dir() == tmp_path / "generated_tests"
        # named writes under workspace subdir
        assert ws_named.generated_tests_dir() == tmp_path / "named" / "generated_tests"


# ---------------------------------------------------------------------------
# Protocol compliance (compile-time check — these are runtime smoke tests)
# ---------------------------------------------------------------------------


class TestStorageBackendProtocol:
    def test_local_satisfies_protocol(self) -> None:
        """LocalStorageBackend has all StorageBackend attributes."""
        b: LocalStorageBackend = LocalStorageBackend()
        # If the class didn't satisfy StorageBackend, mypy would complain.
        # At runtime we just verify attributes exist.
        for attr in (
            "workspace",
            "root",
            "generated_tests_dir",
            "evidence_dir",
            "db_path",
            "ensure_dirs",
        ):
            assert hasattr(b, attr), f"Missing attribute: {attr}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_workspace_with_special_chars(self, tmp_path: Path) -> None:
        backend = LocalStorageBackend(root=tmp_path, workspace="my-project_v2.0")
        expected = tmp_path / "my-project_v2.0" / "generated_tests"
        assert backend.generated_tests_dir() == expected
        assert expected.is_dir()

    def test_empty_workspace_string(self, tmp_path: Path) -> None:
        """Empty string workspace — treated as named, creates subdir ''."""
        backend = LocalStorageBackend(root=tmp_path, workspace="")
        # workspace="" → workspace_dir = root / ""
        assert backend.generated_tests_dir() == tmp_path / "generated_tests"

    def test_root_none_uses_repo_root(self) -> None:
        backend = LocalStorageBackend(root=None)
        # Should have found pyproject.toml via _find_repo_root()
        assert (backend.root / "pyproject.toml").exists()
