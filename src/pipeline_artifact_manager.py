"""Persist and reload generated test package metadata.

Provides a thin persistence layer for package-level metadata (user story,
provider/model, report paths, evidence paths) that complements
``run_result_persistence.py`` which handles pytest run outcomes.

No Streamlit imports — fully unit-testable in isolation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PackageManifest:
    """Metadata descriptor for one generated test package.

    Written as ``package_manifest.json`` inside each package directory
    and loaded when the user wants to re-open a previously generated suite.
    """

    package_name: str = ""
    created_at: str = ""  # ISO-8601 timestamp
    source_story: str = ""
    starting_url: str = ""
    additional_urls: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    generated_test_files: list[str] = field(default_factory=list)
    page_object_files: list[str] = field(default_factory=list)
    scrape_manifest_path: str = ""
    reports: list[dict[str, Any]] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)
    run_results_count: int = 0
    last_run_at: str = ""  # ISO-8601, updated by run_result_persistence on each run

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackageManifest:
        """Construct from a plain dict."""
        return cls(
            package_name=data.get("package_name", ""),
            created_at=data.get("created_at", ""),
            source_story=data.get("source_story", ""),
            starting_url=data.get("starting_url", ""),
            additional_urls=data.get("additional_urls", []),
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            generated_test_files=data.get("generated_test_files", []),
            page_object_files=data.get("page_object_files", []),
            scrape_manifest_path=data.get("scrape_manifest_path", ""),
            reports=data.get("reports", []),
            evidence_paths=data.get("evidence_paths", []),
            run_results_count=data.get("run_results_count", 0),
            last_run_at=data.get("last_run_at", ""),
        )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_FILENAME = "package_manifest.json"
SCRAPE_MANIFEST_FILENAME = "scrape_manifest.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_package_manifest(package_root: Path, manifest: PackageManifest) -> None:
    """Write a ``PackageManifest`` as JSON to *package_root*.

    Args:
        package_root: Directory where the package lives (e.g.
            ``generated_tests/test_20260602_login``).
        manifest: Fully populated manifest to persist.
    """
    filepath = package_root / MANIFEST_FILENAME
    filepath.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_package_manifest(
    manifest_path: Path,
    *,
    reconstruct: bool = False,
) -> PackageManifest:
    """Load a ``PackageManifest`` from disk.

    Args:
        manifest_path: Path to ``package_manifest.json`` (or package root
            when *reconstruct* is True).
        reconstruct: When True and the manifest file is absent, build a
            minimal manifest from on-disk artefacts.

    Returns:
        A populated ``PackageManifest``.

    Raises:
        FileNotFoundError: When the manifest does not exist and
            *reconstruct* is False.
    """
    if reconstruct and not manifest_path.name == MANIFEST_FILENAME:
        # manifest_path is the package root — try canonical file first
        canonical = manifest_path / MANIFEST_FILENAME
        if canonical.exists():
            return _load_from_file(canonical)
        return _reconstruct_manifest(manifest_path)

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Package manifest not found: {manifest_path}. Use reconstruct=True to build a minimal manifest from disk."
        )
    return _load_from_file(manifest_path)


def find_existing_packages(base_dir: Path) -> list[PackageManifest]:
    """Discover previously generated packages under *base_dir*.

    Scans ``base_dir`` for subdirectories that either contain
    ``package_manifest.json`` (preferred) or fall back to directories
    with ``test_*.py`` files (legacy packages without a manifest).

    Returns:
        Manifests sorted by ``created_at`` descending (newest first).
        Legacy packages are reconstructed on-the-fly and marked with
        ``created_at`` derived from the oldest file mtime.
    """
    manifests: list[PackageManifest] = []

    if not base_dir.exists():
        return manifests

    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir():
            continue

        # Skip helper directories (e.g. __pycache__)
        if entry.name.startswith("__"):
            continue

        canonical = entry / MANIFEST_FILENAME
        if canonical.exists():
            loaded = _load_from_file(canonical)
            # Refresh dynamic fields
            loaded.run_results_count = _count_run_results(entry)
            manifests.append(loaded)
        elif _looks_like_package(entry):
            manifests.append(_reconstruct_manifest(entry))

    # Sort by created_at descending (newest first)
    manifests.sort(key=lambda m: m.created_at, reverse=True)
    return manifests


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_from_file(filepath: Path) -> PackageManifest:
    """Parse a JSON manifest file."""
    data = json.loads(filepath.read_text(encoding="utf-8"))
    manifest = PackageManifest.from_dict(data)
    # Ensure package_name is populated
    if not manifest.package_name:
        manifest.package_name = filepath.parent.name
    return manifest


def _reconstruct_manifest(package_root: Path) -> PackageManifest:
    """Build a minimal ``PackageManifest`` from on-disk artefacts.

    Used for legacy packages that predate ``package_manifest.json``.
    """
    test_files = _scan_test_files(package_root)
    po_files = _scan_page_object_files(package_root)

    # Derive created_at from oldest file mtime
    all_files = list(package_root.rglob("*.py")) + list(package_root.glob("*.json"))
    created_at = ""
    if all_files:
        oldest = min(all_files, key=lambda f: f.stat().st_mtime)
        created_at = datetime.fromtimestamp(oldest.stat().st_mtime, tz=None).isoformat()

    scrape_path = ""
    scrape_file = package_root / SCRAPE_MANIFEST_FILENAME
    if scrape_file.exists():
        scrape_path = SCRAPE_MANIFEST_FILENAME

    run_count = _count_run_results(package_root)

    return PackageManifest(
        package_name=package_root.name,
        created_at=created_at,
        source_story="unknown",
        starting_url="unknown",
        additional_urls=[],
        provider="unknown",
        model="unknown",
        generated_test_files=test_files,
        page_object_files=po_files,
        scrape_manifest_path=scrape_path,
        reports=[],
        evidence_paths=[],
        run_results_count=run_count,
        last_run_at="",
    )


def _looks_like_package(directory: Path) -> bool:
    """Heuristic: does the directory look like a generated test package?

    A directory is considered a package if it contains at least one
    ``test_*.py`` file or a ``scrape_manifest.json``.
    """
    return bool(list(directory.glob("test_*.py")) or (directory / SCRAPE_MANIFEST_FILENAME).exists())


def _scan_test_files(package_root: Path) -> list[str]:
    """Return relative test file names in the package root."""
    return sorted(f.name for f in package_root.glob("test_*.py"))


def _scan_page_object_files(package_root: Path) -> list[str]:
    """Return relative page-object file names under ``pages/``."""
    pages_dir = package_root / "pages"
    if not pages_dir.is_dir():
        return []
    return sorted(str(f.relative_to(package_root)) for f in pages_dir.glob("*.py") if not f.name.startswith("__"))


def _count_run_results(package_root: Path) -> int:
    """Count run-result JSON files in or under the package."""
    # Run results may live inside the package or in evidence/run_results/
    direct = list(package_root.glob("run_results_*.json"))
    # Also check evidence subdirectory
    evidence_dir = package_root / "evidence"
    if evidence_dir.is_dir():
        evidence_dir_results = list(evidence_dir.glob("run_results_*.json"))
        return len(direct) + len(evidence_dir_results)
    return len(direct)


# ---------------------------------------------------------------------------
# Report / evidence helpers
# ---------------------------------------------------------------------------


def add_report_to_manifest(
    manifest: PackageManifest,
    report_format: str,
    report_path: str,
) -> None:
    """Append a report entry to the manifest's report list.

    Args:
        manifest: The manifest to update (modified in-place).
        report_format: One of ``"local"``, ``"jira"``, ``"html"``.
        report_path: Filesystem path to the generated report.
    """
    manifest.reports.append(
        {
            "format": report_format,
            "path": report_path,
            "generated_at": datetime.now(UTC).isoformat(),
        }
    )


def update_last_run_at(manifest: PackageManifest, timestamp: str | None = None) -> None:
    """Set ``last_run_at`` on the manifest to the given or current time.

    Args:
        manifest: The manifest to update (modified in-place).
        timestamp: ISO-8601 string. Defaults to now (UTC).
    """
    manifest.last_run_at = timestamp or datetime.now(UTC).isoformat()
    manifest.run_results_count += 1
