"""Workspace-isolated storage abstraction.

Centralises all path construction so no module in the project constructs
``Path("generated_tests")`` or ``Path("evidence")`` directly.  The default
workspace (``"default"``) mirrors the current repo-root layout for
backwards compatibility; named workspaces isolate data under a subdirectory.

Usage::

    from src.storage import get_storage, init_storage

    # At app startup (Streamlit / CLI):
    init_storage(workspace="my-project")

    # Anywhere that needs a path:
    storage = get_storage()
    tests_dir = storage.generated_tests_dir()
    db_path = storage.db_path()
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class StorageBackend(Protocol):
    """Interface for storage backends.

    ``LocalStorageBackend`` is the only implementation shipped today.
    S3 / GCS / Azure Blob backends can be added later without changing
    consumer code — they just need to satisfy this protocol.
    """

    @property
    def workspace(self) -> str: ...

    @property
    def root(self) -> Path: ...

    def generated_tests_dir(self) -> Path: ...
    def evidence_dir(self) -> Path: ...
    def db_path(self) -> Path: ...
    def rag_path(self) -> Path: ...
    def ensure_dirs(self) -> None: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    """Walk upward from *this module* until we find ``pyproject.toml``.

    Falls back to :func:`Path.cwd` when no repository root is detected
    (e.g. the module was copied outside a checkout).
    """
    current = Path(__file__).resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------


class LocalStorageBackend:
    """Local filesystem storage with workspace isolation.

    Directory layout::

        <root>/                       # when workspace == "default"
          generated_tests/
          evidence/
            run_results.sqlite

        <root>/<workspace>/           # when workspace != "default"
          generated_tests/
          evidence/
            run_results.sqlite
    """

    def __init__(
        self,
        root: Path | None = None,
        workspace: str = "default",
    ) -> None:
        self._root = root or _find_repo_root()
        self._workspace = workspace
        self.ensure_dirs()

    # -- properties ----------------------------------------------------------

    @property
    def workspace(self) -> str:
        return self._workspace

    @property
    def root(self) -> Path:
        return self._root

    # -- path builders -------------------------------------------------------

    def workspace_dir(self) -> Path:
        """``<root>/<workspace>/`` (or ``<root>/`` for default)."""
        if self._workspace == "default":
            return self._root
        return self._root / self._workspace

    def generated_tests_dir(self) -> Path:
        """``<root>/<workspace>/generated_tests/``."""
        return self.workspace_dir() / "generated_tests"

    def evidence_dir(self) -> Path:
        """``<root>/<workspace>/evidence/``."""
        return self.workspace_dir() / "evidence"

    def db_path(self) -> Path:
        """``<root>/<workspace>/evidence/run_results.sqlite``."""
        return self.evidence_dir() / "run_results.sqlite"

    def rag_path(self) -> Path:
        """``<root>/<workspace>/evidence/rag_store.db``."""
        return self.evidence_dir() / "rag_store.db"

    # -- lifecycle -----------------------------------------------------------

    def ensure_dirs(self) -> None:
        """Create workspace directory structure if it does not exist."""
        self.generated_tests_dir().mkdir(parents=True, exist_ok=True)
        self.evidence_dir().mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Return the global storage singleton.

    If not yet initialised this lazily creates a ``LocalStorageBackend``
    with ``workspace="default"`` so that every module can safely call
    ``get_storage()`` without worrying about startup ordering.
    """
    global _storage
    if _storage is None:
        _storage = LocalStorageBackend()
    return _storage


def init_storage(
    root: Path | None = None,
    workspace: str = "default",
) -> StorageBackend:
    """Initialise (or re-initialise) the storage singleton.

    Call once at application startup::

        # Streamlit
        init_storage(workspace=os.environ.get("WORKSPACE", "default"))

        # CLI
        init_storage(workspace=args.workspace)
    """
    global _storage
    _storage = LocalStorageBackend(root=root, workspace=workspace)
    return _storage


def reset_storage() -> None:
    """Reset the storage singleton (for test isolation)."""
    global _storage
    _storage = None
