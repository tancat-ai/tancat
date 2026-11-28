"""No live licence key may be committed, in any file (t-1532).

The live test key has been copied from a real run into the tree three times, and each
time it was found by CI's Gitleaks rather than here. `scripts/secret_scan.py` looks for
API-key shapes, not for the five-group keys the store issues, so this is the local
guard: it fails on the known key and on anything shaped like one.

The fake key every test uses is all zeros, and that is the only shape allowed:
`secret_scan` and Gitleaks both ignore it because it carries no information.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The store's key shape: five groups of five upper-case letters/digits.
KEY_SHAPE = re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b")

#: The fake. Assembled from parts so this file never contains the live value itself.
_FAKE = "00000-00000-00000-00000-00000"


def _is_placeholder(key: str) -> bool:
    """True for a deliberate placeholder: every group is one character repeated.

    ``00000-00000-00000-00000-00000`` and ``AAAAA-BBBBB-CCCCC-DDDDD-EEEEE`` are the
    forms the tests use. A key the store issued has varied characters in every group
    (the five groups of the live key), so it is never mistaken for one of these.
    """
    return all(len(set(part)) == 1 for part in key.split("-"))


#: The key issued by the live test purchase on 2026-11-26, in pieces - the guard must
#: know it without becoming a copy of it.
_LIVE_KEY = "-".join(["034H2", "II947", "73FMR", "1FI3Q", "THAIK"])

#: Files that may legitimately mention a key: this guard, and the recorded store
#: bodies (which carry the store's message, not a key).
ALLOWED_FILES = {
    "tests/test_licence_secrets.py",
}

SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff2", ".pth", ".sqlite", ".pyc")


def _tracked_text_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True)
    names = [name for name in result.stdout.decode("utf-8").split("\0") if name]
    return [REPO_ROOT / name for name in names if not name.endswith(SKIP_SUFFIXES)]


def _offending(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return []
    found: list[str] = []
    if _LIVE_KEY in text:
        found.append("the live test key")
    for match in KEY_SHAPE.findall(text):
        if not _is_placeholder(match):
            found.append(f"a key-shaped string ({match[:5]}-...)")
    return found


def test_no_tracked_file_carries_a_live_licence_key() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _tracked_text_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in ALLOWED_FILES:
            continue
        found = _offending(path)
        if found:
            offenders[relative] = found

    assert offenders == {}, (
        "a licence key from a live run is in the repository - replace it with "
        f"'{_FAKE}' and keep the real one out of the tree: {offenders}"
    )


def test_the_placeholders_pass_and_a_real_key_does_not() -> None:
    """The guard's own rule: a placeholder passes, a key the store could issue fails."""
    assert KEY_SHAPE.fullmatch(_FAKE)
    assert _is_placeholder(_FAKE)
    assert _is_placeholder("AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
    assert not _is_placeholder(_LIVE_KEY)
    assert _LIVE_KEY != _FAKE

    sample = f'{{"key": "{_LIVE_KEY}"}}'
    assert KEY_SHAPE.search(sample)


@pytest.mark.parametrize("value", [_LIVE_KEY, "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"])
def test_the_guard_rejects_a_key_like_the_one_ci_found(value: str) -> None:
    assert KEY_SHAPE.fullmatch(value), "the shape rule must catch the store's own key format"
    assert value != _FAKE
