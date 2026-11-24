"""Release guards: every reason a tag must NOT reach PyPI, checked before it does.

The workflow calls this once, after the build and before the upload, and each
guard owns its message so a failure says exactly what is wrong:

1. **the tag matches the packaged version** - ``v1.0.0`` for ``version = "1.0.0"``;
2. **no file is 100 MB or more** - PyPI's per-file limit, with the size printed;
   a long log is often the file that exceeded it, including one kept for the
   ``docs`` extra, and the totals are printed whether or not anything fails;
3. **the licence record check passes** - ``licence_record.py --check``, so the
   shipped metadata still matches ``uv.lock``;
4. **the commit is on main** - a release comes from merged history, never from a
   feature branch.

Usage::

    python scripts/release_guards.py --tag v1.0.0 --dist dist
    python scripts/release_guards.py --tag v1.0.0 --dist dist --repo-root .

Exit code 0 when every guard passes, 1 on the first failure (with its message).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

#: PyPI's per-file limit: a file of this size or larger is refused.
MAX_FILE_BYTES = 100 * 1024 * 1024


def packaged_version(repo_root: Path) -> str:
    """``[project].version`` from pyproject.toml."""
    with (repo_root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def tag_matches_version(tag: str, repo_root: Path) -> tuple[bool, str]:
    """Guard 1: the tag is ``v`` + the packaged version."""
    version = packaged_version(repo_root)
    expected = f"v{version}"
    if tag != expected:
        return False, (
            f"tag '{tag}' does not match the packaged version '{expected}'. "
            f"Bump [project].version in pyproject.toml to {version} (or tag {expected}) before releasing."
        )
    return True, f"tag '{tag}' matches [project].version {version}"


def file_sizes(dist: Path) -> list[tuple[Path, int]]:
    """Every distribution file and its size, in name order."""
    return [(path, path.stat().st_size) for path in sorted(dist.iterdir()) if path.is_file()]


def files_within_limit(dist: Path, limit: int = MAX_FILE_BYTES) -> tuple[bool, str]:
    """Guard 2: no file reaches PyPI's per-file limit; the sizes are printed."""
    sizes = file_sizes(dist)
    if not sizes:
        return False, f"no distribution files in '{dist}' - there is nothing to publish"
    too_big = [(path.name, size) for path, size in sizes if size >= limit]
    listing = ", ".join(f"{name} {size / 1024 / 1024:.2f} MB" for name, size in too_big) or "none"
    detail = f"{len(sizes)} file(s): " + ", ".join(f"{path.name} {size / 1024 / 1024:.2f} MB" for path, size in sizes)
    if too_big:
        return False, (
            f"{len(too_big)} file(s) at or over PyPI's 100 MB limit ({listing}). "
            f"Remove the large file from the build (a log or data file in the package?), then rebuild. {detail}"
        )
    return True, f"every file is under the 100 MB limit ({detail})"


def licence_record_ok(repo_root: Path) -> tuple[bool, str]:
    """Guard 3: the committed licence record matches ``uv.lock``."""
    script = repo_root / "scripts" / "maintenance" / "licence_record.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"], cwd=repo_root, capture_output=True, text=True, timeout=120
    )
    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    if result.returncode != 0:
        return (
            False,
            f"the licence record check failed - run scripts/maintenance/licence_record.py --write. {output[:400]}",
        )
    return True, output or "the licence record matches uv.lock"


def tag_is_on_main(repo_root: Path, base: str = "origin/main") -> tuple[bool, str]:
    """Guard 4: the checked-out commit is contained in *base* (default origin/main)."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", base],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return False, (
            f"this commit is not on {base}. A release must be tagged on main, after the change is "
            f"merged - never from a feature branch."
        )
    return True, f"the commit is on {base}"


def run_guards(tag: str, dist: Path, repo_root: Path) -> tuple[bool, list[str]]:
    """Run all four guards in order; return (ok, one line per guard)."""
    lines: list[str] = []
    checks = (
        ("tag matches version", lambda: tag_matches_version(tag, repo_root)),
        ("file sizes", lambda: files_within_limit(dist)),
        ("licence record", lambda: licence_record_ok(repo_root)),
        ("tag on main", lambda: tag_is_on_main(repo_root)),
    )
    for name, check in checks:
        ok, message = check()
        lines.append(f"[{'OK' if ok else 'REFUSED'}] {name}: {message}")
        if not ok:
            return False, lines
    return True, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refuse a tag that must not reach PyPI.")
    parser.add_argument("--tag", required=True, help="The tag being released, e.g. v1.0.0")
    parser.add_argument("--dist", required=True, help="Directory holding the built wheel and sdist")
    parser.add_argument("--repo-root", default=".", help="Repository root (default: current directory)")
    args = parser.parse_args(argv)

    ok, lines = run_guards(args.tag, Path(args.dist), Path(args.repo_root).resolve())
    for line in lines:
        print(line)
    if not ok:
        print("REFUSING TO PUBLISH.", file=sys.stderr)
        return 1
    print("All release guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
