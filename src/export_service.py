"""Export generated test packages with EvidenceTracker stripped."""

from __future__ import annotations

import ast
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .code_postprocessor import strip_evidence_from_pom, strip_evidence_from_test_code
from .pipeline_models import ExportMode

# B-032: AI-012 (2026-06-15) swapped the JSON-dir run history for a single
# SQLite file named ``run_results.sqlite`` (src/sqlite_persistence.py). The
# export service kept copying ``playwright_tests.db`` — a name nothing in the
# repo ever creates — so the run-history copy was a silent no-op. Export
# prefers the current name and falls back to the legacy one for old packages.
_DB_FILENAMES: tuple[str, ...] = ("run_results.sqlite", "playwright_tests.db")


def _find_sqlite_db(source: Path) -> Path | None:
    """Locate the package run-history SQLite DB (current or legacy name)."""
    for db_name in _DB_FILENAMES:
        for candidate in (source / "evidence" / db_name, source / db_name):
            if candidate.exists():
                return candidate
    return None


def _is_docstring_statement(stmt: ast.stmt) -> bool:
    """Return True for a bare string-expression statement (docstring)."""
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)


def _is_stub_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True when a test function body contains no real test logic.

    A function is a stub when every non-docstring statement is ``pass``,
    ``...`` (Ellipsis), or a bare ``pytest.skip(...)`` call. B-031 found 34 of
    35 exports were exactly this shape (``def test_x(page): pass``) — exports
    run against empty/stub source packages with no guard.
    """
    body = [stmt for stmt in node.body if not _is_docstring_statement(stmt)]
    if not body:
        return True
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "skip"
                and isinstance(func.value, ast.Name)
                and func.value.id == "pytest"
            ):
                continue
        return False
    return True


def _count_stub_functions(source: Path) -> tuple[int, int]:
    """Return ``(stub_test_count, total_test_count)`` across ``test_*.py`` files."""
    stub_count = 0
    total_count = 0
    for test_file in sorted(source.glob("test_*.py")):
        try:
            tree = ast.parse(test_file.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                total_count += 1
                if _is_stub_function(node):
                    stub_count += 1
    return stub_count, total_count


def _guard_stub_source(source: Path) -> None:
    """Raise ValueError when the source package has nothing runnable to export.

    B-031: guard against stub/empty source packages — without this, exporting
    an empty/stub package silently produces a non-runnable suite (the exact
    failure mode that left 34/35 exports in exported_tests/ as ``pass``
    stubs).
    """
    stub_count, total_count = _count_stub_functions(source)
    if total_count == 0:
        raise ValueError(
            f"Refusing to export '{source.name}': no test functions found in any test_*.py file. "
            "Generate a real package before exporting."
        )
    if stub_count == total_count:
        raise ValueError(
            f"Refusing to export '{source.name}': all {total_count} test function(s) are stubs "
            "(bodies are only `pass` / `...` / `pytest.skip()`). Generate a real package before exporting."
        )


def export_clean_suite(
    *,
    source_package_dir: str | Path,
    export_mode: ExportMode,
    output_base_dir: str = "exported_tests",
    story_slug: str = "",
) -> ExportResult:
    """Export a clean test suite from a generated package.

    Args:
        source_package_dir: Path to the generated_tests package directory.
        export_mode: Either ExportMode.POM or ExportMode.FLAT.
        output_base_dir: Base directory for exported suites.
        story_slug: Slug for the output directory name.

    Returns:
        ExportResult with paths to exported artifacts.
    """
    source = Path(source_package_dir)
    if not source.exists():
        raise FileNotFoundError(f"Source package directory does not exist: {source}")

    # B-031: refuse to export stub/empty source packages.
    _guard_stub_source(source)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = story_slug or "_".join(source.name.split("_")[1:]) if len(source.name.split("_")) > 1 else source.name
    # Guard against same-second collisions (e.g. back-to-back exports in a
    # gate script): never silently overwrite an existing export directory.
    export_dir = Path(output_base_dir) / f"{timestamp}_{slug}"
    counter = 1
    while export_dir.exists():
        export_dir = Path(output_base_dir) / f"{timestamp}_{slug}_{counter}"
        counter += 1
    export_dir.mkdir(parents=True, exist_ok=True)

    test_files_exported: list[str] = []
    page_objects_exported: list[str] = []

    # Process POM classes (POM mode only)
    if export_mode == ExportMode.POM:
        pages_dir = source / "pages"
        if pages_dir.exists():
            export_pages_dir = export_dir / "pages"
            export_pages_dir.mkdir(parents=True, exist_ok=True)
            (export_pages_dir / "__init__.py").write_text("", encoding="utf-8")

            for po_file in sorted(pages_dir.glob("*.py")):
                if po_file.name == "__init__.py":
                    continue
                raw_pom = po_file.read_text(encoding="utf-8")
                clean_pom = strip_evidence_from_pom(raw_pom)
                out_path = export_pages_dir / po_file.name
                out_path.write_text(clean_pom, encoding="utf-8")
                page_objects_exported.append(str(out_path))

    # Process test files
    for test_file in source.glob("test_*.py"):
        raw_test = test_file.read_text(encoding="utf-8")

        if export_mode == ExportMode.POM:
            # POM mode: keep POM imports/instantiations/method calls, strip
            # only the evidence_tracker layer (decorators, calls, param, and
            # the tracker argument in POM instantiations).
            clean_test = strip_evidence_from_test_code(raw_test, preserve_pom_calls=True)
        else:
            # Flat mode: strip all evidence tracker calls and inline the
            # resolved selectors (POM → flat conversion).
            clean_test = strip_evidence_from_test_code(raw_test)

        out_path = export_dir / test_file.name
        out_path.write_text(clean_test, encoding="utf-8")
        test_files_exported.append(str(out_path))

    # Generate clean conftest.py
    _write_clean_conftest(export_dir, export_mode)

    # Copy scrape_manifest.json
    manifest_src = source / "scrape_manifest.json"
    if manifest_src.exists():
        shutil.copy2(str(manifest_src), str(export_dir / "scrape_manifest.json"))

    # Copy SQLite database (AI-012: single file replaces JSON directory).
    # B-032: the run-history DB is run_results.sqlite — playwright_tests.db is
    # a legacy name nothing writes anymore (fallback kept for old packages).
    sqlite_db_src = _find_sqlite_db(source)
    if sqlite_db_src is not None:
        evidence_dest = export_dir / "evidence"
        evidence_dest.mkdir(parents=True, exist_ok=True)
        dest_db = evidence_dest / sqlite_db_src.name
        shutil.copy2(str(sqlite_db_src), str(dest_db))
        # Also copy WAL and SHM files if they exist (WAL mode artifacts)
        for suffix in ("-wal", "-shm"):
            wal_src = sqlite_db_src.parent / f"{sqlite_db_src.name}{suffix}"
            if wal_src.exists():
                shutil.copy2(str(wal_src), str(evidence_dest / wal_src.name))

    # Update package_manifest.json with export info
    _update_package_manifest(source, export_dir, export_mode)

    # Generate README.md
    _generate_export_readme(export_dir, export_mode, source)

    return ExportResult(
        export_dir=str(export_dir),
        test_files=test_files_exported,
        page_objects=page_objects_exported,
        conftest=str(export_dir / "conftest.py"),
        readme=str(export_dir / "README.md"),
    )


class ExportResult:
    """Result of an export operation."""

    def __init__(
        self,
        *,
        export_dir: str,
        test_files: list[str],
        page_objects: list[str],
        conftest: str,
        readme: str,
    ) -> None:
        self.export_dir = export_dir
        self.test_files = test_files
        self.page_objects = page_objects
        self.conftest = conftest
        self.readme = readme

    def summary(self) -> str:
        """Return a human-readable summary of the export."""
        lines = [
            f"Exported to: {self.export_dir}",
            f"  Tests: {len(self.test_files)}",
            f"  Page Objects: {len(self.page_objects)}",
            "  Conftest: 1",
            "  README: 1",
        ]
        return "\n".join(lines)


def _write_clean_conftest(export_dir: Path, export_mode: ExportMode) -> None:
    """Write a clean conftest.py without evidence_tracker fixture."""
    mode_label = "POM" if export_mode == ExportMode.POM else "Flat"
    conftest_content = f'''"""Auto-generated conftest for exported test suite.
Exported: {datetime.now().isoformat()}
Mode: {mode_label}
"""

# Standard Playwright fixtures are provided by pytest-playwright.
# No custom fixtures needed for clean export.
'''
    (export_dir / "conftest.py").write_text(conftest_content, encoding="utf-8")


def _update_package_manifest(source: Path, export_dir: Path, export_mode: ExportMode) -> None:
    """Copy and update package_manifest.json with export metadata."""
    manifest_src = source / "package_manifest.json"
    if not manifest_src.exists():
        return

    try:
        manifest_data: dict[str, Any] = json.loads(manifest_src.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        shutil.copy2(str(manifest_src), str(export_dir / "package_manifest.json"))
        return

    mode_label = "pom" if export_mode == ExportMode.POM else "flat"
    manifest_data["export_mode"] = mode_label
    manifest_data["exported_at"] = datetime.now().isoformat()

    (export_dir / "package_manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")


def _generate_export_readme(export_dir: Path, export_mode: ExportMode, source: Path) -> None:
    """Generate README.md with export metadata."""
    mode_label = "POM" if export_mode == ExportMode.POM else "Flat"

    # Try to read source story from package_manifest.json
    source_story = ""
    base_url = ""
    provider = ""
    model = ""

    manifest_path = source / "package_manifest.json"
    if manifest_path.exists():
        try:
            data: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_story = data.get("source_story", "")
            base_url = data.get("starting_url", "")
            provider = data.get("provider", "")
            model = data.get("model", "")
        except json.JSONDecodeError:
            pass

    pages_note = "- `pages/` — Page object modules" if export_mode == ExportMode.POM else ""
    package_name = export_dir.name

    # Read created_at from package_manifest.json
    generated_at = "Unknown"
    if manifest_path.exists():
        try:
            manifest_data: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
            generated_at = manifest_data.get("created_at", "Unknown")
        except json.JSONDecodeError:
            pass

    # Check if SQLite DB was included in export
    has_sqlite = (export_dir / "evidence" / "run_results.sqlite").exists()
    if not has_sqlite:
        has_sqlite = (export_dir / "evidence" / "playwright_tests.db").exists()
    sqlite_note = "- `evidence/run_results.sqlite` — Run history (SQLite)" if has_sqlite else ""

    readme = f"""# Exported Test Suite: {package_name}

**Generated:** {generated_at}
**Exported:** {datetime.now().isoformat()}
**Export Mode:** {mode_label}
**Source Story:** {source_story}
**Base URL:** {base_url}
**LLM Provider:** {provider} / {model}

## Contents
- `test_*.py` — Generated test files
{pages_note}
{sqlite_note}
- `scrape_manifest.json` — Original scrape data
- `package_manifest.json` — Package metadata

## Running Tests
```bash
pytest test_*.py -v
```

## Notes
- EvidenceTracker dependency has been stripped
- Tests use standard Playwright locators
- Screenshot evidence and failure diagnostics are not captured
"""
    (export_dir / "README.md").write_text(readme, encoding="utf-8")
