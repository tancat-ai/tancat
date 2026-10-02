"""Pre-commit secret guard.

Blocks a commit that would add a hardcoded API key or token to the repository.
Stdlib only, so it is fast and needs no project dependencies.

Usage (pre-commit passes the staged filenames):

    python scripts/security/secret_scan.py <file> [<file> ...]

Run with no arguments to scan the files staged for commit.

Exit code 0 = clean. Exit code 1 = at least one secret-shaped token found.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Known token shapes. Each is anchored to a provider prefix so ordinary code
# (variable names, content hashes, slugs) does not trip the guard.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DeepSeek/OpenAI/Anthropic API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("GitLab personal access token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

# A match that carries one of these markers is a documented placeholder, not a
# live secret (for example ``sk-your-key-here``). ``sk-REDACTED`` is the value
# this repository uses when a key is scrubbed from history.
_PLACEHOLDERS: tuple[str, ...] = (
    "redacted",
    "example",
    "your",
    "dummy",
    "placeholder",
    "changeme",
    "xxxx",
    "test",
)


@dataclass(frozen=True)
class Finding:
    """One secret-shaped token found in a file."""

    path: str
    line_no: int
    kind: str


def scan_text(text: str, path: str = "<text>") -> list[Finding]:
    """Return every secret-shaped token in ``text``, line by line."""
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _PATTERNS:
            for match in pattern.finditer(line):
                if any(marker in match.group(0).lower() for marker in _PLACEHOLDERS):
                    continue
                findings.append(Finding(path=path, line_no=line_no, kind=kind))
    return findings


def scan_file(path: str | Path) -> list[Finding]:
    """Scan one file. Missing or unreadable files are treated as clean."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(text, str(file_path))


def staged_files() -> list[str]:
    """Filenames staged for commit, used when the hook gets no arguments."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    """Entry point: scan the given paths (or the staged set) and report."""
    paths = list(argv) if argv is not None else sys.argv[1:]
    if not paths:
        paths = staged_files()

    findings: list[Finding] = []
    for path in paths:
        findings.extend(scan_file(path))

    if not findings:
        return 0

    print("secret-scan: blocked a hardcoded secret:", file=sys.stderr)
    for finding in findings:
        # The token itself is never printed, so the guard cannot leak it.
        print(f"  {finding.path}:{finding.line_no}: {finding.kind}", file=sys.stderr)
    print(
        "Move the value to an environment variable or a gitignored .env file.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
