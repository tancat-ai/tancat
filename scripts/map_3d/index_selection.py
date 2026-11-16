"""Which files the 3D map indexes - one rule, shared by the generator and its test.

The indexes are committed and published, so they must describe the REPOSITORY, not
whoever's working tree ran the generator. A filesystem walk did the opposite: it
indexed 1,102 paths that existed only on one machine - exported test output, captured
scrapes under ``scripts/eval/scraped_pages/`` and the private research notes under
``docs/private/`` - so the public map leaked internal note names and nobody else could
reproduce the files (t-1440).

The rule is "only paths git knows about". This module is the single place it lives,
so the generator cannot drift from the test that checks its output: the test asks for
the same selection and fails if a tracked file that should be indexed is missing.

Labels are returned the way the indexes write them, with a ``./`` prefix.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: Directories whose contents are never architecture.
SKIP_DIRS = {
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
    "memory-bank",
    "evidence",
    # Generated graph artifacts — thousands of hashed AST-cache nodes that drown the
    # real architecture in the 3D map (2026-08-13).
    "graphify-out",
}

#: Dotfiles at the repo root that ARE part of the project's shape.
ROOT_CONFIG_FILES = frozenset(
    {
        ".clinerules",
        ".clineignore",
        ".dockerignore",
        ".gitignore",
        ".env.example",
        ".python-version",
        "pyproject.toml",
        "pytest.ini",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "LICENSE",
        "fix.sh",
        "launch_ui.sh",
        "launch_dev.sh",
    }
)

#: Prefixes that must never be indexed, even if a file inside one gets tracked:
#: private notes and captured data are not architecture.
NEVER_INDEXED = (
    "docs/private/",
    "exported_tests/",
    "scripts/eval/scraped_pages/",
    # Committed, but captured page data: a scrape is evidence, not a file a reader
    # navigates the map to.
    "fixtures/scraped_pages/",
)

#: File types with no architectural meaning.
SKIP_EXTENSIONS = (
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".woff",
    ".ttf",
    ".woff2",
    ".map",
    ".lock",
    ".tag",
    ".met",
    ".wheel",
)

#: Paths that are outputs of this generator itself.
SELF_OUTPUTS = frozenset({"3d_map_data.json", "nodes.csv", "links.csv"})

#: Noise that has no place on the map.
SKIP_FRAGMENTS = ("mock_insurance_site", "cart.html", "cline-mcp-memory-bank")


def tracked_files(root: Path) -> list[str]:
    """Every path git tracks, read from the index (never the filesystem)."""
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def is_indexed(rel: str) -> bool:
    """True when the repository path *rel* belongs on the map."""
    if rel.startswith(NEVER_INDEXED):
        return False
    if any(fragment in rel for fragment in SKIP_FRAGMENTS):
        return False

    parts = rel.split("/")
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return False
    if any(part.startswith(".") for part in parts[:-1]):
        return False

    name = parts[-1]
    if name.startswith(".") and rel not in ROOT_CONFIG_FILES:
        return False
    if name.endswith(SKIP_EXTENSIONS):
        return False
    if name.endswith((".xml", ".lock", ".txt", ".log", ".err")) and rel != ".env.example":
        return False
    if name in SELF_OUTPUTS:
        return False
    return True


def select_indexed_files(root: Path) -> list[str]:
    """The labels the indexes must contain for the repository at *root*, sorted."""
    return sorted({f"./{rel}" for rel in tracked_files(root) if is_indexed(rel)})
