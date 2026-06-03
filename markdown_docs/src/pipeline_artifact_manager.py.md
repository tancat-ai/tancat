# `src/pipeline_artifact_manager.py` — Package Artifact Manager

**Module:** Persist and load generated test package metadata  
**Created:** 2026-06-02  
**Status:** Stable  
**Feature:** AI-026 — Persist Generated Tests (Step 1)

---

## Overview

Provides package-level metadata persistence for generated test suites. Complements `run_result_persistence.py` (which handles pytest run outcomes) by managing the higher-level package context: user stories, LLM provider/model, report paths, and evidence locations.

Each generated package in `generated_tests/` receives a `package_manifest.json` file describing the suite. The module discovers existing packages, loads their manifests, and reconstructs minimal metadata for legacy packages that predate this feature.

No Streamlit imports — fully unit-testable in isolation. Shared between CLI and Streamlit UI.

---

## Dependencies

| Import | Source | Purpose |
|--------|--------|---------|
| `from __future__ import annotations` | stdlib | Postponed evaluation of annotations |
| `json` | stdlib | JSON serialization/deserialization |
| `dataclasses` | stdlib | `PackageManifest` dataclass |
| `datetime` | stdlib | Timestamp handling |
| `pathlib.Path` | stdlib | File system operations |
| `typing` | stdlib | Type hints (`List`, `Dict`, `Any`) |

---

## Data Structures

### `PackageManifest`

Core dataclass representing a single generated test package. Maps directly to `package_manifest.json` on disk.

| Field | Type | Description |
|-------|------|-------------|
| `package_name` | `str` | Package directory name (e.g., `test_20260602_143022_login_flow`) |
| `created_at` | `str` | ISO-8601 timestamp of pipeline run |
| `source_story` | `str` | Original user story text |
| `starting_url` | `str` | Entry URL for the journey |
| `additional_urls` | `list[str]` | Extra URLs scraped during pipeline |
| `provider` | `str` | LLM provider name (`ollama`, `lm-studio`, `openai`) |
| `model` | `str` | LLM model identifier |
| `generated_test_files` | `list[str]` | Test file paths in package |
| `page_object_files` | `list[str]` | Page Object file paths |
| `scrape_manifest_path` | `str` | Relative path to `scrape_manifest.json` |
| `reports` | `list[dict[str, str]]` | Report records: `{"format", "path", "generated_at"}` |
| `evidence_paths` | `list[str]` | Screenshot/evidence file paths |
| `run_results_count` | `int` | Number of `run_results_*.json` files |
| `last_run_at` | `str` | ISO-8601 timestamp of last pytest run |

**Methods:**
- `to_dict() -> dict[str, Any]` — Serialize to plain dict (uses `dataclasses.asdict`)
- `from_dict(data: dict[str, Any]) -> PackageManifest` — Class method; constructs from dict with defaults for missing fields

---

## Public API

### Core Persistence

| Function | Signature | Description |
|----------|-----------|-------------|
| `save_package_manifest` | `(package_root: Path, manifest: PackageManifest) -> None` | Write `package_manifest.json` to `package_root`. Creates parent directories if needed. |
| `load_package_manifest` | `(package_root: Path, reconstruct: bool = False) -> PackageManifest` | Load manifest from `package_root/package_manifest.json`. If `reconstruct=True` and file is missing, build minimal manifest from disk scan. |
| `find_existing_packages` | `(base_dir: Path) -> list[PackageManifest]` | Discover packages in `base_dir`. Prefers canonical manifests, falls back to reconstruction for legacy packages. Returns list sorted by `created_at` descending. |

### Report & Evidence Helpers

| Function | Signature | Description |
|----------|-----------|-------------|
| `add_report_to_manifest` | `(manifest: PackageManifest, report_format: str, report_path: str) -> None` | Append a report record to `manifest.reports` with current timestamp. |
| `update_last_run_at` | `(manifest: PackageManifest, timestamp: str \| None = None) -> None` | Update `last_run_at` and increment `run_results_count`. Uses current time if `timestamp` is `None`. |

---

## File Format

Each generated package stores metadata as:

```
generated_tests/<package_name>/
├── test_*.py
├── conftest.py
├── page_objects/
│   └── po_*.py
├── scrape_manifest.json         # existing — written by pipeline_writer.py
├── package_manifest.json        # THIS module — package metadata
├── run_results_*.json           # existing — written by run_result_persistence.py
└── evidence/
    └── screenshot_*.png
```

**`package_manifest.json` example:**

```json
{
  "package_name": "test_20260602_143022_login_flow",
  "created_at": "2026-06-02T14:30:22+01:00",
  "source_story": "As a user, I want to login to the app...",
  "starting_url": "https://example.com/login",
  "additional_urls": ["https://example.com/dashboard"],
  "provider": "ollama",
  "model": "qwen3.5:35b",
  "generated_test_files": ["test_01_login.py", "test_02_dashboard.py"],
  "page_object_files": ["page_objects/po_login_page.py"],
  "scrape_manifest_path": "scrape_manifest.json",
  "reports": [
    {
      "format": "jira",
      "path": "reports/report_jira.md",
      "generated_at": "2026-06-02T14:35:00+01:00"
    }
  ],
  "evidence_paths": ["evidence/screenshot_01.png"],
  "run_results_count": 3,
  "last_run_at": "2026-06-02T15:00:00+01:00"
}
```

---

## Package Discovery Logic

`find_existing_packages()` uses a two-phase discovery:

1. **Canonical scan** — Look for directories containing `package_manifest.json`. Load via `load_package_manifest()`.
2. **Legacy reconstruction** — For directories without a manifest but with `test_*.py` files, reconstruct a minimal manifest from disk.

**Excluded directories:** `__pycache__`, `.git`, and any directory without test files or a manifest.

**Sort order:** `created_at` descending (newest first).

---

## Legacy Package Reconstruction

When `reconstruct=True` and no `package_manifest.json` exists, the module scans the package directory:

| Reconstructed Field | Source |
|---------------------|--------|
| `package_name` | Parent directory name |
| `created_at` | Oldest file modification timestamp in package |
| `source_story` | `"unknown"` |
| `starting_url` | `"unknown"` |
| `provider` | `""` |
| `model` | `""` |
| `generated_test_files` | Glob `test_*.py` at package root |
| `page_object_files` | Scan `pages/`, `page_objects/` subdirectories for `*.py` (excluding `__init__.py`) |
| `scrape_manifest_path` | `"scrape_manifest.json"` if file exists, else `""` |
| `reports` | `[]` |
| `evidence_paths` | `[]` |
| `run_results_count` | Count of `run_results_*.json` files |
| `last_run_at` | `""` |

---

## Integration Points

| Consumer | Integration |
|----------|-------------|
| `src/pipeline_writer.py` (Step 3) | Will call `save_package_manifest()` after writing test files |
| `cli/main.py` (Step 4) | Will call `find_existing_packages()` for "Load Existing" menu |
| `streamlit_app.py` via `ui_renderers.py` (Step 5) | Will call `find_existing_packages()` for "Load Saved Package" sidebar |
| `src/run_result_persistence.py` | Complementary module — handles run outcomes; `update_last_run_at()` bridges the two |

---

## Relationship with `run_result_persistence.py`

| Module | Handles |
|--------|---------|
| `run_result_persistence.py` | Pytest run outcomes (pass/fail/skip per test, retry tracking, flakiness) |
| `pipeline_artifact_manager.py` | Package metadata (user story, provider/model, report paths, evidence paths) |

Both modules write to the same package directory but manage different concerns. `update_last_run_at()` in this module provides a bridge, updating manifest metadata when a new pytest run completes.

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| JSON over database | Consistent with `scrape_manifest.json` and `run_results_*.json` — no new dependencies |
| `reconstruct` flag on `load_package_manifest` | Keeps backward compatibility with legacy packages without requiring migration |
| Manifest lives in package root | Co-located with test files, scrape manifest, and run results — single source of truth per package |
| `find_existing_packages` returns manifests, not paths | Consumers get structured data immediately, not raw paths to parse |
| Discovery prefers canonical over reconstructed | Ensures accurate metadata when available, falls back gracefully |

---

## Test Coverage

22 unit tests in `tests/test_pipeline_artifact_manager.py` covering:
- PackageManifest to_dict/from_dict round-trip
- from_dict with missing fields (defaults)
- save and load round-trip
- All fields persisted in JSON
- FileNotFoundError for missing manifest
- Package name populated from parent directory
- find_existing_packages with canonical manifests
- Legacy package discovery (no manifest, test files only)
- Non-package directories skipped
- Canonical manifest preferred over reconstruction
- Reconstruct from package root
- __init__.py excluded from page_object_files
- reconstruct=True with canonical present
- reconstruct=True with no manifest
- reconstruct=False with no manifest raises
- add_report_to_manifest
- update_last_run_at with default and explicit timestamp
- run_results_count in package root
- run_results_count in evidence subdirectory

---

## Notes

- Module is fully synchronous — no async I/O
- Thread-safe for single-writer scenarios (typical for test pipeline)
- No file locking — not designed for concurrent writers
- `MANIFEST_FILENAME` constant (`"package_manifest.json"`) is exported for consumers