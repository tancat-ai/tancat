# FEATURE SPEC — Persist Generated Tests Across Sessions
## AI-026

**Status:** Ready for implementation
**Last updated:** 2026-05-06
**Depends on:** `src/pipeline_writer.py`, `cli/main.py`, `streamlit_app.py`
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

## Goals

1. Allow the CLI to load an existing generated test package from disk.
2. Preserve relevant metadata, evidence, and report links for previously generated suites.
3. Enable rerunning saved test suites without re-triggering the LLM pipeline.
4. Keep Streamlit and CLI aligned by sharing the same artifact persistence helpers.
5. Maintain the current output-only rule for generated tests: they are not part of `tests/`.

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

---

## Feature Scope

### In scope

- `Snapshot` package metadata for each generated suite in a manifest JSON file.
- CLI menu commands such as `Load Existing Generated Tests` and `Re-run Saved Suite`.
- A reusable persistence helper in `src/` that can save and load package descriptors.
- Preservation of generated file paths, evidence locations, report outputs, and any
  pipeline state needed to rerun or inspect the suite.
- Streamlit UI support for loading an existing saved package and displaying its
  associated reports/diagnostics.

### Out of scope

- Regenerating tests from an old suite automatically.
- Editing saved generated tests in place via the persistence layer.
- Making generated tests discoverable by `pytest` automatically through `tests/`.
- Converting existing artifacts into a new package format unless the manifest is
  backward-compatible with current `generated_tests/` layout.

---

## Implementation Plan

### 1. `src/pipeline_artifact_manager.py`

Create a shared helper module responsible for loading and saving generated suite metadata.
This module should define a package descriptor schema and expose:

- `save_package_manifest(package_root: Path, manifest: PackageManifest) -> None`
- `load_package_manifest(manifest_path: Path) -> PackageManifest`
- `find_existing_packages(base_dir: Path) -> list[PackageManifest]`

### 2. Package Manifest Schema

Store the metadata in a JSON file beside generated tests, for example:

- `generated_tests/<package_name>/manifest.json`

Manifest fields should include:

- `package_name`
- `created_at`
- `source_story`
- `generated_test_files`
- `reports`
- `evidence_paths`
- `pipeline_artifacts`
- `provider`
- `model`
- `run_results_path` (optional)

### 3. CLI Menu Enhancements

Update `cli/main.py` to add new commands:

- `Load Existing Generated Tests`
- `Show Saved Package Metadata`
- `Re-run Saved Suite`

The CLI should load the manifest, display high-level package info, and allow the user
to rerun the saved suite via pytest or the existing run orchestration code.

### 4. Streamlit UI Support

Add an optional Streamlit control for loading an existing package directory or manifest.
When a package is loaded, display its metadata and offer to rerun the suite. Reuse the
same `src/pipeline_artifact_manager.py` helpers used by the CLI.

### 5. Preserve Diagnostic Data

When loading a saved package, include any available failure diagnostics and report
paths in the displayed metadata. This makes it possible to inspect prior results without
regenerating.

---

## Success Criteria

- A saved generated test package can be loaded from disk in the CLI.
- The CLI can rerun a loaded saved package without regenerating tests.
- Loaded packages expose their previously generated report locations.
- Streamlit can load the same package format and surface the same metadata.
- Existing generation behavior continues to work for new packages.
