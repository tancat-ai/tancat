# Feature Spec — Workspace Isolation & Storage Abstraction

**Feature ID:** AI-029
**Created:** 2026-07-19
**Status:** Draft
**Priority:** Medium (Tier 3 — Infrastructure)
**Depends on:** None (pure refactoring, no feature dependencies)

---

## 1. Problem Statement

The codebase uses hardcoded `Path("generated_tests")` and `Path("evidence")` in ~15 files. This creates two problems for commercialization:

1. **No multi-tenancy path** — all data lives in a single `generated_tests/` and `evidence/` directory. Adding workspace isolation later requires finding every hardcoded path and retrofitting a `{tenant_id}` prefix.

2. **No cloud storage path** — S3/GCS/Azure Blob can't be swapped in without rewriting every file that touches disk. The current code assumes a local POSIX filesystem everywhere.

Both problems are cheap to fix now (<2 hours of refactoring) and expensive to fix later (ETL customer data, mass find-and-replace, regression risk).

---

## 2. Goals

| Goal | Criteria |
|------|----------|
| **Centralized path construction** | All storage paths flow through a single `StorageBackend` class. No file in the project constructs `Path("generated_tests")` or `Path("evidence")` directly. |
| **Workspace isolation** | Default workspace is `default`. User/CLI can set a workspace name. Storage paths become `<root>/<workspace>/generated_tests/` and `<root>/<workspace>/evidence/`. |
| **Interface for future backends** | `StorageBackend` is an ABC (or Protocol). `LocalStorageBackend` is the only implementation for now. `S3StorageBackend` can be added later without touching any consumer code. |
| **No behavior change** | Existing data stays in place. Default workspace mirrors current behavior — `generated_tests/` and `evidence/` at repo root. |
| **Per-workspace SQLite** | Each workspace gets its own `evidence/<workspace>/run_results.sqlite`. The AI-028 `evidence_index` table lives in the same DB. |

---

## 3. Non-Goals

- Multi-user auth (separate feature — this is about data isolation, not identity)
- S3/GCS implementation (just the interface for it)
- Workspace switching in Streamlit sidebar (can be a follow-up; CLI flag is enough for MVP)
- Database-per-tenant at the SQL level (row-level `tenant_id` columns — single DB, many tenants — is an anti-pattern we're explicitly avoiding by using file-per-tenant)

---

## 4. Architecture

### 4.1 Module: `src/storage.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StorageBackend(Protocol):
    """Protocol for storage backends. Local filesystem is the default;
    S3/GCS can be added later without changing consumer code."""

    @property
    def workspace(self) -> str: ...

    @property
    def root(self) -> Path: ...

    def generated_tests_dir(self) -> Path: ...
    def evidence_dir(self) -> Path: ...
    def db_path(self) -> Path: ...
    def ensure_dirs(self) -> None: ...


class LocalStorageBackend:
    """Local filesystem storage with workspace isolation.

    Directory layout:
        <root>/
          <workspace>/
            generated_tests/    # test packages + evidence sidecars
            evidence/           # run_results.sqlite + exports
    """

    def __init__(
        self,
        root: Path | None = None,
        workspace: str = "default",
    ) -> None:
        self._root = root or Path.cwd()
        self._workspace = workspace
        self.ensure_dirs()

    @property
    def workspace(self) -> str:
        return self._workspace

    @property
    def root(self) -> Path:
        return self._root

    def workspace_dir(self) -> Path:
        """Returns <root>/<workspace>/"""
        return self._root / self._workspace

    def generated_tests_dir(self) -> Path:
        """Returns <root>/<workspace>/generated_tests/"""
        return self.workspace_dir() / "generated_tests"

    def evidence_dir(self) -> Path:
        """Returns <root>/<workspace>/evidence/"""
        return self.workspace_dir() / "evidence"

    def db_path(self) -> Path:
        """Returns <root>/<workspace>/evidence/run_results.sqlite"""
        return self.evidence_dir() / "run_results.sqlite"

    def ensure_dirs(self) -> None:
        """Create workspace directory structure if it doesn't exist."""
        self.generated_tests_dir().mkdir(parents=True, exist_ok=True)
        self.evidence_dir().mkdir(parents=True, exist_ok=True)
```

### 4.2 Singleton Pattern

```python
# src/storage.py (continued)

_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Return the global storage singleton."""
    global _storage
    if _storage is None:
        _storage = LocalStorageBackend()
    return _storage


def init_storage(
    root: Path | None = None,
    workspace: str = "default",
) -> StorageBackend:
    """Initialize (or re-initialize) the storage singleton.

    Called at app startup (Streamlit) or CLI entry point.
    """
    global _storage
    _storage = LocalStorageBackend(root=root, workspace=workspace)
    return _storage


def reset_storage() -> None:
    """Reset the storage singleton. Used in tests for isolation."""
    global _storage
    _storage = None
```

### 4.3 Migration: What Changes Where

The principle: **replace `Path("generated_tests")` and `Path("evidence")` with `get_storage().generated_tests_dir()` and `get_storage().evidence_dir()`**. The `SQLitePersistence` module already takes a `db_path` parameter — just pass `get_storage().db_path()` instead.

| Current | Replacement |
|---------|------------|
| `Path("generated_tests")` | `get_storage().generated_tests_dir()` |
| `Path("evidence")` | `get_storage().evidence_dir()` |
| `Path("evidence/run_results.sqlite")` | `get_storage().db_path()` |
| `SQLitePersistence()` (default path) | `SQLitePersistence(db_path=get_storage().db_path())` |

### 4.4 Files to Update (~15 files)

**Streamlit UI:**
- `streamlit_app.py` — line 549: `base_dir = Path(__file__).resolve().parent / "generated_tests"` → `base_dir = get_storage().generated_tests_dir()`
- `src/ui/ui_evidence.py` — already accepts `base_dir: Path` in constructor (good — no change needed)
- `src/ui/ui_saved_packages.py` — `Path("generated_tests")` references
- `src/ui/ui_run_results.py` — ditto

**Pipeline core:**
- `src/ui_pipeline.py` — `find_evidence_sidecars(base_dir)`, `find_all_evidence_dirs(base_dir)`, `find_sidecar_for_test(base_dir, ...)` already accept `base_dir: Path` (good — no signature change, just the caller changes)
- `src/pipeline_writer.py` — hardcoded `Path("generated_tests")` for output paths
- `src/export_service.py` — hardcoded paths

**Persistence:**
- `src/run_result_persistence.py` — `_get_db()` currently creates `SQLitePersistence()` with default path. Change to `SQLitePersistence(db_path=get_storage().db_path())`. The `_reset_db()` used in tests just resets the singleton — isolation is handled by test-level `init_storage(root=tmp_path)`.

**CLI:**
- `cli/main.py` — `init_storage(workspace=args.workspace)` at startup
- `cli/pipeline_runner.py` — hardcoded paths
- `cli/session.py` — any path references

**Other:**
- `src/sqlite_persistence.py` — no change (already accepts `db_path` parameter)
- `src/run_history_chart.py` — no change (consumes `PersistedRunResult`, not paths)
- `scripts/verify_production.py` — hardcoded paths

### 4.5 Workspace in CLI

```bash
# Default workspace
python -m cli.main

# Named workspace
python -m cli.main --workspace project-alpha

# Results in: ./project-alpha/generated_tests/ and ./project-alpha/evidence/
```

### 4.6 Workspace in Streamlit

For MVP, workspace is an environment variable or a `--workspace` flag passed to `streamlit run`. A sidebar workspace switcher can be a follow-up.

```bash
WORKSPACE=project-alpha streamlit run streamlit_app.py
```

In `streamlit_app.py`, add early in `_init_session_state()`:

```python
workspace = os.environ.get("WORKSPACE", "default")
init_storage(workspace=workspace)
```

### 4.7 Backwards Compatibility

Existing data lives at the repo root (`generated_tests/` and `evidence/`). The default workspace `"default"` uses `root="."` (current working directory), so:

```
Before: ./generated_tests/  and  ./evidence/
After:  ./default/generated_tests/  and  ./default/evidence/
```

This is a **breaking layout change**. To avoid breaking existing workflows, the default `root` should be the **repo root** (not CWD), detected by looking for `pyproject.toml`:

```python
def _find_repo_root() -> Path:
    """Find the repository root (where pyproject.toml lives)."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()
```

But this still moves `generated_tests/` under `default/`. For a truly non-breaking change during development, use `root="."` and **skip** the workspace subdirectory when workspace is `"default"`:

```python
def workspace_dir(self) -> Path:
    if self._workspace == "default":
        return self._root  # backwards compat: no subdirectory
    return self._root / self._workspace
```

This way: `default` → `./generated_tests/` (unchanged), `project-alpha` → `./project-alpha/generated_tests/` (isolated).

---

## 5. Implementation Phases

### Phase 1: Storage Module (no consumer changes)
- [ ] `src/storage.py` — `StorageBackend` Protocol, `LocalStorageBackend`, `get_storage()`, `init_storage()`, `reset_storage()`
- [ ] `_find_repo_root()` for automatic repo-root detection
- [ ] `workspace="default"` backwards-compat: no subdirectory for default
- [ ] Unit tests: `tests/test_storage.py` — test path construction for default + named workspaces, test singleton lifecycle, test directory creation

### Phase 2: Migrate Consumers
- [ ] Update `streamlit_app.py` — call `init_storage()` at startup, use `get_storage()` for paths
- [ ] Update `src/ui_pipeline.py` — replace hardcoded `Path("generated_tests")` with storage calls
- [ ] Update `src/pipeline_writer.py`
- [ ] Update `src/export_service.py`
- [ ] Update `src/run_result_persistence.py` — pass `get_storage().db_path()` to `SQLitePersistence`
- [ ] Update `cli/main.py` — `init_storage(workspace=args.workspace)` + `--workspace` argument
- [ ] Update `cli/pipeline_runner.py`
- [ ] Update `scripts/verify_production.py`

### Phase 3: Verify
- [ ] `ruff check` clean
- [ ] `mypy` clean
- [ ] Full test suite passes (ensure all tests use `reset_storage()` and `init_storage(root=tmp_path)` in fixtures)
- [ ] `verify_production.py` generates tests, runs them, and evidence appears in correct workspace
- [ ] Manual test: `--workspace test-proj` creates isolated directory

---

## 6. Dependencies & Risks

| Dependency | Status |
|-----------|--------|
| None | Pure refactoring — no feature dependencies |

| Risk | Mitigation |
|------|-----------|
| Breaking existing paths during migration | Phase 2 is the riskiest step. Do it in one commit with full test suite verification. |
| Test isolation leaks between workspaces | `reset_storage()` in test fixtures. Each test that touches storage should call `init_storage(root=tmp_path)`. |
| Forgetting a hardcoded path | `rg 'Path\("generated_tests"\)'` and `rg 'Path\("evidence"\)'` after migration should return zero results. CI gate. |
| Streamlit `st.session_state` not workspace-aware | For MVP, workspace is set at startup and doesn't change. Per-session workspace switching is a follow-up. |

---

## 7. Success Criteria

- [ ] `rg 'Path\("generated_tests"\)' -- '*.py'` returns zero results (no hardcoded paths remain)
- [ ] `rg 'Path\("evidence"\)' -- '*.py'` returns zero results
- [ ] Default workspace (`default`) produces files at `./generated_tests/` and `./evidence/` (backwards compatible)
- [ ] Named workspace (`my-project`) produces files at `./my-project/generated_tests/` and `./my-project/evidence/`
- [ ] `SQLitePersistence(db_path=get_storage().db_path())` creates DB at correct workspace path
- [ ] Full test suite passes with zero regressions
- [ ] `verify_production.py` passes end-to-end
- [ ] 15+ unit tests for `src/storage.py`

---

## 8. Open Questions

1. **Should the Streamlit sidebar let users switch workspaces live?**  
   → Defer to follow-up. MVP uses env var or CLI flag. Live switching requires reloading all state, which is complex in Streamlit.

2. **Should `evidence/run_results.sqlite` stay per-workspace or move to a top-level DB with `workspace_id` column?**  
   → Per-workspace (file-per-tenant). Single-DB-with-row-level-isolation is what we're explicitly avoiding (see §3).

3. **What about the eval harness (`scripts/eval/`) — does it need workspace awareness?**  
   → Not for MVP. Eval is a development tool, not a customer-facing feature.

---

*Created: 2026-07-19*
