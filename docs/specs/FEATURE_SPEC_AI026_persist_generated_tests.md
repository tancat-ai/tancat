# FEATURE SPEC — Persist Generated Tests
## AI-026

**Status:** Steps 1-6 COMPLETE — Step 7 (Backwards Compatibility) already complete
**Last updated:** 2026-06-03 (step 6 completed: Persist Diagnostic Data)
**Depends on:** `src/pipeline_writer.py`, `src/run_result_persistence.py`, `src/pipeline_run_service.py`, `src/pipeline_models.py`, `cli/main.py`
**Priority:** Medium — improves workflow and reuse without changing core generation logic

---

## Problem Statement

The tool currently generates tests and saves them to `generated_tests/`, but the CLI
and UI only retain those artifacts for the active runtime session. If the user exits
and returns later, there is no supported way to reload a previously generated suite,
inspect its metadata, rerun the same suite, or review the saved reports and failure
diagnostics without regenerating from scratch.

This limits the workflow for validation and debugging because generated artifacts
are effectively disposable unless the user manually keeps track of directories and
files.

---

## Current State (as of 2026-06-02)

The following capabilities already exist and reduce the scope of this feature:

### `src/run_result_persistence.py` (created 2026-06-02)

Provides run-result persistence (pytest outcomes):
- `persist_run_result()` — saves pass/fail/skip per test after pytest runs
- `load_run_result()` — loads a single run's results
- `list_run_results()` — discovers run JSON files by package name
- `load_all_run_results()` — loads history of all runs for a package
- `compute_run_history()` — aggregates counts across runs
- `get_flaky_tests()` — identifies tests that alternate pass/fail across runs
- `compare_runs()` — diff two runs for regressions/improvements

**Covers:** run outcomes, retry tracking, flakiness detection, run comparison.
**Does NOT cover:** user story text, provider/model info, report paths, evidence paths, scrape manifest metadata.

### `src/pipeline_writer.py`

Writes `scrape_manifest.json` per generated package after each pipeline run. The manifest contains scraped page metadata and pipeline artifacts, but **does not** contain: `source_story`, `provider`, `model`, `run_results_path`, or `evidence_paths`.

### `src/pipeline_run_service.py`

`run_saved_test()` already supports:
- Running tests from a saved package path (`pipeline_saved_path`)
- `rerun_failed_only` flag
- `previous_run` parameter for comparing with prior results

### `src/pipeline_models.py`

- `ManifestRecord` — single unresolved/info record (already has `to_dict()`)
- `PipelineArtifactSet` — full pipeline output package (already has `to_dict()`)

---

## Goals

1. Allow the CLI to load an existing generated test package from disk.
2. Preserve relevant metadata, evidence, and report links for previously generated suites.
3. Enable rerunning saved test suites without re-triggering the LLM pipeline.
4. Keep Streamlit and CLI aligned by sharing the same artifact persistence helpers.
5. Maintain the current output-only rule for generated tests: they are not part of `tests/`.
6. Surface run history and flakiness metrics when loading a saved package.

---

## Design Principles

- **Explicit persistence:** Saving and loading generated suites should be a deliberate
  user action, not an automatic background process.
- **Shared artifact model:** CLI and Streamlit should use the same package descriptor
  and helper functions so both UIs behave consistently.
- **Non-invasive generation path:** Existing generation logic remains unchanged; this
  feature adds a persistence layer around generated output.
- **Report continuity:** Loaded suites should retain links to their previously generated
  reports and failure diagnostics when available.
- **Complement existing modules:** `run_result_persistence.py` handles run outcomes;
  the new `pipeline_artifact_manager.py` handles package metadata. They work together.

---

## Feature Scope

### In scope

- Snapshot package metadata for each generated suite in a `package_manifest.json` file.
- CLI menu commands: `Load Existing Generated Tests`, `Show Saved Package Metadata`, `Re-run Saved Suite`.
- A reusable persistence helper in `src/pipeline_artifact_manager.py` that save and loads package descriptors.
- Preservation of generated file paths, evidence locations, report outputs, and any
  pipeline state needed to rerun or inspect the suite.
- Streamlit UI support for loading an existing saved package and displaying its
  associated reports/diagnostics.
- Display run history and flakiness metrics (from `run_result_persistence.py`) when loading a package.

### Out of scope

- Regenerating tests from an old suite automatically.
- Editing saved generated tests in place via the persistence layer.
- Making generated tests discoverable by `pytest` automatically through `tests/`.
- Converting existing artifacts into a new package format unless the manifest is
  backward-compatible with current `generated_tests/` layout.

---

## Implementation Plan

### 1. `src/pipeline_artifact_manager.py` — ✅ COMPLETE (2026-06-02)

Implemented shared helper module responsible for loading and saving generated suite **metadata** (complementary to `run_result_persistence.py` which handles **run outcomes**).

**Responsibility split:**

| Module | Handles |
|--------|---------|
| `run_result_persistence.py` | Pytest run outcomes (pass/fail/skip per test, retry tracking, flakiness) |
| `pipeline_artifact_manager.py` | Package metadata (user story, provider/model, report paths, evidence paths) |

**Public API (implemented):**

```python
def save_package_manifest(package_root: Path, manifest: PackageManifest) -> None
def load_package_manifest(package_root: Path, reconstruct: bool = False) -> PackageManifest
def find_existing_packages(base_dir: Path) -> list[PackageManifest]
def add_report_to_manifest(manifest: PackageManifest, report_format: str, report_path: str) -> None
def update_last_run_at(manifest: PackageManifest, timestamp: str | None = None) -> None
def count_run_results_in_package(package_root: Path) -> int
```

**Implementation details:**
- `PackageManifest` dataclass with `to_dict()` / `from_dict()` serialization
- `find_existing_packages()` uses two-phase discovery: canonical manifests first, then legacy reconstruction
- Legacy packages (without `package_manifest.json`) are reconstructed from disk scan
- 22 unit tests in `tests/test_pipeline_artifact_manager.py`
- Module doc at `markdown_docs/src/pipeline_artifact_manager.py.md`

**`find_existing_packages()` discovery logic:**
- Scan `generated_tests/` for subdirectories containing `package_manifest.json`
- For older packages without `package_manifest.json` but with `scrape_manifest.json`,
  attempt to reconstruct a minimal manifest from available data
- Return manifests sorted by `created_at` descending

### 2. Package Manifest Schema — ✅ COMPLETE (2026-06-03)

Store the metadata as `package_manifest.json` inside each generated package directory:

```
generated_tests/<package_name>/
├── test_*.py                    # Generated test files
├── conftest.py                  # Shared fixtures
├── pages/                       # Generated page object modules (packages)
│   ├── __init__.py
│   └── po_*.py
├── scrape_manifest.json         # Scraped page data (existing — written by pipeline_writer.py)
├── package_manifest.json        # NEW — package metadata (this feature)
├── run_results_*.json           # Run outcomes (existing — written by run_result_persistence.py)
└── evidence/                    # Screenshot evidence, failure diagnostics
```

**`package_manifest.json` fields:**

```jsonc
{
  "package_name": "test_20260602_143022_login_flow",
  "created_at": "2026-06-02T14:30:22+01:00",
  "source_story": "As a user, I want to login to the app...",
  "starting_url": "https://example.com/login",
  "additional_urls": ["https://example.com/dashboard"],
  "provider": "ollama",
  "model": "qwen3.5:35b",
  "generated_test_files": ["test_01_login.py", "test_02_dashboard.py"],
  "page_object_files": ["pages/po_login_page.py"],
  "scrape_manifest_path": "scrape_manifest.json",
  "reports": [],
  "evidence_paths": [],
  "run_results_count": 3,
  "last_run_at": "2026-06-02T15:00:00+01:00"
}
```

**Field sourcing:**

| Field | Source | Status |
|-------|--------|--------|
| `package_name` | Package directory name | ✅ Persisted |
| `created_at` | Pipeline run timestamp | ✅ Persisted |
| `source_story` | `story_text` parameter to `write_run_artifacts()` | ✅ Persisted |
| `starting_url` | `base_url` parameter to `write_run_artifacts()` | ✅ Persisted |
| `additional_urls` | `additional_urls` parameter to `write_run_artifacts()` | ✅ Persisted |
| `provider` | `provider_name` parameter to `write_run_artifacts()` | ✅ Persisted |
| `model` | `model_name` parameter to `write_run_artifacts()` | ✅ Persisted |
| `generated_test_files` | Derivable from package directory scan | ✅ Persisted |
| `page_object_files` | Derivable from `pages/` directory scan | ✅ Persisted |
| `scrape_manifest_path` | Relative path to existing `scrape_manifest.json` | ✅ Persisted |
| `reports` | Updated after each report generation | ✅ Complete (step 6) |
| `evidence_paths` | Derived from screenshot evidence | ✅ Complete (step 6) |
| `run_results_count` | Dynamic — counted from `run_results_*.json` files | ✅ Persisted |
| `last_run_at` | Updated by `run_result_persistence.py` on each pytest run | ✅ Persisted |

**Implementation:**
- `PackageManifest` dataclass in `src/pipeline_artifact_manager.py`
- `save_package_manifest()` called from `pipeline_writer.write_run_artifacts()`
- `load_package_manifest()` loads from `package_manifest.json` with `reconstruct=True` fallback
- Module doc updated at `markdown_docs/src/pipeline_artifact_manager.py.md`
- Module doc updated at `markdown_docs/src/pipeline_writer.py.md`

**`pipeline_writer.py` changes (Step 2/3 integration):**
- Added `provider_name`, `model_name`, `additional_urls` parameters to `write_run_artifacts()`
- Calls `save_package_manifest()` after writing all artifact files
- Callers updated:
  - `src/ui_pipeline.py` passes `provider_name`, `model_name`, `additional_urls`
  - `cli/test_case_orchestrator.py` passes `provider_name`, `model_name`

### 3. `pipeline_writer.py` — ✅ COMPLETE (2026-06-03)

> **NOTE:** Step 3 is integrated into Step 2. The `write_run_artifacts()` method accepts `provider_name`, `model_name`, `additional_urls` parameters and calls `save_package_manifest()`.

### 4. CLI Menu Enhancements — ✅ COMPLETE (2026-06-03)

Update `cli/main.py` to add new top-level menu commands (before "Configure LLM" / "Enter User Story"):

| Command | Behavior | Implementation |
|---------|----------|----------------|
| **Load Existing Generated Tests** | Calls `find_existing_packages()` → renders a numbered list of packages sorted by date. User selects one → loads `package_manifest.json` + run history from `run_result_persistence.list_run_results()`. Populates session with loaded data. | `cli/main.py`: `_handle_load_existing_packages()`, `_handle_show_package_metadata()`, `_handle_rerun_saved_suite()`. Uses `cli/pipeline_runner.py`: `load_existing_packages()`, `run_saved_test_from_package()`. |
| **Show Saved Package Metadata** | Displays manifest fields in a structured table. Also shows run history summary (from `compute_run_history()`) and flakiness report (from `get_flaky_tests()`). | `render_saved_package_list()`, `render_package_metadata()`, `render_package_run_history()` in `cli/menu_renderer.py` |
| **Re-run Saved Suite** | Sets `session.pipeline_saved_path` to the loaded package's test files → calls `run_saved_test()` from `pipeline_run_service.py`. | `run_saved_test_from_package()` in `cli/pipeline_runner.py` → `run_saved_test()` in `src/pipeline_run_service.py` |

**Files modified:**
- `cli/main.py` — new menu options (4, 5, 6) + handler functions + loaded package state in menu
- `cli/session.py` — `loaded_package_manifest` and `loaded_package_run_results` attributes
- `cli/pipeline_runner.py` — `load_existing_packages()` and `run_saved_test_from_package()` functions
- `cli/menu_renderer.py` — `render_saved_package_list()`, `render_package_metadata()`, `render_package_run_history()` functions
- `tests/test_cli_pipeline_runner.py` — new tests for `load_existing_packages` and `run_saved_test_from_package`

**Discovery flow:**
```
Main menu → "Load Existing Generated Tests"
  → find_existing_packages("generated_tests/")
  → Render numbered list (package name, created_at, test count, run count)
  → User selects package index
  → load_package_manifest() + load_all_run_results()
  → Populate session state
  → Return to main menu (now showing loaded package context)
```

When a package is loaded, the main menu state summary shows:
```
  Loaded : test_20260602_143022_login_flow (3 tests, 5 runs)
  Story  : As a user, I want to login...
  URL    : https://example.com/login
```

### 5. Streamlit UI Support — ✅ COMPLETE (2026-06-03)

Implemented `SavedPackagePanel` class in `src/ui_renderers.py` that provides full Streamlit UI support for loading and managing saved packages.

**Implementation details:**
- `SavedPackagePanel` class in `src/ui_renderers.py` with sidebar and main panel rendering
- Sidebar: dropdown selector for packages, "Load Package" button, loaded package summary with run metrics
- Main panel: detailed metadata display, run history table, flaky test warnings, re-run controls
- Uses same `pipeline_artifact_manager.py` helpers (`find_existing_packages`) as CLI
- Uses `run_result_persistence.py` for run history (`load_all_run_results`, `compute_run_history`, `get_flaky_tests`)
- Session state keys: `loaded_package_manifest`, `loaded_package_root`, `loaded_package_runs`, `loaded_package_history`, `loaded_package_flaky`
- Integrated into `streamlit_app.py` sidebar via `SavedPackagePanel().render_sidebar()`
- Main panel rendered via `SavedPackagePanel().render_main_panel()` in main content area

**Files modified:**
- `src/ui_renderers.py` — new `SavedPackagePanel` class (~250 lines)
- `streamlit_app.py` — sidebar integration + main panel rendering

**Sidebar UI:**
```
Configuration
  [LLM Provider selector]

Saved Packages
  ─────────────
  [Package dropdown]
  [📂 Load Package]

  Loaded: test_20260602_143022_login_flow
  Created: 2026-06-02T14:30:22+01:00
  Story: As a user, I want to login...
  URL: https://example.com/login

  Total Runs: 5
  Total Passed: 12
  Total Failed: 3

  [▶️ Re-run Saved Suite]
```

**Main Panel UI:**
```
📦 Package: test_20260602_143022_login_flow
  Created: 2026-06-02T14:30:22+01:00    Provider: ollama
  Model: qwen3.5:35b                    URL: https://example.com/login
  Test files: 3                         Page objects: 2

  [User Story] [Test Files (3)] [Page Objects (2)]
  [Run History (5)] [⚠️ Flaky Tests (1)]
  [▶️ Run Saved Suite] [🔄 Re-run Failed Only]
```

### 6. Preserve Diagnostic Data — ✅ COMPLETE (2026-06-03)

When loading a saved package, include any available failure diagnostics and report
paths in the displayed metadata. This makes it possible to inspect prior results without
regenerating. The CLI's existing `view_failure_diagnostics()` function in `pipeline_runner.py`
was extended to work with loaded packages via `view_saved_package_diagnostics()`.

**Implementation details:**
- `view_saved_package_diagnostics()` in `cli/pipeline_runner.py` — loads and displays diagnostics for saved packages
- Loads `package_manifest.json` to retrieve `reports` and `evidence_paths` fields
- Scans `evidence/` subdirectory for `*.evidence.json` files matching test names
- Displays report locations, evidence file count, and per-test failure details
- For each failed step: shows locator, error message, and diagnosis data
- CLI menu option 11: "View Saved Package Diagnostics" accessible when a package is loaded
- `_handle_view_saved_diagnostics()` in `cli/main.py` wires menu to pipeline runner
- 6 unit tests in `tests/test_cli_saved_package_diagnostics.py`

**Files modified:**
- `cli/pipeline_runner.py` — new `view_saved_package_diagnostics()` function
- `cli/main.py` — new menu option + `_handle_view_saved_diagnostics()` handler
- `tests/test_cli_saved_package_diagnostics.py` — 6 tests covering evidence display

**Diagnostic output includes:**
- Report paths from manifest (local, Jira, HTML formats)
- Evidence paths from manifest
- Per-evidence file: test name, status, page URL
- Per failed step: step number, type, label, locator, error message
- Diagnosis data: suggested alternatives, available elements

### 7. Backwards Compatibility — ✅ COMPLETE (2026-06-02)

For older generated packages that predate this feature (have `scrape_manifest.json` but no `package_manifest.json`):

- `find_existing_packages()` still discovers them by scanning for `test_*.py` files
- A minimal manifest is reconstructed on-the-fly from available data:
  - `package_name` from directory name
  - `created_at` from oldest file timestamp
  - `generated_test_files` from directory scan
  - Other fields marked as `"unknown"`
- `load_package_manifest()` offers a `reconstruct=True` flag for this fallback

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Generation Pipeline (existing)                             │
│  pipeline_writer.py                                         │
│    → writes scrape_manifest.json                            │
│    → writes test files, page objects                        │
│    [NEW] → calls save_package_manifest()                    │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Package on disk                                            │
│  generated_tests/<package_name>/                            │
│    ├── test_*.py                                            │
│    ├── scrape_manifest.json         (existing)              │
│    ├── package_manifest.json        (NEW)                   │
│    └── run_results_*.json           (existing)              │
└──────────────────┬──────────────────────────────────────────┘
                   │
         ┌─────────┴──────────┐
         ▼                    ▼
┌──────────────────┐  ┌──────────────────┐
│ pipeline_        │  │ run_result_      │
│ artifact_        │  │ persistence.py   │
│ manager.py       │  │                  │
│ (metadata)       │  │ (run outcomes)   │
└──────────────────┘  └──────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│  CLI / Streamlit Load                                       │
│  1. find_existing_packages() → list packages                │
│  2. load_package_manifest() → metadata                      │
│  3. load_all_run_results() → run history                    │
│  4. Display + allow re-run                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Success Criteria

- [x] A saved generated test package can be loaded from disk in the CLI.
- [x] The CLI can rerun a loaded saved package without regenerating tests.
- [x] Loaded packages expose their previously generated report locations.
- [x] Loaded packages expose run history and flakiness metrics.
- [x] Streamlit can load the same package format and surface the same metadata.
- [x] Existing generation behavior continues to work for new packages.
- [x] Older packages (without `package_manifest.json`) are still discoverable.
- [x] `ruff`, `mypy`, and `pytest` pass after all changes.

---

## Testing Strategy

| Test | Type | Description | Status |
|------|------|-------------|--------|
| `test_save_and_load_manifest` | Unit | Save a manifest, load it, assert all fields match | ✅ In `test_pipeline_artifact_manager.py` |
| `test_find_existing_packages` | Unit | Create mock packages, verify discovery order and count | ✅ In `test_pipeline_artifact_manager.py` |
| `test_reconstruct_old_package` | Unit | Load a package without `package_manifest.json`, verify minimal manifest | ✅ In `test_pipeline_artifact_manager.py` |
| `test_load_existing_packages_no_packages_found` | Unit | `load_existing_packages()` handles empty generated_tests dir | ✅ Complete |
| `test_load_existing_packages_selects_package` | Unit | User selects valid index → manifest loaded | ✅ Complete |
| `test_run_saved_test_from_package` | Unit | `run_saved_test_from_package()` calls run_saved_test with correct args | ✅ Complete |
| `test_manifest_includes_source_story` | Unit | Verify `source_story` field is persisted after pipeline run | ✅ Verified via `test_write_run_artifacts_creates_package_with_manifest_and_pages` |
| `test_shows_no_evidence_message_when_empty` | Unit | Empty evidence dir shows informative message | ✅ Complete |
| `test_shows_report_paths_from_manifest` | Unit | Report paths from manifest are displayed | ✅ Complete |
| `test_shows_evidence_paths_from_manifest` | Unit | Evidence paths from manifest are displayed | ✅ Complete |
| `test_displays_failure_diagnostics_per_test` | Unit | Failed steps show locator, error, diagnosis | ✅ Complete |
| `test_shows_no_failures_when_all_passed` | Unit | All-passing tests show success message | ✅ Complete |
| `test_shows_multiple_evidence_files` | Unit | Multiple evidence files show count | ✅ Complete |

---

*Last updated: 2026-06-03*
*Supersedes: 2026-06-02 version*