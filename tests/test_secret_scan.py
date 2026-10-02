"""Tests for the pre-commit secret guard (``scripts/security/secret_scan.py``).

Covers the contract the owner approved: the guard fails on a planted key and
passes without one, and it never fires on the documented placeholder that the
history scrub writes into scrubbed commits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.security import secret_scan

# Assembled from parts so this test file never carries a scannable token.
FAKE_DEEPSEEK_KEY = "sk-" + "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
FAKE_AWS_KEY = "AKIA" + "IOSFODNN7REALKEY"
SCRUB_PLACEHOLDER_KEY = "sk-REDACTED"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_planted_key_is_flagged(tmp_path: Path) -> None:
    """A planted DeepSeek key must be caught, and the hook must fail."""
    path = _write(tmp_path, "leaky.py", f'API_KEY = "{FAKE_DEEPSEEK_KEY}"\n')

    findings = secret_scan.scan_file(path)

    assert findings, "a planted DeepSeek key must be flagged"
    assert findings[0].kind == "DeepSeek/OpenAI/Anthropic API key"
    assert findings[0].line_no == 1
    assert secret_scan.main([str(path)]) == 1


def test_clean_file_passes(tmp_path: Path) -> None:
    """A file that reads the key from the environment must pass."""
    path = _write(
        tmp_path,
        "clean.py",
        'import os\n\nAPI_KEY = os.environ["DEEPSEEK_API_KEY"]\n',
    )

    assert secret_scan.scan_file(path) == []
    assert secret_scan.main([str(path)]) == 0


def test_scrub_placeholder_is_allowed(tmp_path: Path) -> None:
    """The placeholder written by the history scrub must not be flagged."""
    path = _write(tmp_path, "scrubbed.py", f'API_KEY = "{SCRUB_PLACEHOLDER_KEY}"\n')

    assert secret_scan.scan_file(path) == []
    assert secret_scan.main([str(path)]) == 0


def test_other_token_shapes_are_flagged(tmp_path: Path) -> None:
    """The guard is not DeepSeek-only; other provider prefixes are covered too."""
    aws = _write(tmp_path, "aws.py", f'AWS_ACCESS_KEY_ID = "{FAKE_AWS_KEY}"\n')

    findings = secret_scan.scan_file(aws)

    assert findings, "an AWS access key id must be flagged"
    assert findings[0].kind == "AWS access key id"


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("gh.py", 'TOKEN = "ghp_' + "a" * 36 + '"\n'),
        ("google.py", 'KEY = "AIza' + "b" * 35 + '"\n'),
        ("gitlab.py", 'TOKEN = "glpat-' + "c" * 20 + '"\n'),
    ],
)
def test_more_provider_prefixes(tmp_path: Path, name: str, content: str) -> None:
    path = _write(tmp_path, name, content)

    assert secret_scan.scan_file(path), f"{name} must be flagged"
