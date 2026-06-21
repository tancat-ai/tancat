# `src/export_service.py`

## High-Level Purpose

`export_service.py` builds clean, runnable exports from generated Playwright test packages. Its main responsibility is to copy and rewrite selected package artifacts into an `exported_tests`-style output directory while removing `EvidenceTracker` dependencies from test code and page object modules.

The module supports two export modes through `ExportMode`:

- `ExportMode.POM`: exports `test_*.py` files plus matching `pages/po_*.py` page object modules.
- Non-POM / flat mode: exports only cleaned `test_*.py` files plus shared metadata and support artifacts.

It also generates a clean `conftest.py`, updates or copies package metadata, optionally carries forward scrape and SQLite evidence artifacts, and writes an export-facing `README.md`.

## Imports and Dependencies

- `json`: parses and serializes `package_manifest.json`.
- `shutil`: copies manifest and SQLite files while preserving file metadata via `copy2`.
- `datetime.datetime`: creates timestamped export directories and export metadata.
- `pathlib.Path`: normalizes and manipulates filesystem paths.
- `typing.Any`: annotates decoded JSON manifest dictionaries.
- `.code_postprocessor.strip_evidence_from_pom`: removes evidence-related code from page object modules.
- `.code_postprocessor.strip_evidence_from_test_code`: removes evidence-related code from generated tests.
- `.pipeline_models.ExportMode`: controls whether the export is POM or flat.

## Public API

### `export_clean_suite`

```python
def export_clean_suite(
    *,
    source_package_dir: str | Path,
    export_mode: ExportMode,
    output_base_dir: str = "exported_tests",
    story_slug: str = "",
) -> ExportResult:
```

Exports a clean test suite from a generated package directory.

Parameters:

- `source_package_dir: str | Path`: path to the generated test package to export.
- `export_mode: ExportMode`: export shape, currently distinguishing POM exports from flat exports.
- `output_base_dir: str = "exported_tests"`: base directory where timestamped export folders are created.
- `story_slug: str = ""`: optional slug used in the export directory name. If omitted, the slug is inferred from the source package directory name.

Returns:

- `ExportResult`: object containing paths to the export directory, exported test files, exported page objects, generated `conftest.py`, and generated `README.md`.

Raises:

- `FileNotFoundError`: raised when `source_package_dir` does not exist.

Behavior:

1. Converts `source_package_dir` to `Path` and verifies it exists.
2. Creates a timestamped export directory under `output_base_dir`.
3. In POM mode, reads `pages/po_*.py`, strips evidence code, and writes cleaned page objects to `export_dir/pages/`.
4. Reads each root-level `test_*.py`, strips evidence code, and writes cleaned tests to the export directory.
5. Writes a clean `conftest.py` without custom evidence fixtures.
6. Copies `scrape_manifest.json` when present.
7. Copies `playwright_tests.db` and related WAL/SHM files when present under either `evidence/` or the package root.
8. Updates `package_manifest.json` with export metadata when valid JSON is available, or copies the original manifest if JSON decoding fails.
9. Generates an export `README.md`.
10. Returns an `ExportResult` with exported artifact paths.

## Classes

### `ExportResult`

```python
class ExportResult:
```

Simple result container for an export operation.

#### `__init__`

```python
def __init__(
    self,
    *,
    export_dir: str,
    test_files: list[str],
    page_objects: list[str],
    conftest: str,
    readme: str,
) -> None:
```

Parameters:

- `export_dir: str`: path to the export directory.
- `test_files: list[str]`: paths to exported test files.
- `page_objects: list[str]`: paths to exported page object files.
- `conftest: str`: path to generated `conftest.py`.
- `readme: str`: path to generated `README.md`.

Returns:

- `None`.

Attributes:

- `self.export_dir`
- `self.test_files`
- `self.page_objects`
- `self.conftest`
- `self.readme`

#### `summary`

```python
def summary(self) -> str:
```

Returns a human-readable multiline summary of the export.

Parameters:

- None.

Returns:

- `str`: summary containing export destination and counts for tests, page objects, conftest, and README.

## Private Helpers

### `_write_clean_conftest`

```python
def _write_clean_conftest(export_dir: Path, export_mode: ExportMode) -> None:
```

Writes a minimal generated `conftest.py` into the export directory.

Parameters:

- `export_dir: Path`: directory where `conftest.py` should be written.
- `export_mode: ExportMode`: mode used only to label the generated file as `POM` or `Flat`.

Returns:

- `None`.

Side effects:

- Writes `export_dir / "conftest.py"` using UTF-8.

### `_update_package_manifest`

```python
def _update_package_manifest(source: Path, export_dir: Path, export_mode: ExportMode) -> None:
```

Copies or updates `package_manifest.json` with export metadata.

Parameters:

- `source: Path`: generated package directory containing the source manifest.
- `export_dir: Path`: export directory where the updated manifest should be written.
- `export_mode: ExportMode`: determines whether `export_mode` metadata is written as `"pom"` or `"flat"`.

Returns:

- `None`.

Behavior:

- If `source / "package_manifest.json"` does not exist, returns without writing anything.
- If the manifest cannot be decoded as JSON, copies it unchanged into the export directory.
- If decoding succeeds, adds:
  - `export_mode`
  - `exported_at`
- Writes formatted JSON with two-space indentation.

Side effects:

- May copy or write `export_dir / "package_manifest.json"`.

### `_generate_export_readme`

```python
def _generate_export_readme(export_dir: Path, export_mode: ExportMode, source: Path) -> None:
```

Generates a README describing the exported test suite.

Parameters:

- `export_dir: Path`: directory where `README.md` should be written.
- `export_mode: ExportMode`: controls mode labels and whether a page object note is included.
- `source: Path`: source generated package used to read metadata from `package_manifest.json`.

Returns:

- `None`.

Behavior:

- Reads `source / "package_manifest.json"` when present and valid.
- Extracts optional metadata:
  - `source_story`
  - `starting_url`
  - `provider`
  - `model`
  - `created_at`
- Detects whether `export_dir / "evidence" / "playwright_tests.db"` exists.
- Writes a README with generation/export timestamps, mode, story and provider metadata, content notes, a basic pytest command, and export limitations.

Side effects:

- Writes `export_dir / "README.md"` using UTF-8.

## Key Architectural Patterns

### Export-Oriented Service Function

The module centers on `export_clean_suite` as a single orchestration function. It validates input, prepares the destination, delegates specialized writing tasks to private helpers, and returns a compact result object.

### Filesystem Transformation Pipeline

The export process is a filesystem pipeline:

1. Read generated package artifacts.
2. Transform code by stripping evidence-related dependencies.
3. Write cleaned artifacts into a new timestamped export directory.
4. Copy optional metadata and evidence database artifacts.
5. Generate export-specific support files.

### Mode-Based Branching

`ExportMode` gates POM-specific behavior. POM mode includes `pages/po_*.py` processing and page object README notes; flat mode skips page object export but otherwise uses the same evidence-stripping path for test files.

### Private Writer Helpers

Support-file generation is separated into private helpers:

- `_write_clean_conftest` owns conftest creation.
- `_update_package_manifest` owns manifest update/copy behavior.
- `_generate_export_readme` owns human-readable export documentation.

This keeps the public function focused on orchestration while leaving output-format details close to the writer functions.

### Defensive Metadata Handling

The manifest helpers tolerate missing or invalid `package_manifest.json` files:

- Missing manifests are ignored.
- Invalid JSON is copied unchanged for preservation.
- README metadata falls back to empty strings or `"Unknown"`.

### Lightweight Result Object

`ExportResult` is a manually defined container rather than a dataclass. It stores string paths and provides a `summary()` formatter for UI or CLI presentation.

## External Side Effects

This module performs direct filesystem writes and copies:

- Creates a timestamped export directory.
- Creates `pages/` and `evidence/` subdirectories when needed.
- Writes cleaned Python files.
- Writes generated `conftest.py`, `README.md`, and JSON metadata.
- Copies scrape manifests and SQLite database artifacts.

It does not run exported tests, invoke Playwright, or call an LLM.

## Notable Implementation Details

- Export directories are named with `datetime.now().strftime("%Y%m%d_%H%M%S")`.
- When `story_slug` is not provided, the slug is derived from the source directory name by dropping the first underscore-delimited segment when possible.
- Test files are discovered using `source.glob("test_*.py")`.
- Page object files are discovered using `source / "pages"` and `glob("po_*.py")`.
- SQLite evidence databases are searched in both `source / "evidence"` and the package root.
- WAL and SHM companion files are copied when present.
- Generated support files use UTF-8 encoding.
