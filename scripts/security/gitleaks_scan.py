"""Best-effort local gitleaks hook.

gitleaks knows many provider key shapes that
``scripts/security/secret_scan.py`` does not, so it runs alongside it.

The gitleaks binary is not installed everywhere (it needs Go to build from
source, and this project keeps pre-commit dependency-free). This hook
therefore runs gitleaks on the staged commit when the binary is available,
and skips with a clear message when it is not - a missing tool must not
block a commit. The CI job ``Gitleaks Secret Scan`` always runs gitleaks
over the history, so a shape this hook misses locally is still caught
before it reaches main.

The binary is found on PATH, or via ``GITLEAKS_BIN``.

Usage (pre-commit calls it with no arguments):

    python scripts/security/gitleaks_scan.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

_ENV_BIN = "GITLEAKS_BIN"

# The official gitleaks pre-commit entry, run against the staged commit.
_STAGED_ARGS = ["git", "--pre-commit", "--redact", "--staged", "--verbose"]


def find_gitleaks() -> str | None:
    """Return the gitleaks binary to run, or None when there is none."""
    override = os.environ.get(_ENV_BIN, "").strip()
    if override:
        return shutil.which(override) or override
    return shutil.which("gitleaks")


def main(argv: list[str] | None = None) -> int:
    """Run gitleaks on the staged commit, or skip when it is not installed."""
    binary = find_gitleaks()
    if not binary:
        print(
            "gitleaks-scan: gitleaks is not installed, so the local scan is "
            "skipped. The CI job 'Gitleaks Secret Scan' runs it over the full "
            "history."
        )
        return 0

    try:
        result = subprocess.run([binary, *_STAGED_ARGS], check=False)
    except OSError as exc:
        # A best-effort local layer never blocks a commit on its own setup.
        print(f"gitleaks-scan: could not run {binary}: {exc}", file=sys.stderr)
        return 0
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
