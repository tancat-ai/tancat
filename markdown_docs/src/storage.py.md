# `src/storage.py`

## High-Level Purpose

Workspace-isolated storage abstraction. Centralises all path construction so no module in the project constructs `Path("generated_tests")` or `Path("evidence")` directly. The default workspace (`"default"`) mirrors the current repo-root layout for backwards compatibility; named workspaces isolate data under a subdirectory.

Enables future cloud storage backends (S3, GCS, Azure Blob) without changing consumer code — they just need to satisfy the `StorageBackend` Protocol.

## Module Metadata

- **Lines:** ~145
- **Imports:** `pathlib.Path`, `typing.Protocol`
- **Spec:** `docs/specs/FEATURE_SPEC_AI029_workspace_storage.md`
- **Shipped:** 2026-07-19

## Protocol: `StorageBackend`

```python
class StorageBackend(Protocol):
    @property
    def workspace(self) -> str: ...
    @property
    def root(self) -> Path: ...
    def generated_tests_dir(self) -> Path: ...
    def evidence_dir(self) -> Path: ...
    def db_path(self) -> Path: ...
    def rag_path(self) -> Path: ...
    def ensure_dirs(self) -> None: ...
```

All path methods return `Path` objects — no string construction in consumers.

### Path methods

| Method | Returns |
|--------|---------|
| `generated_tests_dir()` | `<root>/<workspace>/generated_tests/` |
| `evidence_dir()` | `<root>/<workspace>/evidence/` |
| `db_path()` | `<root>/<workspace>/evidence/run_results.sqlite` |
| `rag_path()` | `<root>/<workspace>/evidence/rag_store.db` |

## Class: `LocalStorageBackend`

Local filesystem storage with workspace isolation. The only implementation shipped today.

```python
def __init__(self, root: Path | None = None, workspace: str = "default") -> None: ...
```

**Directory layout:**

```
<root>/                       # workspace == "default"
  generated_tests/
  evidence/
    run_results.sqlite
    rag_store.db

<root>/<workspace>/           # workspace != "default"
  generated_tests/
  evidence/
    run_results.sqlite
    rag_store.db
```

`ensure_dirs()` creates the workspace directory structure if it doesn't exist — called automatically during `__init__`.

## Singleton Management

### `get_storage() -> StorageBackend`
Return the global storage singleton. Lazily creates a `LocalStorageBackend` with `workspace="default"` on first call — safe to call from any module without worrying about startup ordering.

### `init_storage(root=None, workspace="default") -> StorageBackend`
Initialise (or re-initialise) the storage singleton. Call once at application startup:
- **Streamlit:** `init_storage(workspace=os.environ.get("WORKSPACE", "default"))`
- **CLI:** `init_storage(workspace=args.workspace)`

### `reset_storage() -> None`
Reset the singleton — used in test teardown for isolation.

## Key Design Decisions

- **Protocol-first:** `StorageBackend` is a `Protocol`, not an ABC — structural subtyping means backends don't need to inherit, only satisfy the interface.
- **Default workspace = repo root:** Backwards compatibility — all existing code that used `Path("generated_tests")` maps seamlessly.
- **Lazy singleton:** No explicit initialisation required — consumers call `get_storage()` and get a functional backend immediately.
- **`rag_path()` added 2026-07-21:** Returns path for the RAG vector store DB (`rag_store.db`), part of Phase 3 RAG integration.

## Dependencies

- `pathlib.Path` — stdlib only
- `pyproject.toml` — used to auto-detect repo root

## Depended On By

- **~15 consumer files** migrated from hardcoded `Path("generated_tests")` / `Path("evidence")`
- `src/rag_store.py` — uses `rag_path()` for vector store location
- `src/orchestrator.py` — uses `rag_path()` when building RAG retriever
- CI gate: `rg 'Path\("generated_tests"\)' -- '*.py'` must return zero results

## Notes

- CI gate enforces: zero hardcoded path hits in any `*.py` file under `src/`
- Future: S3/GCS/Azure Blob backends implement `StorageBackend` protocol
- `_find_repo_root()` walks upward from the module file looking for `pyproject.toml`
