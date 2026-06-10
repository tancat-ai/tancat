"""Export generated test packages with EvidenceTracker stripped."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .code_postprocessor import strip_evidence_from_pom, strip_evidence_from_test_code
from .pipeline_models import ExportMode


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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = story_slug or "_".join(source.name.split("_")[1:]) if len(source.name.split("_")) > 1 else source.name
    export_dir = Path(output_base_dir) / f"{timestamp}_{slug}"
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

            for po_file in pages_dir.glob("po_*.py"):
                raw_pom = po_file.read_text(encoding="utf-8")
                clean_pom = strip_evidence_from_pom(raw_pom)
                out_path = export_pages_dir / po_file.name
                out_path.write_text(clean_pom, encoding="utf-8")
                page_objects_exported.append(str(out_path))

    # Process test files
    for test_file in source.glob("test_*.py"):
        raw_test = test_file.read_text(encoding="utf-8")

        if export_mode == ExportMode.POM:
            # In POM mode, still strip evidence_tracker calls from test file
            # (assertions use direct evidence_tracker calls)
            clean_test = strip_evidence_from_test_code(raw_test)
        else:
            # Flat mode: strip all evidence tracker calls
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
