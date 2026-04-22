#!/usr/bin/env python3
"""Project sanitizer script for AI-Playwright-Test-Generator.

Automates project cleanup:
1. Auto-move misplaced test files into /tests/
2. Purge junk files (.log, temporary .txt)
3. Audit documentation links against links.csv
4. CI-ready: non-zero exit code if issues found

Usage:
    python scripts/project_sanitizer.py

Exit codes:
    0 - All clean (no misplaced tests)
    1 - Issues found or errors
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

# ────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TESTS_DIR = PROJECT_ROOT / "tests"
LINKS_CSV = PROJECT_ROOT / "docs" / "links.csv"

# Files/directories to skip during scan
SKIP_DIRS: set[str] = {
    ".venv",
    "__pycache__",
    "node_modules",
    ".git",
    "screenshots",
    "htmlcov",
    "pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "playwright",
    "test-results",
    "playwright-report",
    "blob-report",
    "scratch",
    ".uv-cache",
    ".pytest_cache",
    ".tmp",
    ".streamlit",
    ".cache",
    "cline-mcp-memory-bank",
    "generated_tests",
    "evidence",
    "memory-bank",
    ".vscode",
}

# Module directories containing .py files that are NOT test files
# even if they match test_*.py pattern
MODULE_DIRS: set[str] = {
    "src",
    "cli",
    "scripts",
    "assets",
}

# Whitelisted .txt files to keep
TXT_WHITELIST: set[str] = {
    "requirements.txt",
    "LICENSE",
    "CHANGELOG.md",  # Note: .md not .txt
}

# Whitelisted .log files to keep (none by default)
LOG_WHITELIST: set[str] = set()

# Test file patterns to look for
TEST_PATTERNS = ("test_*.py",)

# ────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────


def is_skip_dir(name: str) -> bool:
    """Check if directory should be skipped."""
    return name in SKIP_DIRS or name.startswith(".")


def load_links_csv() -> tuple[set[str], set[str]]:
    """Load links.csv and return (sources, targets) as sets of basenames."""
    sources: set[str] = set()
    targets: set[str] = set()
    if not LINKS_CSV.exists():
        print(f"[WARN] links.csv not found at {LINKS_CSV}")
        return sources, targets
    try:
        with open(LINKS_CSV, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                src = row.get("source", "").strip()
                tgt = row.get("target", "").strip()
                if src:
                    sources.add(src)
                if tgt:
                    targets.add(tgt)
    except Exception as e:
        print(f"[ERROR] Failed to read links.csv: {e}")
    return sources, targets


def find_files_in_dir(pattern: str, root: Path) -> list[Path]:
    """Find files matching pattern in directory (non-recursive for top-level)."""
    return sorted(root.glob(pattern))


def find_all_files_matching_pattern(pattern: str, root: Path, skip_dirs: set[str]) -> list[Path]:
    """Recursively find files matching pattern, skipping specified directories."""
    results: list[Path] = []
    for item in sorted(root.rglob(pattern)):
        if item.is_file():
            # Check if any parent is in skip_dirs
            rel = item.relative_to(root)
            skip = False
            for part in rel.parts[:-1]:  # Check directory parts only
                if part in skip_dirs or part.startswith("."):
                    skip = True
                    break
            if not skip:
                results.append(item)
    return results


# ────────────────────────────────────────────
# Feature 1: Auto-Move Tests
# ────────────────────────────────────────────


def auto_move_tests() -> list[Path]:
    """Find test_*.py files outside /tests/ and move them.

    Only looks in the project root and directories that are NOT
    known module directories (src/, cli/, scripts/, assets/).
    """
    misplaced: list[Path] = []

    for test_file in find_all_files_matching_pattern("test_*.py", PROJECT_ROOT, SKIP_DIRS):
        rel = test_file.relative_to(PROJECT_ROOT)
        # Skip files already in /tests/
        if rel.parts[0] == "tests":
            continue
        # Skip files in generated_tests/
        if rel.parts[0] == "generated_tests":
            continue
        # Skip files in module directories (these are not test files)
        if rel.parts[0] in MODULE_DIRS:
            continue
        misplaced.append(test_file)

    if not misplaced:
        print("[OK] No misplaced test files found.")
        return misplaced

    print(f"\n[MOVE] Found {len(misplaced)} misplaced test file(s):")
    for f in misplaced:
        rel = f.relative_to(PROJECT_ROOT)
        # Maintain directory structure under /tests/
        rel_parts = list(rel.parts)
        # Remove the filename, get the directory structure
        dir_parts = rel_parts[:-1]
        dest = TESTS_DIR / Path(*dir_parts) / rel_parts[-1]

        # Handle name collisions
        if dest.exists():
            filename = Path(rel_parts[-1])
            stem = filename.stem
            suffix = filename.suffix
            counter = 1
            while dest.exists():
                dest = TESTS_DIR / Path(*dir_parts) / f"{stem}_{counter}{suffix}"
                counter += 1

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest))
        print(f"  -> {rel} => {dest.relative_to(PROJECT_ROOT)}")

    return misplaced


# ────────────────────────────────────────────
# Feature 2: Purge Junk
# ────────────────────────────────────────────


def purge_junk() -> list[Path]:
    """Delete .log files and temporary .txt files."""
    purged: list[Path] = []

    # Find .log files
    for log_file in find_all_files_matching_pattern("*.log", PROJECT_ROOT, SKIP_DIRS):
        rel = log_file.relative_to(PROJECT_ROOT)
        if log_file.name in LOG_WHITELIST:
            continue
        try:
            log_file.unlink()
            print(f"  [DEL] {rel}")
            purged.append(rel)
        except Exception as e:
            print(f"  [WARN] Could not delete {rel}: {e}")

    # Find temporary .txt files (exclude whitelisted)
    for txt_file in find_all_files_matching_pattern("*.txt", PROJECT_ROOT, SKIP_DIRS):
        rel = txt_file.relative_to(PROJECT_ROOT)
        if txt_file.name in TXT_WHITELIST or txt_file.name == "requirements.txt":
            continue
        # Exclude UAT output files that might be useful for debugging
        if txt_file.name.startswith("uat_output"):
            continue
        try:
            txt_file.unlink()
            print(f"  [DEL] {rel}")
            purged.append(rel)
        except Exception as e:
            print(f"  [WARN] Could not delete {rel}: {e}")

    if not purged:
        print("[OK] No junk files to purge.")
    else:
        print(f"\n[DEL] Purged {len(purged)} junk file(s).")

    return purged


# ────────────────────────────────────────────
# Feature 3: Audit Links
# ────────────────────────────────────────────


def audit_links() -> list[str]:
    """Compare .md files against links.csv for orphans.

    Normalizes paths to handle ./ prefix variations between
    links.csv and actual file paths.
    """
    sources, targets = load_links_csv()

    if not sources and not targets:
        print("[WARN] Could not load links.csv for audit.")
        return []

    # Normalize all references: strip ./ prefix for consistent comparison
    all_refs: set[str] = set()
    for ref in sources | targets:
        # Strip ./ prefix and normalize path separators
        normalized = ref.lstrip("./").replace("\\", "/")
        all_refs.add(normalized)
        # Also keep original for partial matching
        all_refs.add(ref.lstrip("./"))

    # Find all .md files in the project
    orphan_md: list[str] = []
    for md_file in find_all_files_matching_pattern("*.md", PROJECT_ROOT, SKIP_DIRS):
        rel = str(md_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
        # Normalize: strip ./ prefix
        rel_clean = rel.lstrip("./")
        if rel_clean not in all_refs:
            orphan_md.append(rel)

    if orphan_md:
        print(f"\n[WARN] Found {len(orphan_md)} orphan .md file(s) (not referenced in links.csv):")
        for f in orphan_md:
            print(f"  - {f}")
    else:
        print("[OK] No orphan .md files found.")

    return orphan_md


# ────────────────────────────────────────────
# CLI Argument Parsing
# ────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Project sanitizer for AI-Playwright-Test-Generator.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Report issues without moving/deleting files (CI mode).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes.",
    )
    return parser.parse_args(argv)


# ────────────────────────────────────────────
# Main
# ────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Run all sanitizer steps and return exit code."""
    args = parse_args(argv)

    print("=" * 60)
    print("Project Sanitizer")
    print(f"Root: {PROJECT_ROOT}")
    if args.check_only:
        print("Mode: CHECK-ONLY (CI)")
    elif args.dry_run:
        print("Mode: DRY-RUN")
    else:
        print("Mode: FULL")
    print("=" * 60)

    has_misplaced_tests = False
    has_junk_files = False
    issues_found = False

    # Step 1: Auto-move tests
    print("\n--- Step 1: Auto-Move Tests ---")
    if args.check_only or args.dry_run:
        misplaced = auto_move_tests_check()
    else:
        misplaced = auto_move_tests()
    if misplaced:
        has_misplaced_tests = True
        issues_found = True

    # Step 2: Purge junk
    print("\n--- Step 2: Purge Junk ---")
    if args.check_only or args.dry_run:
        purged = purge_junk_check()
    else:
        purged = purge_junk()
    if purged:
        has_junk_files = True
        issues_found = True

    # Step 3: Audit links
    print("\n--- Step 3: Audit Links ---")
    orphans = audit_links()
    if orphans:
        issues_found = True

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Misplaced tests found: {len(misplaced)}")
    print(f"  Junk files found: {len(purged)}")
    print(f"  Orphan .md files: {len(orphans)}")
    print("=" * 60)

    # CI-critical: only misplaced tests and junk files cause failure
    if has_misplaced_tests:
        print("\n[FAIL] Misplaced test files were found.")
        print("       Exit code 1 — CI pipelines should fail on this.")
        return 1

    if has_junk_files:
        print("\n[FAIL] Junk files were found.")
        print("       Exit code 1 — CI pipelines should fail on this.")
        return 1

    if issues_found:
        print("\n[WARN] Issues found (see above). Review recommended.")
        return 1

    print("\n[OK] Project is clean. No issues found.")
    return 0


def auto_move_tests_check() -> list[Path]:
    """Check for misplaced test files without moving them."""
    misplaced: list[Path] = []

    for test_file in find_all_files_matching_pattern("test_*.py", PROJECT_ROOT, SKIP_DIRS):
        rel = test_file.relative_to(PROJECT_ROOT)
        if rel.parts[0] == "tests":
            continue
        if rel.parts[0] == "generated_tests":
            continue
        if rel.parts[0] in MODULE_DIRS:
            continue
        misplaced.append(test_file)

    if not misplaced:
        print("[OK] No misplaced test files found.")
    else:
        print(f"\n[FAIL] Found {len(misplaced)} misplaced test file(s):")
        for f in misplaced:
            rel = f.relative_to(PROJECT_ROOT)
            print(f"  - {rel}")
    return misplaced


def purge_junk_check() -> list[Path]:
    """Check for junk files without deleting them."""
    purged: list[Path] = []

    for log_file in find_all_files_matching_pattern("*.log", PROJECT_ROOT, SKIP_DIRS):
        rel = log_file.relative_to(PROJECT_ROOT)
        if log_file.name in LOG_WHITELIST:
            continue
        purged.append(rel)

    for txt_file in find_all_files_matching_pattern("*.txt", PROJECT_ROOT, SKIP_DIRS):
        rel = txt_file.relative_to(PROJECT_ROOT)
        if txt_file.name in TXT_WHITELIST or txt_file.name == "requirements.txt":
            continue
        if txt_file.name.startswith("uat_output"):
            continue
        purged.append(rel)

    if not purged:
        print("[OK] No junk files found.")
    else:
        print(f"\n[FAIL] Found {len(purged)} junk file(s):")
        for f in purged:
            print(f"  - {f}")
    return purged


if __name__ == "__main__":
    sys.exit(main())
